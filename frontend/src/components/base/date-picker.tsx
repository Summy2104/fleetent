import * as React from 'react'
import { CalendarIcon, X } from 'lucide-react'

import { Calendar } from '@/components/ui/calendar'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { cn } from '@/lib/utils'

/** A single date (`yyyy-MM-dd`) with an optional `HH:mm` time; both optional. */
export interface DateFieldValue {
  date?: string
  time?: string
}

/**
 * Two independently-selected {@link DateFieldValue} ends. Not a linked range —
 * start and end are each chosen on their own and are individually optional ("选填").
 */
export interface DateRangeValue {
  from?: string
  to?: string
  fromTime?: string
  toTime?: string
}

/** Inclusive ISO bounds derived from a {@link DateRangeValue}, ready for a server query. */
export interface DateRangeBounds {
  since?: string
  until?: string
}

/**
 * Expand the two ends to inclusive ISO bounds. A missing start time defaults to
 * the beginning of the day; a missing end time defaults to the last millisecond.
 * A provided end time is treated as minute-inclusive.
 */
export function dateRangeBounds(value: DateRangeValue | undefined): DateRangeBounds {
  const bounds: DateRangeBounds = {}
  if (value?.from) {
    bounds.since = `${value.from}T${value.fromTime ? `${value.fromTime}:00` : '00:00:00'}`
  }
  if (value?.to) {
    bounds.until = `${value.to}T${value.toTime ? `${value.toTime}:59.999` : '23:59:59.999'}`
  }
  return bounds
}

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

function formatLabel(value: DateFieldValue | undefined): string | null {
  if (!value?.date && !value?.time) return null
  if (value.date && value.time) return `${value.date} ${value.time}`
  return value.date ?? value.time ?? null
}

export interface DatePickerProps {
  value?: DateFieldValue
  onChange: (value: DateFieldValue | undefined) => void
  placeholder?: string
  triggerAriaLabel?: string
  triggerClassName?: string
  clearLabel?: string
  timeLabel?: string
}

/**
 * Popover-anchored single-date picker with an optional time. Emits a date-only
 * (`yyyy-MM-dd`) string plus an optional `HH:mm`, so the value survives
 * serialization into column-filter state and server queries.
 */
export function DatePicker({
  value,
  onChange,
  placeholder = 'Pick a date',
  triggerAriaLabel,
  triggerClassName,
  clearLabel = 'Clear date',
  timeLabel = 'Time',
}: DatePickerProps): JSX.Element {
  const [open, setOpen] = React.useState(false)
  const label = formatLabel(value)
  const timeInputId = `${(triggerAriaLabel ?? 'date').replace(/\s+/g, '-').toLowerCase()}-time`

  const emit = (next: DateFieldValue): void => {
    onChange(next.date || next.time ? next : undefined)
  }

  const handleSelect = (date: Date | undefined): void => {
    emit({ ...value, date: date ? toIsoDate(date) : undefined })
  }

  const handleTime = (event: React.ChangeEvent<HTMLInputElement>): void => {
    emit({ ...value, time: event.target.value || undefined })
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
          'flex h-8 w-[170px] items-center gap-2 rounded-md border border-input bg-background px-3 text-sm shadow-sm',
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
          defaultMonth={fromIsoDate(value?.date)}
          mode="single"
          onSelect={handleSelect}
          selected={fromIsoDate(value?.date)}
        />
        <div className="grid gap-1.5 border-t p-3">
          <Label className="text-muted-foreground text-xs" htmlFor={timeInputId}>
            {timeLabel}
          </Label>
          <Input className="h-8" id={timeInputId} onChange={handleTime} type="time" value={value?.time ?? ''} />
        </div>
      </PopoverContent>
    </Popover>
  )
}
