import React, { useState } from "react";
import { errorMessage } from "../api/listingsApi.js";

export default function CreateRecord({ onAdd }) {
  const [title, setTitle] = useState("");
  const [address, setAddress] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await onAdd({ title, address }); // parent redirects to "/" on success
    } catch (err) {
      setError(errorMessage(err));
      setSaving(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="page-title">Add Listing</div>
        <div className="subtitle">Enter the listing title and property address</div>
      </div>

      <div className="card-body">
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

          <button className="btn primary" type="submit" disabled={saving}>
            Add Listing
          </button>
        </form>
      </div>
    </div>
  );
}
