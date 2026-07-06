import type { Table } from '@tanstack/react-table'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'

import { SimpleSelect } from '@/components/base/simple-select'
import { Button } from '@/components/ui/button'

interface DataTablePaginationProps<TData> {
  table: Table<TData>
  pageSizeOptions?: number[]
}

export function DataTablePagination<TData>({ table, pageSizeOptions = [10, 20, 50] }: DataTablePaginationProps<TData>) {
  const { pageIndex, pageSize } = table.getState().pagination
  const pageCount = table.getPageCount()

  return (
    <div className="flex items-center justify-between gap-4 px-1 py-1">
      <div className="flex items-center gap-2 text-muted-foreground text-sm">
        <span className="hidden sm:inline">Rows per page</span>
        <SimpleSelect
          onValueChange={(value) => table.setPagination({ pageIndex: 0, pageSize: Number(value) })}
          options={pageSizeOptions.map((size) => ({ label: String(size), value: String(size) }))}
          triggerAriaLabel="Rows per page"
          triggerClassName="h-8 w-[72px]"
          value={String(pageSize)}
        />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground text-sm">
          Page {pageIndex + 1} of {Math.max(pageCount, 1)}
        </span>
        <Button
          aria-label="Go to first page"
          disabled={!table.getCanPreviousPage()}
          onClick={() => table.setPageIndex(0)}
          size="icon-sm"
          variant="outline"
        >
          <ChevronsLeft />
        </Button>
        <Button
          aria-label="Go to previous page"
          disabled={!table.getCanPreviousPage()}
          onClick={() => table.previousPage()}
          size="icon-sm"
          variant="outline"
        >
          <ChevronLeft />
        </Button>
        <Button
          aria-label="Go to next page"
          disabled={!table.getCanNextPage()}
          onClick={() => table.nextPage()}
          size="icon-sm"
          variant="outline"
        >
          <ChevronRight />
        </Button>
        <Button
          aria-label="Go to last page"
          disabled={!table.getCanNextPage()}
          onClick={() => table.setPageIndex(pageCount - 1)}
          size="icon-sm"
          variant="outline"
        >
          <ChevronsRight />
        </Button>
      </div>
    </div>
  )
}
