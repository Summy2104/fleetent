import type { ColumnDef } from '@tanstack/react-table'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { DataTablePagination } from './data-table-pagination'
import { useDataTable } from './use-data-table'

interface Row {
  id: string
  name: string
}

const DATA: Row[] = Array.from({ length: 5 }, (_, index) => ({
  id: String(index),
  name: `Row ${index}`,
}))
const COLUMNS: ColumnDef<Row, unknown>[] = [{ accessorKey: 'name', header: 'Name' }]

function Harness() {
  const table = useDataTable<Row>({ columns: COLUMNS, data: DATA, initialPageSize: 2 })
  return (
    <div>
      <DataTablePagination pageSizeOptions={[2, 4]} table={table} />
      <span data-testid="page">{table.getState().pagination.pageIndex}</span>
    </div>
  )
}

describe('DataTablePagination', () => {
  it('disables previous on first page and advances with next', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.getByRole('button', { name: 'Go to previous page' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Go to next page' }))
    expect(screen.getByTestId('page')).toHaveTextContent('1')
  })

  it('resets to first page when page size changes', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.click(screen.getByRole('button', { name: 'Go to next page' }))
    expect(screen.getByTestId('page')).toHaveTextContent('1')
    // base-ui Select trigger renders as role="combobox", not role="button"
    await user.click(screen.getByRole('combobox', { name: 'Rows per page' }))
    await user.click(await screen.findByRole('option', { name: '4' }))
    expect(screen.getByTestId('page')).toHaveTextContent('0')
  })
})
