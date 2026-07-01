import * as React from 'react'
import { type ColumnDef, flexRender, type Row } from '@tanstack/react-table'

import { Badge } from '@/components/base/badge'
import { Card } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from '@/components/ui/empty'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { cn } from '@/lib/utils'
import { DataTablePagination } from './data-table-pagination'
import { DataTableToolbar } from './data-table-toolbar'
import { DataTableViewOptions } from './data-table-view-options'
import type { DataTableProps } from './types'
import { useDataTable } from './use-data-table'

/**
 * Custom filter for multi-select faceted filters. Coerces cell values via `String(...)`,
 * so a `null`/`undefined` cell becomes `"null"`/`"undefined"` — a row with a missing value
 * only matches an option whose value is literally that string.
 */
function multiSelectFilterFn<TData>(row: Row<TData>, columnId: string, value: unknown): boolean {
  if (!Array.isArray(value) || value.length === 0) return true
  return value.includes(String(row.getValue(columnId)))
}

function selectionColumn<TData>(): ColumnDef<TData, unknown> {
  return {
    id: '__select__',
    enableSorting: false,
    enableHiding: false,
    header: ({ table }) => (
      <Checkbox
        aria-label="Select all"
        checked={table.getIsAllPageRowsSelected()}
        indeterminate={table.getIsSomePageRowsSelected() && !table.getIsAllPageRowsSelected()}
        onCheckedChange={(checked) => table.toggleAllPageRowsSelected(checked)}
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        aria-label="Select row"
        checked={row.getIsSelected()}
        onCheckedChange={(checked) => row.toggleSelected(checked)}
      />
    ),
  }
}

function useTableColumns<TData>(
  columns: ColumnDef<TData, unknown>[],
  enableRowSelection: boolean
): ColumnDef<TData, unknown>[] {
  return React.useMemo(() => {
    const withFilterFns = columns.map((column) => {
      const filter = column.meta?.filter
      if (!filter || column.filterFn) return column
      if (filter.type === 'select') return { ...column, filterFn: 'equalsString' as const }
      if (filter.type === 'multi-select') return { ...column, filterFn: multiSelectFilterFn }
      return { ...column, filterFn: 'includesString' as const }
    })
    return enableRowSelection ? [selectionColumn<TData>(), ...withFilterFns] : withFilterFns
  }, [columns, enableRowSelection])
}

function hasColumnFilters<TData>(columns: ColumnDef<TData, unknown>[]): boolean {
  return columns.some((column) => Boolean(column.meta?.filter))
}

/**
 * Generic data table built on TanStack Table. Pass a **stable (memoized) `columns` reference** —
 * a new array literal each render causes TanStack Table to rebuild its column model on every render.
 */
export function DataTable<TData>(props: DataTableProps<TData>) {
  const {
    columns,
    data,
    enableGlobalFilter = false,
    enableRowSelection = false,
    enableColumnVisibility = false,
    pageSizeOptions = [10, 20, 50],
    isLoading = false,
    emptyState,
    title,
    toolbar,
    actions,
    className,
    ...rest
  } = props

  const tableColumns = useTableColumns(columns, enableRowSelection)

  const table = useDataTable<TData>({
    columns: tableColumns,
    data,
    enableRowSelection,
    initialPageSize: pageSizeOptions[0],
    ...rest,
  })

  // 筛选卡：有可筛选项时才渲染。表头带：有列显隐或 actions 时才渲染。
  const hasFilters = enableGlobalFilter || hasColumnFilters(columns) || Boolean(toolbar)
  const hasHeaderBand = title != null || enableColumnVisibility || Boolean(actions)
  const columnCount = table.getVisibleLeafColumns().length
  const rowCount = table.getCoreRowModel().rows.length

  return (
    <div className={cn('space-y-3', className)}>
      {hasFilters ? (
        <Card className="px-4 py-3">
          <DataTableToolbar enableGlobalFilter={enableGlobalFilter} table={table}>
            {toolbar}
          </DataTableToolbar>
        </Card>
      ) : null}
      <Card className="gap-0 divide-y py-0">
        {hasHeaderBand ? (
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
            <div className="flex items-center gap-2 font-medium text-base">
              {title}
              {title != null ? <Badge variant="secondary">{rowCount}</Badge> : null}
            </div>
            <div className="flex items-center gap-2">
              {actions}
              {enableColumnVisibility ? <DataTableViewOptions table={table} /> : null}
            </div>
          </div>
        ) : null}
        <div className="overflow-x-auto">
          <Table>
            <TableHeader className="bg-muted/50">
              {table.getHeaderGroups().map((headerGroup) => (
                <TableRow key={headerGroup.id}>
                  {headerGroup.headers.map((header) => (
                    <TableHead key={header.id}>
                      {header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}
                    </TableHead>
                  ))}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <SkeletonRows columns={columnCount} rows={table.getState().pagination.pageSize} />
              ) : table.getRowModel().rows.length ? (
                table.getRowModel().rows.map((row) => (
                  <TableRow data-state={row.getIsSelected() ? 'selected' : undefined} key={row.id}>
                    {row.getVisibleCells().map((cell) => (
                      <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>
                    ))}
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell className="h-32 p-0" colSpan={columnCount}>
                    {emptyState ?? <DefaultEmpty />}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        <div className="px-4 py-2.5">
          <DataTablePagination pageSizeOptions={pageSizeOptions} table={table} />
        </div>
      </Card>
    </div>
  )
}

function SkeletonRows({ rows, columns }: { rows: number; columns: number }) {
  return (
    <>
      {Array.from({ length: rows }).map((_, rowIndex) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder rows have no stable id
        <TableRow key={`skeleton-row-${rowIndex}`}>
          {Array.from({ length: columns }).map((_, cellIndex) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: static placeholder cells have no stable id
            <TableCell key={`skeleton-cell-${rowIndex}-${cellIndex}`}>
              <Skeleton className="h-4 w-full" />
            </TableCell>
          ))}
        </TableRow>
      ))}
    </>
  )
}

function DefaultEmpty() {
  return (
    <Empty className="border-0">
      <EmptyHeader>
        <EmptyTitle>No data</EmptyTitle>
        <EmptyDescription>There are no records to display.</EmptyDescription>
      </EmptyHeader>
    </Empty>
  )
}
