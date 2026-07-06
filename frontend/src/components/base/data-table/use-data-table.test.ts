import type { ColumnDef } from '@tanstack/react-table'
import { act, renderHook } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { useDataTable } from './use-data-table'

interface Row {
  id: string
  name: string
  age: number
}

const DATA: Row[] = [
  { id: '1', name: 'Bob', age: 30 },
  { id: '2', name: 'Ann', age: 25 },
]

const COLUMNS: ColumnDef<Row, unknown>[] = [
  { accessorKey: 'name', header: 'Name' },
  { accessorKey: 'age', header: 'Age' },
]

describe('useDataTable', () => {
  it('manages pagination internally when uncontrolled', () => {
    const { result } = renderHook(() => useDataTable<Row>({ columns: COLUMNS, data: DATA, initialPageSize: 1 }))
    expect(result.current.getState().pagination).toEqual({ pageIndex: 0, pageSize: 1 })
    act(() => result.current.nextPage())
    expect(result.current.getState().pagination.pageIndex).toBe(1)
  })

  it('routes sorting to onSortingChange and keeps state external when controlled', () => {
    const onSortingChange = vi.fn()
    const { result } = renderHook(() =>
      useDataTable<Row>({ columns: COLUMNS, data: DATA, sorting: [], onSortingChange })
    )
    act(() => result.current.getColumn('name')?.toggleSorting())
    expect(onSortingChange).toHaveBeenCalledTimes(1)
    expect(result.current.getState().sorting).toEqual([])
  })

  it('does not reorder rows in memory when manualSorting is set', () => {
    const { result } = renderHook(() =>
      useDataTable<Row>({
        columns: COLUMNS,
        data: DATA,
        manualSorting: true,
        sorting: [{ id: 'name', desc: false }],
      })
    )
    const names = result.current.getRowModel().rows.map((row) => row.original.name)
    expect(names).toEqual(['Bob', 'Ann'])
  })

  it('warns when manualPagination is enabled without rowCount', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    renderHook(() => useDataTable<Row>({ columns: COLUMNS, data: DATA, manualPagination: true }))
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})
