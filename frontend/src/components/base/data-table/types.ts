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
  toolbar?: React.ReactNode // 外部自定义筛选区（左侧，与列筛选并列）
  actions?: React.ReactNode // 专用功能按钮插槽（toolbar 右侧，如「新增」/导出）；所有独立操作按钮统一放此处
  getRowId?: (row: TData) => string
  className?: string
}
