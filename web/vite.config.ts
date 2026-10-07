/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const API_PATHS = [
  '/auth',
  '/me',
  '/healthz',
  '/cohort',
  '/patients',
  '/readings',
  '/alerts',
  '/export',
  '/model',
  '/stats',
  '/metrics',
];
const BACKEND = process.env.GLUCORAG_BACKEND ?? 'http://127.0.0.1:8000';

export default defineConfig({
  base: '/ui/',
  plugins: [react()],
  build: {
    outDir: '../glucorag/api/static',
    emptyOutDir: true,
    sourcemap: false,
    // The CSP forbids inline scripts: never inline the module preload polyfill.
    modulePreload: { polyfill: false },
    rollupOptions: {
      output: {
        // Vendor code changes rarely: separate chunks keep the immutable cache warm across releases.
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (/[\\/](recharts|d3-[^\\/]+|victory-vendor|decimal\.js-light|es-toolkit|immer|reselect|@reduxjs|react-redux|redux)[\\/]/.test(id)) return 'charts';
          return 'vendor';
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: Object.fromEntries(API_PATHS.map((p) => [p, { target: BACKEND, changeOrigin: false }])),
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    restoreMocks: true,
  },
});
