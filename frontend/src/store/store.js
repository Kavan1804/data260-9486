import { configureStore } from "@reduxjs/toolkit";
import listingsReducer from "../features/listings/listingsSlice";
import landlordsReducer from "../features/landlords/landlordsSlice";

export const store = configureStore({
  reducer: {
    listings: listingsReducer,
    landlords: landlordsReducer,
  },
});
