import React from "react";
import { Link } from "react-router-dom";

export default function Home({ listings, loading, error, auth }) {
  if (!auth.loggedIn) {
    return (
      <div className="card">
        <div className="card-header">
          <div>
            <div className="page-title">Login required</div>
            <div className="subtitle">Log in with your email and password to view rental listings.</div>
          </div>
        </div>
        <div className="card-body">
          <div className="notice">Login required. The listings API only answers requests with a valid session.</div>
        </div>
      </div>
    );
  }

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="page-title">Rental Listings</div>
          <div className="subtitle">
            {listings.length} listings loaded from FastAPI + MySQL (s9486_rel) using your session cookie.
          </div>
        </div>
        <Link className="btn primary" to="/create">
          + Add Listing
        </Link>
      </div>

      <div className="card-body">
        {error && <div className="notice error-text">{error}</div>}
        {loading ? (
          <div className="notice">Loading listings...</div>
        ) : listings.length === 0 ? (
          <div className="notice">No listings found. Click "Add Listing".</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Title</th>
                  <th>Address</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {listings.map((l) => (
                  <tr key={l.id}>
                    <td>{l.id}</td>
                    <td>{l.title}</td>
                    <td>{l.address}</td>
                    <td className="actions">
                      <Link className="btn" to={`/update/${l.id}`}>
                        Update
                      </Link>
                      <Link className="btn danger" to={`/delete/${l.id}`}>
                        Delete
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
