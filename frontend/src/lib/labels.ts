/**
 * Render a bound entity as `Name (id)` for read-back display, falling back to the
 * bare id when no human-readable name is known.
 *
 * Used wherever an already-bound user / agent / tenant is echoed in a table cell
 * or detail view, so the readable name and the stable id stay visible together.
 * Selection controls keep name-only labels; this is display-side only.
 */
export function labelWithId(name: string | null | undefined, id: string): string {
  const trimmed = name?.trim()
  return trimmed ? `${trimmed} (${id})` : id
}
