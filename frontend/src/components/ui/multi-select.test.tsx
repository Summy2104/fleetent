import { useState } from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { MultiSelect, type MultiSelectOption } from '@/components/ui/multi-select';

const OPTIONS: MultiSelectOption[] = [
  { value: 'getting-started', label: 'getting-started' },
  { value: 'pdf-tools', label: 'pdf-tools' },
  { value: 'web-search', label: 'web-search' },
];

// A stateful wrapper so toggling actually re-renders selection, mirroring real usage.
function Harness({
  initial = [],
  onToggle,
  disabled = false,
}: {
  initial?: string[];
  onToggle?: (value: string, enabled: boolean) => void;
  disabled?: boolean;
}): JSX.Element {
  const [selected, setSelected] = useState<string[]>(initial);
  return (
    <MultiSelect
      options={OPTIONS}
      selected={selected}
      disabled={disabled}
      placeholder="Select skills"
      searchPlaceholder="Search skills"
      noMatchLabel="No matching skills"
      triggerLabel="Skills"
      removeLabel={(name) => `Remove ${name}`}
      onToggle={(value, enabled) => {
        onToggle?.(value, enabled);
        setSelected((prev) => (enabled ? [...prev, value] : prev.filter((v) => v !== value)));
      }}
    />
  );
}

function trigger(): HTMLElement {
  return screen.getByRole('combobox', { name: 'Skills' });
}

describe('MultiSelect', () => {
  it('shows the placeholder and lists every option once opened', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    expect(screen.getByText('Select skills')).toBeInTheDocument();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    await user.click(trigger());
    expect(screen.getByRole('option', { name: 'getting-started' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'pdf-tools' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'web-search' })).toBeInTheDocument();
  });

  it('filters options by a case-insensitive substring search', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(trigger());
    await user.type(screen.getByPlaceholderText('Search skills'), 'PDF');

    expect(screen.getByRole('option', { name: 'pdf-tools' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'getting-started' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'web-search' })).not.toBeInTheDocument();
  });

  it('shows the no-match label when nothing matches the search', async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(trigger());
    await user.type(screen.getByPlaceholderText('Search skills'), 'zzz');

    expect(screen.getByText('No matching skills')).toBeInTheDocument();
    expect(screen.queryByRole('option')).not.toBeInTheDocument();
  });

  it('toggles an option on, keeps the panel open, and reflects it as a chip', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<Harness onToggle={onToggle} />);

    await user.click(trigger());
    await user.click(screen.getByRole('option', { name: 'pdf-tools' }));

    expect(onToggle).toHaveBeenCalledWith('pdf-tools', true);
    expect(screen.getByRole('option', { name: 'pdf-tools' })).toHaveAttribute('aria-selected', 'true');
    // multi-select: the panel stays open so more options can be picked
    expect(screen.getByRole('option', { name: 'web-search' })).toBeInTheDocument();
    // selection surfaces as a chip inside the trigger
    expect(within(trigger()).getByText('pdf-tools')).toBeInTheDocument();
  });

  it('toggles an already-selected option off from the list', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<Harness initial={['pdf-tools']} onToggle={onToggle} />);

    await user.click(trigger());
    await user.click(screen.getByRole('option', { name: 'pdf-tools' }));

    expect(onToggle).toHaveBeenCalledWith('pdf-tools', false);
    expect(screen.getByRole('option', { name: 'pdf-tools' })).toHaveAttribute('aria-selected', 'false');
  });

  it('removes a selection via its chip without opening the panel', async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    render(<Harness initial={['pdf-tools']} onToggle={onToggle} />);

    expect(within(trigger()).getByText('pdf-tools')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Remove pdf-tools' }));

    expect(onToggle).toHaveBeenCalledWith('pdf-tools', false);
    expect(within(trigger()).queryByText('pdf-tools')).not.toBeInTheDocument();
    expect(screen.getByText('Select skills')).toBeInTheDocument();
    // the chip remove must not toggle the dropdown open
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes on Escape and on an outside click', async () => {
    const user = userEvent.setup();
    render(
      <>
        <Harness />
        <button type="button">outside</button>
      </>
    );

    await user.click(trigger());
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();

    await user.click(trigger());
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'outside' }));
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
  });

  it('does not open when disabled', async () => {
    const user = userEvent.setup();
    render(<Harness disabled />);

    await user.click(trigger());
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});
