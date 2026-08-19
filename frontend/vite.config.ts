import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite creates the local React development server.
export default defineConfig({
  plugins: [react()],
});
