import React, { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { errorMessage, fetchListingById } from "../api/listingsApi.js";

export default function DeleteRecord({ onDelete }) {
  const { id } = useParams();
  const listingId = Number(id);

  const [listing, setListing] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        setListing(await fetchListingById(listingId));
      } catch {
        setListing(null);
      } finally {
        setLoading(false);
      }
    })();
  }, [listingId]);

  async function handleDelete() {
    setError("");
    try {
      await onDelete(listingId);
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  if (loading) return <div className="notice">Loading listing...</div>;

  return (
    <div className="card">
      <div className="card-header">
        <div className="page-title">Delete Listing</div>
      </div>

      <div className="card-body">
        {listing ? (
          <>
            <p style={{ fontSize: "18px", marginBottom: "24px" }}>
              Are you sure you want to delete <strong>{listing.title}</strong> ({listing.address})?
            </p>
            {error && <p className="error-text">{error}</p>}
            <button className="btn danger" onClick={handleDelete}>
              Delete Listing
            </button>
          </>
        ) : (
          <div className="notice">Listing not found (or already deleted).</div>
        )}
      </div>
    </div>
  );
}
