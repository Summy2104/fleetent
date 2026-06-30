import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { useAdminApi } from '@/lib/api-client'

export type SkillListItem = {
  audit_verdict: string
  description: string
  drifted_agents: string[]
  enabling_agents: string[]
  global_enabled: boolean
  name: string
  source: string
  status: string
}

export type SkillContent = {
  content: string
  name: string
}

export type SkillAgentBinding = {
  agent_id: number
  enabled: boolean
  name?: string
}

export type SkillVersion = {
  author: string
  message: string
  sha: string
  timestamp: string
}

export type SkillDiff = {
  diff: string
  files?: string[]
  truncated?: boolean
}

export type SkillProposal = {
  has_diff: boolean
  id: string
  reason: string
  risk_level: string
  target_skill: string
  type: string
}

type SkillLifecycleAction = 'delete' | 'disable' | 'enable' | 'restore'
type BindingInput = {
  enabled: boolean
}
type CreateSkillInput = {
  content: string
  name: string
  source?: string
}
type EditSkillInput = {
  content: string
}

function invalidateSkillList(queryClient: ReturnType<typeof useQueryClient>): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: ['skills'] })
}

export function useSkillsQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['skills'],
    queryFn: () => api.get<SkillListItem[]>('/admin/skills?include_archived=true'),
  })
}

export function useSkillContentQuery(name: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(name),
    queryKey: ['skill-content', name],
    queryFn: () => api.get<SkillContent>(`/admin/skills/${name}/content`),
  })
}

export function useSkillAgentBindingsQuery(name: string | null) {
  const api = useAdminApi()

  return useQuery({
    enabled: Boolean(name),
    queryKey: ['skill-agents', name],
    queryFn: () => api.get<SkillAgentBinding[]>(`/admin/skills/${name}/agents`),
  })
}

export function useSkillVersionsQuery(name: string | null, enabled: boolean) {
  const api = useAdminApi()

  return useQuery({
    enabled: enabled && Boolean(name),
    queryKey: ['skill-versions', name],
    queryFn: () => api.get<SkillVersion[]>(`/admin/skills/${name}/versions`),
  })
}

export function useSkillDiffQuery(name: string | null, ref: string | null, enabled: boolean) {
  const api = useAdminApi()

  return useQuery({
    enabled: enabled && Boolean(name) && Boolean(ref),
    queryKey: ['skill-diff', name, ref],
    queryFn: () => api.get<SkillDiff>(`/admin/skills/${name}/versions/${ref}/diff`),
  })
}

export function useSkillProposalsQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['skill-proposals'],
    queryFn: () => api.get<SkillProposal[]>('/admin/skills/proposals'),
  })
}

export function useSkillProposalDiffQuery(proposalId: string | null, enabled: boolean) {
  const api = useAdminApi()

  return useQuery({
    enabled: enabled && Boolean(proposalId),
    queryKey: ['skill-proposal-diff', proposalId],
    queryFn: () => api.get<SkillDiff>(`/admin/skills/proposals/${proposalId}/diff`),
  })
}

export function useCreateSkillMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: CreateSkillInput) => api.post('/admin/skills', { source: 'adhoc', ...input }),
    onSuccess: async () => {
      await invalidateSkillList(queryClient)
    },
  })
}

export function useEditSkillMutation(name: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: EditSkillInput) => api.put(`/admin/skills/${name}`, input),
    onSuccess: async () => {
      await Promise.all([
        invalidateSkillList(queryClient),
        queryClient.invalidateQueries({ queryKey: ['skill-content', name] }),
        queryClient.invalidateQueries({ queryKey: ['skill-versions', name] }),
      ])
    },
  })
}

export function useSkillLifecycleMutation(name: string, action: SkillLifecycleAction) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => {
      if (action === 'delete') {
        return api.delete(`/admin/skills/${name}`, { 'X-Confirm': 'true' })
      }
      return api.post(`/admin/skills/${name}/${action}`)
    },
    onSuccess: async () => {
      await Promise.all([
        invalidateSkillList(queryClient),
        queryClient.invalidateQueries({ queryKey: ['skill-content', name] }),
      ])
    },
  })
}

export function useForcePublishSkillMutation(name: string) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.post(`/admin/skills/${name}/force-publish`, undefined, { 'X-Confirm': 'true' }),
    onSuccess: async () => {
      await invalidateSkillList(queryClient)
    },
  })
}

export function useReloadSkillsMutation() {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.post('/admin/skills/reload'),
    onSuccess: async () => {
      await invalidateSkillList(queryClient)
    },
  })
}

export function useSetSkillAgentBindingMutation(name: string, agentId: number) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (body: BindingInput) => api.put(`/admin/skills/${name}/agents/${agentId}`, body),
    onSuccess: async () => {
      await Promise.all([
        invalidateSkillList(queryClient),
        queryClient.invalidateQueries({ queryKey: ['skill-agents', name] }),
      ])
    },
  })
}

// --- skill backflow (platform governance) -----------------------------------

export type BackflowProposal = {
  agent_id: number
  agent_name: string | null
  base_commit: string | null
  base_version: string | null
  conflict: number
  created_at: string
  forked_as: string | null
  id: number
  skill_name: string
  status: string
}

export type BackflowDiff = {
  conflict: boolean
  diff_vs_base: string
  diff_vs_head: string
}

type BackflowAcceptInput = {
  confirm?: boolean
}
type BackflowForkInput = {
  fork_name: string
}

function invalidateBackflow(queryClient: ReturnType<typeof useQueryClient>): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: ['backflow-proposals'] })
}

export function useBackflowProposalsQuery() {
  const api = useAdminApi()

  return useQuery({
    queryKey: ['backflow-proposals'],
    queryFn: () => api.get<BackflowProposal[]>('/admin/skills/backflow'),
  })
}

export function useBackflowDiffQuery(proposalId: number | null, enabled: boolean) {
  const api = useAdminApi()

  return useQuery({
    enabled: enabled && proposalId !== null,
    queryKey: ['backflow-diff', proposalId],
    queryFn: () => api.get<BackflowDiff>(`/admin/skills/backflow/${proposalId}/diff`),
  })
}

export function useBackflowAcceptMutation(proposalId: number) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input?: BackflowAcceptInput) =>
      api.post(
        `/admin/skills/backflow/${proposalId}/accept`,
        undefined,
        input?.confirm ? { 'X-Confirm': 'true' } : undefined
      ),
    onSuccess: async () => {
      await invalidateBackflow(queryClient)
    },
  })
}

export function useBackflowRejectMutation(proposalId: number) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: () => api.post(`/admin/skills/backflow/${proposalId}/reject`),
    onSuccess: async () => {
      await invalidateBackflow(queryClient)
    },
  })
}

export function useBackflowForkMutation(proposalId: number) {
  const api = useAdminApi()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (input: BackflowForkInput) => api.post(`/admin/skills/backflow/${proposalId}/fork`, input),
    onSuccess: async () => {
      await invalidateBackflow(queryClient)
    },
  })
}
