import React, { useMemo } from "react";
import { useDispatch, useSelector } from "react-redux";
import { Link } from "react-router-dom";
import { PAGE_SIZE, deleteListing, fetchListings } from "../features/listings/listingsSlice.js";

export default function Home({ auth }) {
  const dispatch = useDispatch();
  // Everything on this page is read from the Redux store.
  const { items, total, skip, status, error, notice } = useSelector((s) => s.listings);
  const landlords = useSelector((s) => s.landlords.items);
  const landlordName = useMemo(() => new Map(landlords.map((l) => [l.id, l.full_name])), [landlords]);

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

  const from = total === 0 ? 0 : skip + 1;
  const to = skip + items.length;

  return (
    <div className="card">
      <div className="card-header">
        <div>
          <div className="page-title">Rental Listings</div>
          <div className="subtitle">
            Redux store: showing {from}-{to} of {total} listings from FastAPI + MySQL (s9486_rel).
          </div>
        </div>
        <Link className="btn primary" to="/create">
          + Add Listing
        </Link>
      </div>

      <div className="card-body">
        {notice && <div className="notice success-text">{notice}</div>}
        {error && <div className="notice error-text">{error}</div>}
        {status === "loading" ? (
          <div className="notice">Loading listings...</div>
        ) : items.length === 0 ? (
          <div className="notice">No listings found. Click "Add Listing".</div>
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Address</th>
                  <th>Units</th>
                  <th>Landlord</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.id}>
                    <td>{l.id}</td>
                    <td className="nowrap">{l.listing_code}</td>
                    <td>{l.title}</td>
                    <td>{l.address}</td>
                    <td>{l.available_units}</td>
                    <td>{landlordName.get(l.landlord_id) ?? `#${l.landlord_id}`}</td>
                    <td className="actions">
                      <Link className="btn" to={`/update/${l.id}`}>
                        Update
                      </Link>
                      <button className="btn danger" onClick={() => dispatch(deleteListing(l.id))}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pager">
          <button className="btn" disabled={skip === 0} onClick={() => dispatch(fetchListings({ skip: Math.max(0, skip - PAGE_SIZE) }))}>
            Previous
          </button>
          <button className="btn" disabled={to >= total} onClick={() => dispatch(fetchListings({ skip: skip + PAGE_SIZE }))}>
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
