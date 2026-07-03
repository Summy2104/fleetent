import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SIMPLE_SELECT_SEARCH_THRESHOLD, SimpleSelect, type SimpleSelectOption } from '@/components/base/simple-select'
import { I18nProvider } from '@/i18n'

function makeOptions(count: number): SimpleSelectOption[] {
  return Array.from({ length: count }, (_, index) => ({ value: `v${index}`, label: `Option ${index}` }))
}

function Harness({
  options,
  initial = '',
  searchable,
  onValueChange,
}: {
  options: SimpleSelectOption[]
  initial?: string
  searchable?: boolean
  onValueChange?: (value: string) => void
}): JSX.Element {
  const [value, setValue] = useState(initial)
  return (
    <I18nProvider>
      <SimpleSelect
        noMatchLabel="No results found"
        noOptionsLabel="No options available"
        onValueChange={(next) => {
          onValueChange?.(next)
          setValue(next)
        }}
        options={options}
        placeholder="Choose"
        searchable={searchable}
        searchPlaceholder="Search options"
        triggerAriaLabel="Picker"
        value={value}
      />
    </I18nProvider>
  )
}

// The plain <Select> trigger exposes role=combobox; the searchable <Combobox> trigger is a button.
async function openTrigger(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  const trigger = screen.queryByRole('combobox', { name: 'Picker' }) ?? screen.getByRole('button', { name: 'Picker' })
  await user.click(trigger)
}

describe('SimpleSelect', () => {
  it('shows the empty-state message when there are no options', async () => {
    const user = userEvent.setup()
    render(<Harness options={[]} />)

    await openTrigger(user)

    expect(await screen.findByText('No options available')).toBeInTheDocument()
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
  })

  it('stays a plain dropdown (no search box) at or below the threshold', async () => {
    const user = userEvent.setup()
    render(<Harness options={makeOptions(SIMPLE_SELECT_SEARCH_THRESHOLD)} />)

    await openTrigger(user)

    expect(await screen.findByRole('option', { name: 'Option 0' })).toBeInTheDocument()
    expect(screen.queryByPlaceholderText('Search options')).not.toBeInTheDocument()
  })

  it('adds a search box automatically once options exceed the threshold', async () => {
    const user = userEvent.setup()
    render(<Harness options={makeOptions(SIMPLE_SELECT_SEARCH_THRESHOLD + 1)} />)

    await openTrigger(user)

    expect(await screen.findByPlaceholderText('Search options')).toBeInTheDocument()
  })

  it('filters options by a case-insensitive substring in search mode', async () => {
    const user = userEvent.setup()
    render(<Harness options={makeOptions(SIMPLE_SELECT_SEARCH_THRESHOLD + 1)} />)

    await openTrigger(user)
    await user.type(await screen.findByPlaceholderText('Search options'), 'option 1')

    expect(await screen.findByRole('option', { name: 'Option 1' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'Option 2' })).not.toBeInTheDocument()
  })

  it('shows the no-match message when the search matches nothing', async () => {
    const user = userEvent.setup()
    render(<Harness options={makeOptions(SIMPLE_SELECT_SEARCH_THRESHOLD + 1)} />)

    await openTrigger(user)
    await user.type(await screen.findByPlaceholderText('Search options'), 'zzzz')

    expect(await screen.findByText('No results found')).toBeInTheDocument()
    expect(screen.queryByRole('option')).not.toBeInTheDocument()
  })

  it('reports the selected value in search mode', async () => {
    const user = userEvent.setup()
    const onValueChange = vi.fn()
    render(<Harness onValueChange={onValueChange} options={makeOptions(SIMPLE_SELECT_SEARCH_THRESHOLD + 1)} />)

    await openTrigger(user)
    await user.click(await screen.findByRole('option', { name: 'Option 3' }))

    expect(onValueChange).toHaveBeenCalledWith('v3')
  })

  it('reports the selected value in plain mode', async () => {
    const user = userEvent.setup()
    const onValueChange = vi.fn()
    render(<Harness onValueChange={onValueChange} options={makeOptions(3)} />)

    await openTrigger(user)
    await user.click(await screen.findByRole('option', { name: 'Option 2' }))

    expect(onValueChange).toHaveBeenCalledWith('v2')
  })
})
