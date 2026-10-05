import React, { useEffect, useState } from "react";
import { useDispatch } from "react-redux";
import { Route, Routes } from "react-router-dom";

import Navbar from "./components/Navbar.jsx";
import Login from "./pages/Login.jsx";
import Home from "./pages/Home.jsx";
import CreateRecord from "./pages/CreateRecord.jsx";
import UpdateRecord from "./pages/UpdateRecord.jsx";

import { me } from "./api/listingsApi.js";
import { fetchLandlords } from "./features/landlords/landlordsSlice.js";
import { fetchListings, resetListings } from "./features/listings/listingsSlice.js";

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
  const dispatch = useDispatch();
  // Auth stays local React state (HW4); listing data lives in the Redux store.
  const [auth, setAuth] = useState({ checked: false, loggedIn: false, user: null });

  // On first load, ask the backend whether the HTTP-only cookie is still a valid session.
  useEffect(() => {
    me()
      .then((user) => setAuth({ checked: true, loggedIn: true, user }))
      .catch(() => setAuth({ checked: true, loggedIn: false, user: null }));
  }, []);

  useEffect(() => {
    if (auth.loggedIn) {
      dispatch(fetchListings({ skip: 0 }));
      dispatch(fetchLandlords());
    } else {
      dispatch(resetListings());
    }
  }, [auth.loggedIn, dispatch]);

  return (
    <div className="container">
      <Navbar auth={auth} />
      <Login auth={auth} setAuth={setAuth} />

      <Routes>
        <Route path="/" element={<Home auth={auth} />} />
        <Route path="/create" element={<RequireAuth auth={auth}><CreateRecord /></RequireAuth>} />
        <Route path="/update" element={<RequireAuth auth={auth}><UpdateRecord /></RequireAuth>} />
        <Route path="/update/:id" element={<RequireAuth auth={auth}><UpdateRecord /></RequireAuth>} />
      </Routes>
    </div>
  );
}
