import path from "path";
import { fileURLToPath } from "url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  // 玩法、数值、选手照片全部来自本地调参后台。打包成单文件之后页面由
  // bdserver 自己 serve（同源），所以代理只在 dev 下需要。
  server: {
    proxy: {
      "/api": { target: "http://127.0.0.1:8621", changeOrigin: true },
      "/img": { target: "http://127.0.0.1:8621", changeOrigin: true },
    },
  },
});
