import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3003,
    host: "0.0.0.0",
    allowedHosts: ["swerag.fredlingautomation.dev"],
  },
  build: {
    // Code splitting for better caching
    rollupOptions: {
      output: {
        manualChunks: {
          // Vendor chunk: React and core libraries
          "vendor-react": ["react", "react-dom"],
          // 3D libraries in separate chunk (largest dependencies)
          "vendor-three": [
            "three",
            "@react-three/fiber",
            "@react-three/drei",
            "@react-three/postprocessing",
          ],
          // Animation libraries
          "vendor-animation": ["framer-motion"],
          // State management and utilities
          "vendor-utils": ["zustand", "clsx", "tailwind-merge"],
        },
      },
    },
    // Chunk size warning limit (increased since we're code-splitting)
    chunkSizeWarningLimit: 600,
    // Source maps for production debugging (optional, can disable for smaller builds)
    sourcemap: false,
    // Minification
    minify: "esbuild",
    // Target modern browsers for smaller output
    target: "esnext",
  },
});
