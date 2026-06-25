import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';

import { ApiError, describeApiError } from '@/lib/api-client';
import { toast } from '@/lib/toast';

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
          onError: (error) => {
            // 401 is handled by the auth layer (redirect to login); don't double-toast.
            if (error instanceof ApiError && error.status === 401) {
              return;
            }
            toast.error('Action failed', describeApiError(error));
          },
          onSuccess: () => {
            toast.success('Done');
          },
        }),
      })
  );

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
