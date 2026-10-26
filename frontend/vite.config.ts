import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the FastAPI backend runs on 127.0.0.1:8000 and is proxied under /api.
// Build: static files in frontend/dist, served by the backend at "/".
export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: false,
  },
});
