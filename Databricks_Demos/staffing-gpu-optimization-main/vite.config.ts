import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import { defineConfig } from "vite";
import path from "node:path";

export default defineConfig({
  root: "./src/staffing_optimization/ui",
  build: {
    outDir: "../__dist__",
    emptyOutDir: true,
  },
  define: {
    __APP_NAME__: JSON.stringify("Staffing Optimization"),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src/staffing_optimization/ui"),
    },
  },
  plugins: [
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
      routesDirectory: "./routes",
      generatedRouteTree: "./types/routeTree.gen.ts",
    }),
    react(),
    tailwindcss(),
  ],
});
