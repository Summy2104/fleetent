import type { ColumnDef } from '@tanstack/react-table'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { DataTableViewOptions } from './data-table-view-options'
import { useDataTable } from './use-data-table'

interface Row {
  id: string
  name: string
  age: number
}

const DATA: Row[] = [{ id: '1', name: 'Bob', age: 30 }]
const COLUMNS: ColumnDef<Row, unknown>[] = [
  { accessorKey: 'name', header: 'Name', meta: { title: 'Name' } },
  { accessorKey: 'age', header: 'Age', meta: { title: 'Age' } },
]

function Harness() {
  const table = useDataTable<Row>({ columns: COLUMNS, data: DATA })
  return (
    <div>
      <DataTableViewOptions table={table} />
      <span data-testid="age-visible">{String(table.getColumn('age')?.getIsVisible())}</span>
    </div>
  )
}

describe('DataTableViewOptions', () => {
  it('toggles column visibility from the menu', async () => {
    const user = userEvent.setup()
    render(<Harness />)
    expect(screen.getByTestId('age-visible')).toHaveTextContent('true')
    await user.click(screen.getByRole('button', { name: 'Columns' }))
    await user.click(await screen.findByRole('menuitemcheckbox', { name: 'Age' }))
    expect(screen.getByTestId('age-visible')).toHaveTextContent('false')
  })
})
