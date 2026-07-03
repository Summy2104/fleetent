import * as React from 'react'

import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxTrigger,
} from '@/components/ui/combobox'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useT } from '@/i18n'
import { cn } from '@/lib/utils'

export interface SimpleSelectOption {
  value: string
  label: string
}

/**
 * Options past this count auto-upgrade the plain dropdown to a searchable one,
 * so long lists stay findable without every call site opting in.
 */
export const SIMPLE_SELECT_SEARCH_THRESHOLD = 8

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
  /** Force the search box on/off. Defaults to auto: on past {@link SIMPLE_SELECT_SEARCH_THRESHOLD}. */
  searchable?: boolean
  /** Search box placeholder (search mode). Defaults to the shared `select.searchPlaceholder`. */
  searchPlaceholder?: string
  /** Message shown when `options` is empty. Defaults to the shared `select.noOptions`. */
  noOptionsLabel?: string
  /** Message shown when a search matches nothing. Defaults to the shared `select.noMatch`. */
  noMatchLabel?: string
}

// Mirrors the plain SelectTrigger look so a dropdown flipping into search mode stays visually identical.
const TRIGGER_CLASS =
  'flex w-full items-center justify-between gap-2 rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs outline-none transition-[color,box-shadow] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 data-disabled:cursor-not-allowed data-disabled:opacity-50 data-[size=default]:h-9 data-[size=sm]:h-8 dark:bg-input/30 dark:hover:bg-input/50'

/**
 * Thin wrapper over the shadcn/Base UI `Select` composite for the common
 * single-value case: pass `options` instead of composing children by hand.
 *
 * Auto-upgrades to a searchable dropdown (Base UI `Combobox`, which portals so
 * it is never clipped inside a scrollable dialog) once the option count exceeds
 * {@link SIMPLE_SELECT_SEARCH_THRESHOLD}, and always renders an empty state.
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
  triggerSize = 'default',
  searchable,
  searchPlaceholder,
  noOptionsLabel,
  noMatchLabel,
}: SimpleSelectProps) {
  const t = useT()
  // Computed unconditionally to keep hook order stable across the search/plain branches below.
  const items = React.useMemo(
    () => Object.fromEntries(options.map((option) => [option.value, option.label])),
    [options]
  )
  const searchText = searchPlaceholder ?? t('select.searchPlaceholder')
  const noOptionsText = noOptionsLabel ?? t('select.noOptions')
  const noMatchText = noMatchLabel ?? t('select.noMatch')
  const searchOn = searchable ?? options.length > SIMPLE_SELECT_SEARCH_THRESHOLD

  if (searchOn) {
    const selected = options.find((option) => option.value === value) ?? null
    return (
      <Combobox
        disabled={disabled}
        items={options}
        onValueChange={(next: SimpleSelectOption | null) => onValueChange?.(next?.value ?? '')}
        value={selected}
      >
        <ComboboxTrigger
          aria-label={triggerAriaLabel}
          className={cn(TRIGGER_CLASS, triggerClassName)}
          data-size={triggerSize}
          id={triggerId}
        >
          <span
            className={cn('line-clamp-1 flex-1 text-left', !selected && 'text-muted-foreground')}
            title={selected?.label}
          >
            {selected?.label ?? placeholder}
          </span>
        </ComboboxTrigger>
        <ComboboxContent>
          <ComboboxInput placeholder={searchText} showTrigger={false} />
          <ComboboxList>
            {(option: SimpleSelectOption) => (
              <ComboboxItem key={option.value} value={option}>
                {option.label}
              </ComboboxItem>
            )}
          </ComboboxList>
          <ComboboxEmpty>{noMatchText}</ComboboxEmpty>
        </ComboboxContent>
      </Combobox>
    )
  }

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
        {options.length === 0 ? (
          <div className="px-2 py-6 text-center text-muted-foreground text-sm" data-slot="select-empty">
            {noOptionsText}
          </div>
        ) : (
          options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))
        )}
      </SelectContent>
    </Select>
  )
}
