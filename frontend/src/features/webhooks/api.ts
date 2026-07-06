import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type WebhookSourceRecord = {
  agent_id: number | null
  enabled: boolean
  has_secret: boolean
  id: string
  message_template: string | null
  reply_target: string | null
  user_id: string
}

export type WebhookSourceInput = {
  agent_id: number
  enabled: boolean
  id: string
  message_template: string | null
  reply_target: string | null
  secret: string | null
  user_id: string
}

/** How an edit treats the stored secret: keep as-is, overwrite, or drop it. */
export type WebhookSecretAction = 'keep' | 'set' | 'clear'

export type WebhookSourceUpdateInput = {
  agent_id: number
  enabled: boolean
  message_template: string | null
  reply_target: string | null
  secret_action: WebhookSecretAction
  // Present only when secret_action === 'set'.
  secret?: string
  user_id: string
}

const WEBHOOK_SOURCES_QUERY_KEY = ['webhooks', 'sources']

export function useWebhookSourcesQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: WEBHOOK_SOURCES_QUERY_KEY,
    queryFn: () => api.get<WebhookSourceRecord[]>('/admin/webhooks/sources'),
  })
}

export function useCreateWebhookSourceMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: WebhookSourceInput) => api.post<WebhookSourceRecord>('/admin/webhooks/sources', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: WEBHOOK_SOURCES_QUERY_KEY })
    },
  })
}

export function useUpdateWebhookSourceMutation(sourceId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: WebhookSourceUpdateInput) =>
      api.put<WebhookSourceRecord>(`/admin/webhooks/sources/${sourceId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: WEBHOOK_SOURCES_QUERY_KEY })
    },
  })
}

export function useDeleteWebhookSourceMutation(sourceId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.delete<void>(`/admin/webhooks/sources/${sourceId}`),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: WEBHOOK_SOURCES_QUERY_KEY })
    },
  })
}
