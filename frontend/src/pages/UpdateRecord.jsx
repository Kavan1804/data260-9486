import React, { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useNavigate, useParams } from "react-router-dom";
import { api, errorMessage } from "../api/listingsApi.js";
import { clearMessages, updateListing } from "../features/listings/listingsSlice.js";

const FIELDS = ["title", "address", "listing_code", "available_units", "landlord_id"];

export default function UpdateRecord() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { id: routeId } = useParams();
  const items = useSelector((s) => s.listings.items);
  const landlords = useSelector((s) => s.landlords.items);
  const error = useSelector((s) => s.listings.error);

  const [idInput, setIdInput] = useState(routeId ?? "");
  const [original, setOriginal] = useState(null);
  const [form, setForm] = useState(null);
  const [loadError, setLoadError] = useState("");

  // Select by ID: use the copy in Redux if it is on the current page, else GET /listings/{id}.
  async function load(id) {
    setLoadError("");
    setOriginal(null);
    setForm(null);
    const listingId = Number(id);
    if (!Number.isInteger(listingId) || listingId < 1) {
      setLoadError("Enter a positive listing ID");
      return;
    }
    try {
      const listing = items.find((l) => l.id === listingId) ?? (await api.get(`/listings/${listingId}`)).data;
      setOriginal(listing);
      setForm(Object.fromEntries(FIELDS.map((f) => [f, listing[f]])));
    } catch (err) {
      setLoadError(errorMessage(err));
    }
  }

  useEffect(() => {
    dispatch(clearMessages());
    if (routeId) load(routeId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeId]);

  const onChange = (e) => setForm((f) => ({ ...f, [e.target.name]: e.target.value }));

  async function handleSubmit(e) {
    e.preventDefault();
    dispatch(clearMessages());
    // Send only the fields that changed (the API accepts partial updates).
    const changes = {};
    for (const f of FIELDS) {
      const value = f === "available_units" || f === "landlord_id" ? Number(form[f]) : form[f];
      if (value !== original[f]) changes[f] = value;
    }
    if (Object.keys(changes).length === 0) {
      setLoadError("Nothing changed");
      return;
    }
    try {
      await dispatch(updateListing({ id: original.id, changes })).unwrap();
      navigate("/");
    } catch {
      // error message is in Redux state
    }
  }

  return (
    <div className="card">
      <div className="card-header">
        <div className="page-title">Update Listing{original ? ` (ID: ${original.id})` : ""}</div>
        <div className="subtitle">Select a listing by ID, then dispatch the updateListing thunk (PUT /listings/:id)</div>
      </div>

      <div className="card-body">
        <form
          className="form id-picker"
          onSubmit={(e) => {
            e.preventDefault();
            load(idInput);
          }}
        >
          <label>
            Listing ID
            <input type="number" min={1} value={idInput} onChange={(e) => setIdInput(e.target.value)} required />
          </label>
          <button className="btn" type="submit">
            Load listing
          </button>
        </form>

        {loadError && <div className="error-text">{loadError}</div>}

        {form && (
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
              <input name="listing_code" value={form.listing_code} onChange={onChange} required />
            </label>
            <label>
              Available units
              <input name="available_units" type="number" min={0} max={500} value={form.available_units} onChange={onChange} required />
            </label>
            <label>
              Landlord
              <select name="landlord_id" value={form.landlord_id} onChange={onChange} required>
                {landlords.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.id} - {l.full_name} ({l.company})
                  </option>
                ))}
              </select>
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
