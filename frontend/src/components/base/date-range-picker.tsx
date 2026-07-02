import * as React from 'react'
import { CalendarIcon, X } from 'lucide-react'
import type { DateRange } from 'react-day-picker'

import type { DateRangeValue } from '@/components/base/date-picker'
import { Calendar } from '@/components/ui/calendar'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

// The range value shape and bounds helper are shared with the two-picker layout
// used in production; re-export them for standalone consumers of this component.
export { type DateRangeBounds, type DateRangeValue, dateRangeBounds } from '@/components/base/date-picker'

function toIsoDate(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function fromIsoDate(value: string | undefined): Date | undefined {
  if (!value) return undefined
  const [year, month, day] = value.split('-').map(Number)
  if (!year || !month || !day) return undefined
  return new Date(year, month - 1, day)
}

function formatEnd(date: string | undefined, time: string | undefined): string | undefined {
  if (!date) return undefined
  return time ? `${date} ${time}` : date
}

function formatLabel(value: DateRangeValue | undefined): string | null {
  const from = formatEnd(value?.from, value?.fromTime)
  const to = formatEnd(value?.to, value?.toTime)
  if (!from && !to) return null
  if (from && to) return `${from} → ${to}`
  return from ?? `→ ${to}`
}

export interface DateRangePickerProps {
  value?: DateRangeValue
  onChange: (value: DateRangeValue | undefined) => void
  placeholder?: string
  triggerAriaLabel?: string
  triggerClassName?: string
  clearLabel?: string
  startTimeLabel?: string
  endTimeLabel?: string
}

/**
 * Popover-anchored range calendar with two optional per-end time pickers.
 *
 * Preserved for reuse but not currently wired into any table — the audit filter
 * uses two independent {@link DatePicker}s instead. Bounds are computed via the
 * shared {@link dateRangeBounds}, so both layouts produce identical queries.
 */
export function DateRangePicker({
  value,
  onChange,
  placeholder = 'Pick a date range',
  triggerAriaLabel,
  triggerClassName,
  clearLabel = 'Clear date range',
  startTimeLabel = 'Start time',
  endTimeLabel = 'End time',
}: DateRangePickerProps): JSX.Element {
  const [open, setOpen] = React.useState(false)
  const label = formatLabel(value)
  const selected: DateRange | undefined = value?.from
    ? { from: fromIsoDate(value.from), to: fromIsoDate(value.to) }
    : undefined

  const emit = (next: DateRangeValue): void => {
    const hasAny = next.from || next.to || next.fromTime || next.toTime
    onChange(hasAny ? next : undefined)
  }

  const handleSelect = (range: DateRange | undefined): void => {
    emit({
      ...value,
      from: range?.from ? toIsoDate(range.from) : undefined,
      to: range?.to ? toIsoDate(range.to) : undefined,
    })
  }

  const handleTime = (key: 'fromTime' | 'toTime') => (event: React.ChangeEvent<HTMLInputElement>) => {
    emit({ ...value, [key]: event.target.value || undefined })
  }

  const clear = (event: React.MouseEvent): void => {
    event.stopPropagation()
    onChange(undefined)
  }

  return (
    <Popover onOpenChange={setOpen} open={open}>
      <PopoverTrigger
        aria-label={triggerAriaLabel}
        className={cn(
          'flex h-8 w-[240px] items-center gap-2 rounded-md border border-input bg-background px-3 text-sm shadow-sm',
          'hover:bg-accent hover:text-accent-foreground focus:outline-none focus:ring-1 focus:ring-ring',
          !label && 'text-muted-foreground',
          triggerClassName
        )}
        type="button"
      >
        <CalendarIcon className="size-4 shrink-0 opacity-60" />
        <span className="truncate">{label ?? placeholder}</span>
        {label ? (
          // biome-ignore lint/a11y/useSemanticElements: a nested <button> inside the trigger is invalid HTML.
          <span
            aria-label={clearLabel}
            className="ml-auto grid size-4 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
            onClick={clear}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') clear(event as unknown as React.MouseEvent)
            }}
            role="button"
            tabIndex={0}
          >
            <X className="size-3" />
          </span>
        ) : null}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0">
        <Calendar
          autoFocus
          defaultMonth={fromIsoDate(value?.from)}
          mode="range"
          numberOfMonths={2}
          onSelect={handleSelect}
          selected={selected}
        />
        <div className="grid grid-cols-2 gap-3 border-t p-3">
          <div className="grid gap-1.5">
            <Label className="text-muted-foreground text-xs" htmlFor="date-range-from-time">
              {startTimeLabel}
            </Label>
            <Input
              className="h-8"
              id="date-range-from-time"
              onChange={handleTime('fromTime')}
              type="time"
              value={value?.fromTime ?? ''}
            />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-muted-foreground text-xs" htmlFor="date-range-to-time">
              {endTimeLabel}
            </Label>
            <Input
              className="h-8"
              id="date-range-to-time"
              onChange={handleTime('toTime')}
              type="time"
              value={value?.toTime ?? ''}
            />
          </div>
        </div>
      </PopoverContent>
    </Popover>
  )
}
