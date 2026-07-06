import type { ColumnDef } from '@tanstack/react-table'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { DataTableColumnHeader } from './data-table-column-header'
import { useDataTable } from './use-data-table'

interface Row {
  id: string
  name: string
}

const DATA: Row[] = [
  { id: '1', name: 'Bob' },
  { id: '2', name: 'Ann' },
]
const COLUMNS: ColumnDef<Row, unknown>[] = [{ accessorKey: 'name', header: 'Name' }]

function Harness() {
  const table = useDataTable<Row>({ columns: COLUMNS, data: DATA })
  const column = table.getColumn('name')
  if (!column) throw new Error('column missing')
  return (
    <div>
      <DataTableColumnHeader column={column} title="Name" />
      <span data-testid="sorted">{String(column.getIsSorted())}</span>
    </div>
  )
}

describe('DataTableColumnHeader', () => {
  it('cycles asc -> desc -> none on click', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    const button = screen.getByRole('button', { name: 'Sort by Name' })
    expect(screen.getByTestId('sorted')).toHaveTextContent('false')
    await user.click(button)
    expect(screen.getByTestId('sorted')).toHaveTextContent('asc')
    await user.click(button)
    expect(screen.getByTestId('sorted')).toHaveTextContent('desc')
    await user.click(button)
    expect(screen.getByTestId('sorted')).toHaveTextContent('false')
  })
})
