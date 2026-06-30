import type { ColumnDef } from '@tanstack/react-table'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { DataTable } from './data-table'

interface Row {
  id: string
  name: string
}

const DATA: Row[] = Array.from({ length: 3 }, (_, index) => ({
  id: String(index),
  name: `Row ${index}`,
}))
const COLUMNS: ColumnDef<Row, unknown>[] = [{ accessorKey: 'name', header: 'Name', meta: { title: 'Name' } }]

describe('DataTable', () => {
  it('renders rows from data', () => {
    render(<DataTable columns={COLUMNS} data={DATA} getRowId={(row) => row.id} />)
    expect(screen.getByText('Row 0')).toBeInTheDocument()
    expect(screen.getByText('Row 2')).toBeInTheDocument()
  })

  it('shows the empty state when there is no data', () => {
    render(<DataTable columns={COLUMNS} data={[]} />)
    expect(screen.getByText('No data')).toBeInTheDocument()
  })

  it('shows skeleton rows while loading', () => {
    const { container } = render(<DataTable columns={COLUMNS} data={[]} isLoading />)
    expect(container.querySelectorAll('[data-slot="skeleton"]').length).toBeGreaterThan(0)
  })

  it('injects a selection column and toggles row selection', async () => {
    const user = userEvent.setup()
    render(<DataTable columns={COLUMNS} data={DATA} enableRowSelection getRowId={(row) => row.id} />)
    const rowCheckboxes = screen.getAllByRole('checkbox', { name: 'Select row' })
    expect(rowCheckboxes).toHaveLength(3)
    await user.click(rowCheckboxes[0])
    await waitFor(() => expect(rowCheckboxes[0]).toBeChecked())
  })

  it('filters rows via the global search box', async () => {
    const user = userEvent.setup()
    render(<DataTable columns={COLUMNS} data={DATA} enableGlobalFilter getRowId={(row) => row.id} />)
    await user.type(screen.getByRole('textbox', { name: 'Search' }), 'Row 1')
    await waitFor(() => expect(screen.queryByText('Row 0')).not.toBeInTheDocument())
    expect(screen.getByText('Row 1')).toBeInTheDocument()
  })

  it('sorts rows when a sortable header is clicked', async () => {
    const user = userEvent.setup()
    const data: Row[] = [
      { id: 'a', name: 'Charlie' },
      { id: 'b', name: 'Alice' },
    ]
    const columns: ColumnDef<Row, unknown>[] = [
      {
        accessorKey: 'name',
        header: ({ column }) => (
          <button onClick={column.getToggleSortingHandler()} type="button">
            Name
          </button>
        ),
      },
    ]
    render(<DataTable columns={columns} data={data} getRowId={(row) => row.id} />)
    const firstCellBefore = screen.getAllByRole('cell')[0]
    expect(firstCellBefore).toHaveTextContent('Charlie')
    await user.click(screen.getByRole('button', { name: 'Name' }))
    await waitFor(() => expect(screen.getAllByRole('cell')[0]).toHaveTextContent('Alice'))
  })
})
