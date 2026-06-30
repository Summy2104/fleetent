import type * as React from 'react'
import type {
  ColumnDef,
  ColumnFiltersState,
  OnChangeFn,
  PaginationState,
  RowData,
  RowSelectionState,
  SortingState,
} from '@tanstack/react-table'

export interface ColumnFilterOption {
  label: string
  value: string
}

export type ColumnFilterConfig =
  | { type: 'text'; placeholder?: string }
  | { type: 'select'; options: ColumnFilterOption[] }
  | { type: 'multi-select'; options: ColumnFilterOption[] }

declare module '@tanstack/react-table' {
  // biome-ignore lint/correctness/noUnusedVariables: module augmentation must mirror the original generic arity
  interface ColumnMeta<TData extends RowData, TValue> {
    filter?: ColumnFilterConfig
    title?: string
    align?: 'left' | 'right' | 'center'
  }
}

export interface DataTableProps<TData> {
  columns: ColumnDef<TData, unknown>[]
  data: TData[]

  // 模式开关：缺省即前端模式；任一打开即对应维度走后端
  manualPagination?: boolean
  manualSorting?: boolean
  manualFiltering?: boolean
  rowCount?: number

  // 受控 state（全部可选；不传则内部自管）
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

  // 功能开关
  enableGlobalFilter?: boolean
  enableRowSelection?: boolean
  enableColumnVisibility?: boolean
  enableSortingRemoval?: boolean
  pageSizeOptions?: number[]

  // 状态与插槽
  isLoading?: boolean
  emptyState?: React.ReactNode
  toolbar?: React.ReactNode
  getRowId?: (row: TData) => string
  className?: string
}
