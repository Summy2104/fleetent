import type { ColumnDef } from '@tanstack/react-table'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { DataTableToolbar } from './data-table-toolbar'
import { useDataTable } from './use-data-table'

interface Row {
  id: string
  name: string
  role: string
}

const DATA: Row[] = [
  { id: '1', name: 'Bob', role: 'admin' },
  { id: '2', name: 'Ann', role: 'user' },
]
const COLUMNS: ColumnDef<Row, unknown>[] = [
  { accessorKey: 'name', header: 'Name', meta: { title: 'Name' } },
  {
    accessorKey: 'role',
    header: 'Role',
    filterFn: 'equalsString',
    meta: {
      title: 'Role',
      filter: {
        type: 'select',
        options: [
          { label: 'Admin', value: 'admin' },
          { label: 'User', value: 'user' },
        ],
      },
    },
  },
]

function Harness() {
  const table = useDataTable<Row>({ columns: COLUMNS, data: DATA })
  return (
    <div>
      <DataTableToolbar enableColumnVisibility enableGlobalFilter table={table}>
        <span>external-slot</span>
      </DataTableToolbar>
      <span data-testid="global">{table.getState().globalFilter}</span>
      <span data-testid="filters">{JSON.stringify(table.getState().columnFilters)}</span>
    </div>
  )
}

describe('DataTableToolbar', () => {
  it('debounces global search into table state', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    await user.type(screen.getByRole('textbox', { name: 'Search' }), 'Bob')
    await waitFor(() => expect(screen.getByTestId('global')).toHaveTextContent('Bob'))
  })

  it('renders the external slot', () => {
    render(<Harness />)
    expect(screen.getByText('external-slot')).toBeInTheDocument()
  })

  it('applies a select column filter', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    // SimpleSelect uses base-ui Select which renders role="combobox" on the trigger, not role="button"
    await user.click(screen.getByRole('combobox', { name: 'Filter Role' }))
    await user.click(await screen.findByRole('option', { name: 'Admin' }))
    await waitFor(() => expect(screen.getByTestId('filters')).toHaveTextContent('"id":"role","value":"admin"'))
  })

  it('shows Reset only when filtered and clears all filters on click', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.queryByRole('button', { name: 'Reset filters' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('combobox', { name: 'Filter Role' }))
    await user.click(await screen.findByRole('option', { name: 'Admin' }))
    await waitFor(() => expect(screen.getByTestId('filters')).toHaveTextContent('"value":"admin"'))

    await user.click(screen.getByRole('button', { name: 'Reset filters' }))
    await waitFor(() => expect(screen.getByTestId('filters')).toHaveTextContent('[]'))
  })
})
