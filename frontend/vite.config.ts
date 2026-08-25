// 빌드 설정.
//
// 이 파일은 원래 Manus AI 작업 환경에서 만들어져, 그쪽 전용 플러그인 네 개를 달고 있었다
// (manus-runtime, jsx-loc, 디버그 로그 수집기, 스토리지 프록시). 우리 서비스에는 쓸모가
// 없는데다 그중 manus-runtime은 **빌드 결과 index.html에 367KB짜리 스크립트를 주입**해서,
// 우리가 배포하는 페이지에 남의 추적 코드가 그대로 실려 나갔다. 전부 걷어냈다.
//
// 지금 남은 것은 React와 Tailwind 둘뿐이다.
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "client", "src"),
      "@shared": path.resolve(import.meta.dirname, "shared"),
    },
  },
  // .env를 frontend/ 에서 읽는다(client/ 가 아니라). VITE_API_BASE_URL이 여기 있다.
  envDir: path.resolve(import.meta.dirname),
  root: path.resolve(import.meta.dirname, "client"),
  build: {
    // 배포는 이 폴더의 정적 파일만 올리면 된다 — 서버가 필요 없다.
    outDir: path.resolve(import.meta.dirname, "dist/public"),
    emptyOutDir: true,
  },
  server: {
    port: 3000,
    strictPort: false,
    host: true,
  },
});
