import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// API port defaults to 8000 but can be overridden (e.g. when 8000 is blocked
// on Windows by a reserved port range). run_dev.ps1 sets API_PORT accordingly.
const apiPort = process.env.API_PORT || "8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
      },
    },
  },
});
