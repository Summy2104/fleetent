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
    // The interaction-heavy page suites (long Base UI dialog/menu flows driven
    // by userEvent) can still flake under severe CI CPU starvation even with the
    // raised timeouts — a menu occasionally mounts too slowly for one poll. Retry
    // absorbs that scheduler jitter: a genuinely broken test fails all attempts,
    // a flake almost always passes the retry. Paired with split/timeout hardening,
    // not a substitute for it.
    retry: 2,
    // Cap parallelism: under v8 coverage the heavy page suites (Radix
    // Select/Dialog flows driven by userEvent) starve each other for CPU when
    // too many workers share too few cores, producing flaky timeouts that move
    // between files run to run. CI runs this on a 2x runner (~8 vCPU), so 4
    // workers keep ~2 vCPU each — enough headroom to stay deterministic while
    // roughly halving wall-clock versus the old 2-worker cap. Do not raise this
    // beyond the runner's vCPU/2 or the starvation flake returns.
    maxWorkers: 4,
    minWorkers: 2,
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    setupFiles: ['./src/test/setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      // shadcn-generated primitives are vendored, not hand-authored; exclude them
      // from coverage so the threshold reflects our own code, not the UI kit.
      exclude: ['src/main.tsx', 'src/components/ui/**'],
      // Ratchet: floors sit ~1pt below actual coverage to lock in gains without
      // nagging on ordinary refactors. Raise them as coverage climbs; never lower
      // to make a red build pass — add tests instead.
      thresholds: {
        lines: 85,
        functions: 80,
        branches: 71,
        statements: 83,
      },
    },
  },
})
