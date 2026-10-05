import React, { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate } from "react-router-dom";
import { clearMessages, createListing } from "../features/listings/listingsSlice.js";

const EMPTY = { title: "", address: "", listing_code: "", available_units: 1, landlord_id: "" };

export default function CreateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const landlords = useSelector((s) => s.landlords.items);
  const error = useSelector((s) => s.listings.error);

  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const onChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    dispatch(clearMessages());
    setSaving(true);
    try {
      await dispatch(
        createListing({ ...form, available_units: Number(form.available_units), landlord_id: Number(form.landlord_id) })
      ).unwrap(); // throws on rejected, so we only leave the page on success
      navigate("/");
    } catch {
      setSaving(false); // the error message is in Redux state
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="page-title">Add Listing</div>
        <div className="subtitle">Dispatches the createListing thunk (POST /listings)</div>
      </div>

      <div className="card-body">
        <form className="form" onSubmit={handleSubmit}>
          <label>
            Listing title
            <input name="title" value={form.title} onChange={onChange} maxLength={200} required />
          </label>
          <label>
            Property address
            <input name="address" value={form.address} onChange={onChange} maxLength={255} required />
          </label>
          <label>
            Listing code (unique, format LST-12345)
            <input name="listing_code" value={form.listing_code} onChange={onChange} placeholder="LST-12345" required />
          </label>
          <label>
            Available units
            <input name="available_units" type="number" min={0} max={500} value={form.available_units} onChange={onChange} required />
          </label>
          <label>
            Landlord
            <select name="landlord_id" value={form.landlord_id} onChange={onChange} required>
              <option value="">Select a landlord</option>
              {landlords.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.id} - {l.full_name} ({l.company})
                </option>
              ))}
            </select>
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
