import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Relative base so the same build works on GitHub Pages and behind the local server.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    proxy: { "/api": "http://127.0.0.1:8077", "/data": "http://127.0.0.1:8077" },
  },
});
