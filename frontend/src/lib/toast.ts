/**
 * Toast public API — thin wrapper over `sonner` so call sites stay decoupled
 * from the underlying toast library. The visual host is `<Toaster />` from
 * `@/components/ui/sonner`, mounted once at the app root.
 */

import { toast as sonnerToast } from 'sonner'

export type ToastVariant = 'success' | 'error' | 'info'

export type ToastInput = {
  title: string
  description?: string
  variant?: ToastVariant
  duration?: number
}

export function pushToast(input: ToastInput): void {
  const { title, description, variant = 'info', duration } = input
  sonnerToast[variant](title, { description, duration })
}

export const toast = {
  success: (title: string, description?: string) => sonnerToast.success(title, { description }),
  error: (title: string, description?: string) => sonnerToast.error(title, { description }),
  info: (title: string, description?: string) => sonnerToast.info(title, { description }),
}
