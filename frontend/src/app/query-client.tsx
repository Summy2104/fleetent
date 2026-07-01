import { type ReactNode, useState } from 'react'
import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'

import { ApiError, describeApiError } from '@/lib/api-client'
import { toast } from '@/lib/toast'

export function AppQueryProvider({ children }: { children: ReactNode }): JSX.Element {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
          },
        },
        // Global feedback for every mutation (create/update/delete/toggle…),
        // so individual call sites don't each need their own toast wiring.
        mutationCache: new MutationCache({
          onError: (error, _vars, _ctx, mutation) => {
            // Mutations that own their own feedback opt out of the global toast.
            if (mutation.meta?.silent) {
              return
            }
            // 401 is handled by the auth layer (redirect to login); don't double-toast.
            if (error instanceof ApiError && error.status === 401) {
              return
            }
            toast.error('Action failed', describeApiError(error))
          },
          onSuccess: (_data, _vars, _ctx, mutation) => {
            if (mutation.meta?.silent) {
              return
            }
            toast.success('Done')
          },
        }),
      })
  )

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
