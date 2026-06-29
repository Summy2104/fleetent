import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';

export default defineConfig({
  base: '/admin/ui/',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 4173,
    // Dev-only: forward admin API calls to the platform backend. The frontend
    // itself is served under /admin/ui, so bypass that prefix and proxy the rest.
    proxy: {
      '/admin': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        bypass(req) {
          if (req.url?.startsWith('/admin/ui')) {
            return req.url;
          }
        },
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
});
