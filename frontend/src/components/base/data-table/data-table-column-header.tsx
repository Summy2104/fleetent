import type { Column } from '@tanstack/react-table'
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface DataTableColumnHeaderProps<TData, TValue> {
  column: Column<TData, TValue>
  title: string
  className?: string
}

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <div className={cn('font-medium', className)}>{title}</div>
  }

  const sorted = column.getIsSorted()

  return (
    <Button
      aria-label={`Sort by ${title}`}
      className={cn('-ml-2.5 h-8', className)}
      onClick={column.getToggleSortingHandler()}
      size="sm"
      variant="ghost"
    >
      <span>{title}</span>
      {sorted === 'asc' ? (
        <ArrowUp data-icon="inline-end" />
      ) : sorted === 'desc' ? (
        <ArrowDown data-icon="inline-end" />
      ) : (
        <ChevronsUpDown className="text-muted-foreground/60" data-icon="inline-end" />
      )}
    </Button>
  )
}
