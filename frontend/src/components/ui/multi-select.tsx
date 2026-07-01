import { useEffect, useMemo, useRef, useState } from 'react'
import { Check, ChevronDown, X } from 'lucide-react'

import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

export type MultiSelectOption = { value: string; label: string }

export function MultiSelect({
  options,
  selected,
  onToggle,
  placeholder,
  searchPlaceholder,
  noMatchLabel,
  removeLabel,
  triggerLabel,
  disabled = false,
  className,
}: {
  options: MultiSelectOption[]
  selected: string[]
  onToggle: (value: string, enabled: boolean) => void
  placeholder: string
  searchPlaceholder: string
  noMatchLabel: string
  removeLabel: (label: string) => string
  triggerLabel: string
  disabled?: boolean
  className?: string
}): JSX.Element {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  // Dismiss the panel when focus/pointer leaves the widget, like a native combobox.
  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent): void {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  // Reset the search box every time the panel reopens so a stale filter never hides options.
  useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  const selectedSet = useMemo(() => new Set(selected), [selected])
  const labelOf = useMemo(() => {
    const map = new Map(options.map((option) => [option.value, option.label]))
    return (value: string) => map.get(value) ?? value
  }, [options])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return options
    return options.filter((option) => option.label.toLowerCase().includes(needle))
  }, [options, query])

  const toggle = (value: string): void => {
    onToggle(value, !selectedSet.has(value))
  }

  return (
    <div
      className={cn('relative', className)}
      onKeyDown={(event) => {
        if (event.key === 'Escape') setOpen(false)
      }}
      ref={containerRef}
    >
      <div
        aria-disabled={disabled}
        aria-expanded={open}
        aria-label={triggerLabel}
        className={cn(
          'flex min-h-8 w-full cursor-pointer flex-wrap items-center gap-1.5 rounded-md border border-input bg-background/60 px-2 py-1 text-sm shadow-sm',
          'focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring',
          disabled && 'pointer-events-none opacity-50'
        )}
        onClick={() => {
          if (!disabled) setOpen((value) => !value)
        }}
        onKeyDown={(event) => {
          if (disabled) return
          if (event.key === 'Enter' || event.key === ' ' || event.key === 'ArrowDown') {
            event.preventDefault()
            setOpen(true)
          }
        }}
        role="combobox"
        tabIndex={disabled ? -1 : 0}
      >
        {selected.length === 0 ? (
          <span className="px-1 text-muted-foreground">{placeholder}</span>
        ) : (
          selected.map((value) => (
            <span
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-secondary/60 py-0.5 pr-1 pl-2.5 text-sm"
              key={value}
            >
              {labelOf(value)}
              {!disabled ? (
                <button
                  aria-label={removeLabel(labelOf(value))}
                  className="grid size-4 place-items-center rounded-full text-muted-foreground hover:bg-destructive/15 hover:text-destructive"
                  onClick={(event) => {
                    event.stopPropagation()
                    onToggle(value, false)
                  }}
                  type="button"
                >
                  <X className="size-3" />
                </button>
              ) : null}
            </span>
          ))
        )}
        <ChevronDown className="ml-auto size-4 shrink-0 opacity-60" />
      </div>

      {open ? (
        <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover text-popover-foreground shadow-soft data-[state=open]:animate-fade-in">
          <div className="p-1">
            <Input
              autoFocus
              className="h-8"
              onChange={(event) => setQuery(event.target.value)}
              placeholder={searchPlaceholder}
              value={query}
            />
          </div>
          <div aria-multiselectable className="max-h-60 overflow-auto p-1 pt-0" role="listbox">
            {filtered.length === 0 ? (
              <div className="px-2 py-1.5 text-muted-foreground text-sm">{noMatchLabel}</div>
            ) : (
              filtered.map((option) => {
                const isSelected = selectedSet.has(option.value)
                return (
                  <div
                    aria-selected={isSelected}
                    className={cn(
                      'relative flex cursor-pointer select-none items-center gap-2 rounded-sm py-1.5 pr-2 pl-8 text-sm outline-none',
                      'hover:bg-accent hover:text-accent-foreground focus-visible:bg-accent focus-visible:text-accent-foreground'
                    )}
                    key={option.value}
                    onClick={() => toggle(option.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        toggle(option.value)
                      }
                    }}
                    role="option"
                    tabIndex={0}
                  >
                    <span className="absolute left-2 flex size-3.5 items-center justify-center">
                      {isSelected ? <Check className="size-4 text-primary" /> : null}
                    </span>
                    {option.label}
                  </div>
                )
              })
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
