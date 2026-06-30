import * as React from 'react'
import type { Table } from '@tanstack/react-table'
import { Search, X } from 'lucide-react'

import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { MultiSelect } from '@/components/ui/multi-select'
import { DataTableViewOptions } from './data-table-view-options'

interface DataTableToolbarProps<TData> {
  table: Table<TData>
  enableGlobalFilter?: boolean
  enableColumnVisibility?: boolean
  children?: React.ReactNode
  actions?: React.ReactNode
}

export function DataTableToolbar<TData>({
  table,
  enableGlobalFilter,
  enableColumnVisibility,
  children,
  actions,
}: DataTableToolbarProps<TData>) {
  const isFiltered = table.getState().columnFilters.length > 0 || Boolean(table.getState().globalFilter)
  const hasRightCluster = enableColumnVisibility || Boolean(actions)

  return (
    <div className="flex flex-wrap items-center gap-2">
      {enableGlobalFilter ? <GlobalSearch table={table} /> : null}
      <ColumnFilters table={table} />
      {isFiltered ? (
        <Button
          aria-label="Reset filters"
          className="h-8 px-2 lg:px-3"
          onClick={() => {
            table.resetColumnFilters()
            table.setGlobalFilter('')
          }}
          variant="ghost"
        >
          Reset
          <X className="size-4" />
        </Button>
      ) : null}
      {children}
      {hasRightCluster ? (
        <div className="ml-auto flex items-center gap-2">
          {enableColumnVisibility ? <DataTableViewOptions table={table} /> : null}
          {actions}
        </div>
      ) : null}
    </div>
  )
}

function GlobalSearch<TData>({ table }: { table: Table<TData> }) {
  const external = (table.getState().globalFilter as string) ?? ''
  const [value, setValue] = React.useState(external)

  // 外部重置/切换时把本地输入同步回来。
  React.useEffect(() => {
    setValue(external)
  }, [external])

  // 防抖 300ms 再写入表格状态。
  React.useEffect(() => {
    const handle = setTimeout(() => {
      if (value !== external) table.setGlobalFilter(value)
    }, 300)
    return () => clearTimeout(handle)
  }, [value, external, table])

  return (
    <div className="relative">
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input
        aria-label="Search"
        className="h-8 w-[200px] pl-8"
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search…"
        value={value}
      />
    </div>
  )
}

function ColumnFilters<TData>({ table }: { table: Table<TData> }) {
  const columns = table.getAllColumns().filter((column) => column.getCanFilter() && column.columnDef.meta?.filter)

  return (
    <>
      {columns.map((column) => {
        const config = column.columnDef.meta?.filter
        if (!config) return null
        const title = column.columnDef.meta?.title ?? column.id

        if (config.type === 'text') {
          return (
            <Input
              aria-label={`Filter ${title}`}
              className="h-8 w-[160px]"
              key={column.id}
              onChange={(event) => column.setFilterValue(event.target.value || undefined)}
              placeholder={config.placeholder ?? title}
              value={(column.getFilterValue() as string) ?? ''}
            />
          )
        }

        if (config.type === 'select') {
          return (
            <SimpleSelect
              key={column.id}
              onValueChange={(value) => column.setFilterValue(value || undefined)}
              options={[{ label: `All ${title}`, value: '' }, ...config.options]}
              triggerAriaLabel={`Filter ${title}`}
              triggerClassName="h-8 w-[160px]"
              value={(column.getFilterValue() as string) ?? ''}
            />
          )
        }

        const selected = (column.getFilterValue() as string[]) ?? []
        return (
          <MultiSelect
            className="w-[200px]"
            key={column.id}
            noMatchLabel="No matches"
            onToggle={(value, enabled) => {
              const next = enabled ? [...selected, value] : selected.filter((item) => item !== value)
              column.setFilterValue(next.length ? next : undefined)
            }}
            options={config.options}
            placeholder={title}
            removeLabel={(label) => `Remove ${label}`}
            searchPlaceholder={`Search ${title}`}
            selected={selected}
            triggerLabel={`Filter ${title}`}
          />
        )
      })}
    </>
  )
}
