/**
 * Compatibility shim — the toast host now lives in `./sonner`. Kept so any
 * lingering `@/components/ui/toaster` imports still resolve. Prefer importing
 * from `@/components/ui/sonner` directly.
 */
export { Toaster } from './sonner'
