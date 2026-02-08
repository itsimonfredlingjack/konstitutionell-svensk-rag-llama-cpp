/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL: string;
  readonly VITE_SCORE_THRESHOLD_GOOD: string;
  readonly VITE_SCORE_THRESHOLD_OK: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
