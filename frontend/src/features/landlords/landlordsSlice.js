import { createAsyncThunk, createSlice } from "@reduxjs/toolkit";
import { api, errorMessage } from "../../api/listingsApi";

// Landlords are only read here, to fill the dropdowns and show owner names.
export const fetchLandlords = createAsyncThunk("landlords/fetch", async (_, thunkAPI) => {
  try {
    const res = await api.get("/landlords", { params: { skip: 0, limit: 200 } });
    return res.data.items;
  } catch (err) {
    return thunkAPI.rejectWithValue(errorMessage(err));
  }
});

const landlordsSlice = createSlice({
  name: "landlords",
  initialState: { items: [], status: "idle", error: null },
  reducers: {},
  extraReducers: (builder) => {
    builder
      .addCase(fetchLandlords.pending, (s) => {
        s.status = "loading";
      })
      .addCase(fetchLandlords.fulfilled, (s, a) => {
        s.status = "succeeded";
        s.items = a.payload;
        s.error = null;
      })
      .addCase(fetchLandlords.rejected, (s, a) => {
        s.status = "failed";
        s.error = a.payload ?? a.error.message;
      });
  },
});

export default landlordsSlice.reducer;
