import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { api, errorMessage } from "../../api/listingsApi";

export const PAGE_SIZE = 25;

// Every thunk rejects with { message, status } so the UI can show the FastAPI error.
const reject = (thunkAPI, err) =>
  thunkAPI.rejectWithValue({ message: errorMessage(err), status: err?.response?.status ?? null });

export const fetchListings = createAsyncThunk("listings/fetch", async ({ skip = 0 } = {}, thunkAPI) => {
  try {
    const res = await api.get("/listings", { params: { skip, limit: PAGE_SIZE } });
    return res.data; // { total, skip, limit, items }
  } catch (err) {
    return reject(thunkAPI, err);
  }
});

export const createListing = createAsyncThunk("listings/create", async (payload, thunkAPI) => {
  try {
    const res = await api.post("/listings", payload);
    return res.data;
  } catch (err) {
    return reject(thunkAPI, err);
  }
});

export const updateListing = createAsyncThunk("listings/update", async ({ id, changes }, thunkAPI) => {
  try {
    const res = await api.put(`/listings/${id}`, changes);
    return res.data;
  } catch (err) {
    return reject(thunkAPI, err);
  }
});

export const deleteListing = createAsyncThunk("listings/delete", async (id, thunkAPI) => {
  try {
    await api.delete(`/listings/${id}`);
    return id;
  } catch (err) {
    return reject(thunkAPI, err);
  }
});

const initialState = {
  items: [],
  total: 0,
  skip: 0,
  status: "idle", // idle | loading | succeeded | failed
  error: null,
  notice: null, // last success message shown on Home
};

const listingsSlice = createSlice({
  name: "listings",
  initialState,
  reducers: {
    clearMessages(state) {
      state.error = null;
      state.notice = null;
    },
    resetListings() {
      return initialState;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchListings.pending, (s) => {
        s.status = "loading";
        s.error = null;
      })
      .addCase(fetchListings.fulfilled, (s, a) => {
        s.status = "succeeded";
        s.items = a.payload.items;
        s.total = a.payload.total;
        s.skip = a.payload.skip;
      })
      .addCase(fetchListings.rejected, (s, a) => {
        s.status = "failed";
        s.error = a.payload?.message ?? a.error.message;
      })

      .addCase(createListing.fulfilled, (s, a) => {
        s.items.unshift(a.payload); // newest first, same order as GET /listings
        if (s.skip === 0 && s.items.length > PAGE_SIZE) s.items.pop(); // keep one page
        s.total += 1;
        s.error = null;
        s.notice = `Created listing ${a.payload.listing_code} (ID ${a.payload.id})`;
      })
      .addCase(updateListing.fulfilled, (s, a) => {
        const i = s.items.findIndex((l) => l.id === a.payload.id);
        if (i !== -1) s.items[i] = a.payload;
        else s.items.unshift(a.payload);
        s.error = null;
        s.notice = `Updated listing ${a.payload.listing_code} (ID ${a.payload.id})`;
      })
      .addCase(deleteListing.fulfilled, (s, a) => {
        s.items = s.items.filter((l) => l.id !== a.payload);
        s.total = Math.max(0, s.total - 1);
        s.error = null;
        s.notice = `Deleted listing ID ${a.payload}`;
      })

      .addMatcher(
        (a) => [createListing.rejected.type, updateListing.rejected.type, deleteListing.rejected.type].includes(a.type),
        (s, a) => {
          s.error = a.payload?.message ?? a.error.message;
          s.notice = null;
        }
      );
  },
});

export const { clearMessages, resetListings } = listingsSlice.actions;
export default listingsSlice.reducer;
