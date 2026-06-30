import * as React from 'react'
import {
  type ColumnDef,
  type ColumnFiltersState,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  type OnChangeFn,
  type PaginationState,
  type RowSelectionState,
  type SortingState,
  type Table,
  useReactTable,
} from '@tanstack/react-table'

export interface UseDataTableOptions<TData> {
  columns: ColumnDef<TData, unknown>[]
  data: TData[]
  manualPagination?: boolean
  manualSorting?: boolean
  manualFiltering?: boolean
  rowCount?: number
  pagination?: PaginationState
  onPaginationChange?: OnChangeFn<PaginationState>
  sorting?: SortingState
  onSortingChange?: OnChangeFn<SortingState>
  columnFilters?: ColumnFiltersState
  onColumnFiltersChange?: OnChangeFn<ColumnFiltersState>
  globalFilter?: string
  onGlobalFilterChange?: OnChangeFn<string>
  rowSelection?: RowSelectionState
  onRowSelectionChange?: OnChangeFn<RowSelectionState>
  enableRowSelection?: boolean
  enableSortingRemoval?: boolean
  initialPageSize?: number
  getRowId?: (row: TData) => string
}

// 受控/非受控统一：传了 controlled 即受控并只回调 onChange；否则内部 useState。
function useControllableState<T>(
  controlled: T | undefined,
  onChange: OnChangeFn<T> | undefined,
  defaultValue: T
): [T, OnChangeFn<T>] {
  const [uncontrolled, setUncontrolled] = React.useState<T>(defaultValue)
  const isControlled = controlled !== undefined
  const value = isControlled ? (controlled as T) : uncontrolled

  const setValue = React.useCallback<OnChangeFn<T>>(
    (updater) => {
      const next = typeof updater === 'function' ? (updater as (old: T) => T)(value) : updater
      if (!isControlled) setUncontrolled(next)
      onChange?.(next)
    },
    [isControlled, onChange, value]
  )

  return [value, setValue]
}

export function useDataTable<TData>(options: UseDataTableOptions<TData>): Table<TData> {
  const {
    columns,
    data,
    manualPagination = false,
    manualSorting = false,
    manualFiltering = false,
    rowCount,
    enableRowSelection = false,
    enableSortingRemoval = true,
    initialPageSize = 10,
    getRowId,
  } = options

  const [pagination, setPagination] = useControllableState<PaginationState>(
    options.pagination,
    options.onPaginationChange,
    { pageIndex: 0, pageSize: initialPageSize }
  )
  const [sorting, setSorting] = useControllableState<SortingState>(options.sorting, options.onSortingChange, [])
  const [columnFilters, setColumnFilters] = useControllableState<ColumnFiltersState>(
    options.columnFilters,
    options.onColumnFiltersChange,
    []
  )
  const [globalFilter, setGlobalFilter] = useControllableState<string>(
    options.globalFilter,
    options.onGlobalFilterChange,
    ''
  )
  const [rowSelection, setRowSelection] = useControllableState<RowSelectionState>(
    options.rowSelection,
    options.onRowSelectionChange,
    {}
  )

  if (import.meta.env.DEV && manualPagination && rowCount === undefined) {
    console.warn(
      '[DataTable] manualPagination is enabled but rowCount was not provided; page count cannot be computed.'
    )
  }

  return useReactTable<TData>({
    data,
    columns,
    state: { pagination, sorting, columnFilters, globalFilter, rowSelection },
    manualPagination,
    manualSorting,
    manualFiltering,
    rowCount,
    enableRowSelection,
    enableSortingRemoval,
    getRowId,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: manualSorting ? undefined : getSortedRowModel(),
    getFilteredRowModel: manualFiltering ? undefined : getFilteredRowModel(),
    getPaginationRowModel: manualPagination ? undefined : getPaginationRowModel(),
  })
}
