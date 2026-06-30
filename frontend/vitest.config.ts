import path from 'node:path'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

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
    // instrumentation plus worker contention slows them enough to flake —
    // give ample headroom. 45s only ever bites a genuinely stuck test.
    testTimeout: 60000,
    hookTimeout: 60000,
    // Cap parallelism hard: under v8 coverage the heavy page suites (Radix
    // Select/Dialog flows driven by userEvent) starve each other for CPU when
    // many workers run at once, producing flaky timeouts that move between
    // files run to run. Two workers keeps each suite on enough cores to finish
    // well within the timeout; we trade wall-clock for deterministic runs.
    maxWorkers: 2,
    minWorkers: 1,
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
})
