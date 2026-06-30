/**
 * Toast bus built on a window CustomEvent. Using the window as the channel
 * (instead of a module-level singleton store) keeps it robust across Vite HMR
 * module re-instantiation: emitter and listener always meet on the one window.
 */

export type ToastVariant = 'success' | 'error' | 'info'

export type ToastInput = {
  title: string
  description?: string
  variant?: ToastVariant
  duration?: number
}

export const TOAST_EVENT = 'fleetent:toast'

export function pushToast(input: ToastInput): void {
  if (typeof window === 'undefined') {
    return
  }
  window.dispatchEvent(new CustomEvent<ToastInput>(TOAST_EVENT, { detail: input }))
}

export const toast = {
  success: (title: string, description?: string) => pushToast({ title, description, variant: 'success' }),
  error: (title: string, description?: string) => pushToast({ title, description, variant: 'error' }),
  info: (title: string, description?: string) => pushToast({ title, description, variant: 'info' }),
}
