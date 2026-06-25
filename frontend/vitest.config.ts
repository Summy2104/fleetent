import path from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    // Interaction-heavy component tests (Radix Select/Dialog flows driven by
    // userEvent) run well under the 5s default normally, but v8 coverage
    // instrumentation slows them enough to flake — give ample headroom.
    testTimeout: 15000,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/main.tsx'],
      thresholds: {
        lines: 76,
        functions: 76,
        branches: 70,
        statements: 76,
      },
    },
  },
});
