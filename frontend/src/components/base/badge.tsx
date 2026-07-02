import type * as React from 'react'

import { Badge as UiBadge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

type UiBadgeProps = React.ComponentProps<typeof UiBadge>
type UiBadgeVariant = NonNullable<UiBadgeProps['variant']>

/** shadcn badge variants plus our semantic status colors. */
export type BadgeVariant = UiBadgeVariant | 'success' | 'warning'

/**
 * Extra variants layered on top of the shadcn badge. They reuse the app's
 * `--success` / `--warning` theme tokens (so they track light/dark like the
 * rest of the UI) and mirror the stock `destructive` variant's tint pattern.
 * The classes override the base variant via `twMerge` (later class wins), so
 * the shadcn `ui/badge.tsx` can be regenerated freely without losing these.
 */
const EXTENDED_VARIANTS: Record<'success' | 'warning', string> = {
  success: 'bg-success/10 text-success focus-visible:ring-success/20 dark:bg-success/20 [a]:hover:bg-success/20',
  warning: 'bg-warning/10 text-warning focus-visible:ring-warning/20 dark:bg-warning/20 [a]:hover:bg-warning/20',
}

export interface BadgeProps extends Omit<UiBadgeProps, 'variant'> {
  variant?: BadgeVariant
}

export function Badge({ variant = 'default', className, ...props }: BadgeProps) {
  if (variant === 'success' || variant === 'warning') {
    return <UiBadge className={cn(EXTENDED_VARIANTS[variant], className)} variant="default" {...props} />
  }

  return <UiBadge className={className} variant={variant} {...props} />
}
