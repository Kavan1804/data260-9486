import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { errorMessage, fetchListingById } from "../api/listingsApi.js";

export default function UpdateRecord({ onUpdate }) {
  const { id } = useParams();
  const listingId = Number(id);

  const [title, setTitle] = useState("");
  const [address, setAddress] = useState("");
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const listing = await fetchListingById(listingId);
        setTitle(listing.title);
        setAddress(listing.address);
        setNotFound(false);
      } catch {
        setNotFound(true);
      } finally {
        setLoading(false);
      }
    })();
  }, [listingId]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await onUpdate(listingId, { title, address });
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (loading) return <div className="notice">Loading listing...</div>;

  return (
    <div className="card">
      <div className="card-header">
        <div className="page-title">Update Listing (ID: {listingId})</div>
      </div>

      <div className="card-body">
        {notFound ? (
          <div className="notice">Listing not found (or already deleted).</div>
        ) : (
          <form className="form" onSubmit={handleSubmit}>
            <label>
              Listing title
              <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} required />
            </label>

            <label>
              Property address
              <input value={address} onChange={(e) => setAddress(e.target.value)} maxLength={255} required />
            </label>

            {error && <div className="error-text">{error}</div>}

            <button className="btn primary" type="submit">
              Save Listing
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
