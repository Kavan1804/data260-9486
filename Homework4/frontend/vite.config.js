import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // Must match FRONTEND_ORIGINS in the backend CORS config.
  server: { port: 5173, strictPort: true },
});
