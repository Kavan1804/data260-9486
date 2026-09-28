import React, { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";

import Navbar from "./components/Navbar.jsx";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import CreateRecord from "./pages/CreateRecord.jsx";
import UpdateRecord from "./pages/UpdateRecord.jsx";
import DeleteRecord from "./pages/DeleteRecord.jsx";

import {
  createListing,
  deleteListing,
  errorMessage,
  fetchListings,
  me,
  updateListing,
} from "./api/listingsApi.js";

function RequireAuth({ auth, children }) {
  if (!auth.checked) return <div className="notice">Checking session...</div>;
  if (!auth.loggedIn) {
    return (
      <div className="card">
        <div className="card-header">
          <div className="page-title">Login required</div>
        </div>
        <div className="card-body">
          <div className="notice">Please log in to add, update, or delete listings.</div>
        </div>
      </div>
    );
  }
  return children;
}

export default function App() {
  const navigate = useNavigate();

  const [auth, setAuth] = useState({ checked: false, loggedIn: false, user: null });
  const [listings, setListings] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // On first load, ask the backend whether the HTTP-only cookie is still a valid session.
  useEffect(() => {
    (async () => {
      try {
        const user = await me();
        setAuth({ checked: true, loggedIn: true, user });
      } catch {
        setAuth({ checked: true, loggedIn: false, user: null });
      }
    })();
  }, []);

  useEffect(() => {
    if (!auth.loggedIn) {
      setListings([]);
      return;
    }
    (async () => {
      try {
        setLoading(true);
        setError("");
        setListings(await fetchListings());
      } catch (err) {
        handleApiError(err);
      } finally {
        setLoading(false);
      }
    })();
  }, [auth.loggedIn]);

  function handleApiError(err) {
    if (err?.response?.status === 401) {
      setAuth({ checked: true, loggedIn: false, user: null });
    } else {
      setError(errorMessage(err));
    }
  }

  // CRUD handlers passed down as props. Errors are rethrown so the form can show them.
  async function onAdd(newListing) {
    try {
      const created = await createListing(newListing);
      setListings((prev) => [created, ...prev]);
      navigate("/");
    } catch (err) {
      if (err?.response?.status === 401) handleApiError(err);
      throw err;
    }
  }

  async function onUpdate(id, changes) {
    try {
      const updated = await updateListing(id, changes);
      setListings((prev) => prev.map((l) => (l.id === id ? updated : l)));
      navigate("/");
    } catch (err) {
      if (err?.response?.status === 401) handleApiError(err);
      throw err;
    }
  }

  async function onDelete(id) {
    try {
      await deleteListing(id);
      setListings((prev) => prev.filter((l) => l.id !== id));
      navigate("/");
    } catch (err) {
      if (err?.response?.status === 401) handleApiError(err);
      throw err;
    }
  }

  return (
    <div className="container">
      <Navbar auth={auth} />
      <Login auth={auth} setAuth={setAuth} />

      <Routes>
        <Route path="/" element={<Home listings={listings} loading={loading} error={error} auth={auth} />} />
        <Route path="/create" element={<RequireAuth auth={auth}><CreateRecord onAdd={onAdd} /></RequireAuth>} />
        <Route path="/update/:id" element={<RequireAuth auth={auth}><UpdateRecord onUpdate={onUpdate} /></RequireAuth>} />
        <Route path="/delete/:id" element={<RequireAuth auth={auth}><DeleteRecord onDelete={onDelete} /></RequireAuth>} />
      </Routes>
    </div>
  );
}
