import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useAuthSession } from '@/app/auth'
import { parseResponse, useAdminApi } from '@/lib/api-client'

export type KnowledgeBase = {
  archived: boolean
  bound_agents: number[]
  chunk_count: number
  description: string
  doc_count: number
  kb_id: string
  last_import: string | null
  tenant_id: string
}

export type CreateKbInput = {
  description: string
  kb_id: string
  tenant_id?: string
}

export type UpdateKbInput = {
  description: string
}

export type DeleteKbInput = {
  tenant_id?: string
}

export type KnowledgeDocument = {
  chunks: number
  created_at: string
  document_id: string
  filename: string
  source: string
  source_url: string | null
}

export type DocumentChunk = {
  chunk_id: string
  content: string
  document_id: string
  filename: string
  kb_id: string
  position: number | null
  score: number | null
  section: string
  section_path: string
  source: string
  source_url: string | null
}

export type DeleteDocumentInput = {
  document_id?: string
  tenant_id?: string
}

export type KbAgentsResult = {
  agents: number[]
  kb_id: string
}

export type BindAgentInput = {
  agent_id: number
  tenant_id?: string
}

export type SearchKbInput = {
  kb_id: string
  query: string
  tenant_id?: string
  top_k?: number
}

export type SearchKbResult = {
  kb_ids: string[]
  mode: string
  query: string
  results: DocumentChunk[]
}

export type UploadDocumentInput = {
  file: File
}

export type UploadDocumentResult = {
  job_id: string
}

const kbListKey = ['kb'] as const

function kbDocumentsKey(kbId: string) {
  return ['kb', kbId, 'documents'] as const
}

function kbAgentsKey(kbId: string) {
  return ['kb', kbId, 'agents'] as const
}

function kbDocumentChunksKey(kbId: string, documentId: string) {
  return ['kb', kbId, 'documents', documentId, 'chunks'] as const
}

function invalidateKbDetailQueries(queryClient: ReturnType<typeof useQueryClient>, kbId: string) {
  return Promise.all([
    queryClient.invalidateQueries({ queryKey: kbListKey }),
    queryClient.invalidateQueries({ queryKey: kbDocumentsKey(kbId) }),
    queryClient.invalidateQueries({ queryKey: kbAgentsKey(kbId) }),
  ])
}

export function useKbsQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: kbListKey,
    queryFn: () => api.get<KnowledgeBase[]>('/admin/kb'),
  })
}

export function useCreateKbMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateKbInput) => api.post<CreateKbInput>('/admin/kb', input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey })
    },
  })
}

export function useUpdateKbMutation(kbId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: UpdateKbInput) => api.patch<UpdateKbInput>(`/admin/kb/${kbId}`, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey })
    },
  })
}

export function useDeleteKbMutation(kbId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input?: DeleteKbInput) => {
      const search = new URLSearchParams()
      if (input?.tenant_id) {
        search.set('tenant_id', input.tenant_id)
      }
      const suffix = search.toString() ? `?${search.toString()}` : ''
      return api.delete<{ archived: boolean; kb_id: string }>(`/admin/kb/${kbId}${suffix}`, {
        'X-Confirm': 'true',
      })
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbListKey })
      queryClient.removeQueries({ queryKey: kbDocumentsKey(kbId) })
      queryClient.removeQueries({ queryKey: kbAgentsKey(kbId) })
    },
  })
}

export function useDocumentsQuery(kbId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(kbId),
    queryKey: kbId ? kbDocumentsKey(kbId) : ['kb', 'documents', 'idle'],
    queryFn: () => api.get<KnowledgeDocument[]>(`/admin/kb/${kbId}/documents`),
  })
}

export function useDocumentChunksQuery(kbId: string | null, documentId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(kbId && documentId),
    queryKey:
      kbId && documentId ? kbDocumentChunksKey(kbId, documentId) : ['kb', 'documents', 'chunks', 'idle'],
    queryFn: () => api.get<DocumentChunk[]>(`/admin/kb/${kbId}/documents/${documentId}/chunks`),
  })
}

export function useDeleteDocumentMutation(kbId: string, defaultDocumentId?: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input?: DeleteDocumentInput) => {
      const documentId = input?.document_id ?? defaultDocumentId
      if (!documentId) {
        throw new Error('document_id is required')
      }
      const search = new URLSearchParams()
      if (input?.tenant_id) {
        search.set('tenant_id', input.tenant_id)
      }
      const suffix = search.toString() ? `?${search.toString()}` : ''
      return api.delete<{ deleted: boolean; document_id: string; kb_id: string }>(
        `/admin/kb/${kbId}/documents/${documentId}${suffix}`,
        { 'X-Confirm': 'true' }
      )
    },
    onSuccess: async () => {
      await invalidateKbDetailQueries(queryClient, kbId)
    },
  })
}

export function useKbAgentsQuery(kbId: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(kbId),
    queryKey: kbId ? kbAgentsKey(kbId) : ['kb', 'agents', 'idle'],
    queryFn: () => api.get<KbAgentsResult>(`/admin/kb/${kbId}/agents`),
  })
}

export function useBindAgentMutation(kbId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: BindAgentInput) => api.post(`/admin/kb/${kbId}/agents`, input),
    onSuccess: async () => {
      await invalidateKbDetailQueries(queryClient, kbId)
    },
  })
}

export function useUnbindAgentMutation(kbId: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: BindAgentInput) => {
      const search = new URLSearchParams()
      if (input.tenant_id) {
        search.set('tenant_id', input.tenant_id)
      }
      const suffix = search.toString() ? `?${search.toString()}` : ''
      return api.delete(`/admin/kb/${kbId}/agents/${input.agent_id}${suffix}`)
    },
    onSuccess: async () => {
      await invalidateKbDetailQueries(queryClient, kbId)
    },
  })
}

export function useSearchKbMutation() {
  const api = useAdminApi()

  return useMutation({
    mutationFn: ({ kb_id, query, tenant_id = 'default', top_k }: SearchKbInput) =>
      api.post<SearchKbResult>('/admin/kb/search', {
        kb_ids: [kb_id],
        query,
        tenant_id,
        ...(top_k !== undefined ? { top_k } : {}),
      }),
  })
}

export function useUploadDocumentMutation(kbId: string) {
  const auth = useAuthSession()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ file }: UploadDocumentInput) => {
      const form = new FormData()
      const blob = new Blob([await file.arrayBuffer()], { type: file.type || 'application/octet-stream' })
      form.set('file', blob, file.name)

      const headers = new Headers()
      if (auth.token) {
        headers.set('authorization', `Session ${auth.token}`)
      }

      const response = await fetch(`${auth.baseUrl}/admin/kb/${kbId}/documents`, {
        body: form,
        headers,
        method: 'POST',
      })

      if (response.status === 401) {
        auth.clearToken()
      }

      return parseResponse<UploadDocumentResult>(response)
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: kbDocumentsKey(kbId) })
    },
  })
}
