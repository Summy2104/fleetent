import * as React from 'react'

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'

export interface SimpleSelectOption {
  value: string
  label: string
}

export interface SimpleSelectProps {
  options: SimpleSelectOption[]
  value?: string | null
  onValueChange?: (value: string) => void
  placeholder?: string
  disabled?: boolean
  triggerId?: string
  triggerClassName?: string
  triggerAriaLabel?: string
  triggerSize?: 'sm' | 'default'
}

/**
 * Thin wrapper over the shadcn/Base UI `Select` composite for the common
 * single-value case: pass `options` instead of composing children by hand.
 */
export function SimpleSelect({
  options,
  value,
  onValueChange,
  placeholder,
  disabled,
  triggerId,
  triggerClassName,
  triggerAriaLabel,
  triggerSize,
}: SimpleSelectProps) {
  const items = React.useMemo(
    () => Object.fromEntries(options.map((option) => [option.value, option.label])),
    [options]
  )

  return (
    <Select
      disabled={disabled}
      items={items}
      onValueChange={(next) => onValueChange?.((next ?? '') as string)}
      value={value ?? ''}
    >
      <SelectTrigger
        aria-label={triggerAriaLabel}
        className={cn('w-full', triggerClassName)}
        id={triggerId}
        size={triggerSize}
      >
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
