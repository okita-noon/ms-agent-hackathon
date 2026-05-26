import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/",
  server: {
    proxy: {
      "/api": "http://localhost:8080",
      "/voicevox": {
        target: "http://localhost:50021",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/voicevox/, ""),
      },
    },
  },
  build: {
    outDir: "dist",
  },
});
