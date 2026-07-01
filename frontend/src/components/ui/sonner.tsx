'use client'

import { CircleCheckIcon, InfoIcon, Loader2Icon, OctagonXIcon, TriangleAlertIcon } from 'lucide-react'
import { Toaster as Sonner, type ToasterProps } from 'sonner'

import { useTheme } from '@/app/theme'

const Toaster = ({ ...props }: ToasterProps) => {
  const { theme } = useTheme()

  return (
    <Sonner
      className="toaster group"
      closeButton
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      position="bottom-right"
      richColors
      style={
        {
          '--normal-bg': 'var(--popover)',
          '--normal-text': 'var(--popover-foreground)',
          '--normal-border': 'var(--border)',
          '--border-radius': 'var(--radius)',
          // Rich-color variants mapped onto the project's theme tokens (these
          // shift automatically between light/dark). Tinted background + solid
          // token border and text/icon color.
          '--success-bg': 'color-mix(in oklab, var(--success) 12%, var(--popover))',
          '--success-border': 'var(--success)',
          '--success-text': 'var(--success)',
          '--error-bg': 'color-mix(in oklab, var(--destructive) 12%, var(--popover))',
          '--error-border': 'var(--destructive)',
          '--error-text': 'var(--destructive)',
          '--warning-bg': 'color-mix(in oklab, var(--warning) 12%, var(--popover))',
          '--warning-border': 'var(--warning)',
          '--warning-text': 'var(--warning)',
          '--info-bg': 'color-mix(in oklab, var(--primary) 12%, var(--popover))',
          '--info-border': 'var(--primary)',
          '--info-text': 'var(--primary)',
        } as React.CSSProperties
      }
      theme={theme}
      toastOptions={{
        classNames: {
          toast: 'cn-toast',
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
