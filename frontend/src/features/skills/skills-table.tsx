import type * as React from 'react'
import { useMemo, useState } from 'react'

import { DataTable } from '@/components/base/data-table'
import {
  type BackflowProposal,
  type SkillProposal,
  useBackflowDiffQuery,
  useBackflowProposalsQuery,
  useSkillGitStatusQuery,
  useSkillProposalsQuery,
  useSkillsQuery,
} from '@/features/skills/api'
import { buildSkillColumns } from '@/features/skills/columns/skill-columns'
import {
  BackflowDialog,
  BackflowWorklist,
  BindingsDialog,
  ContentDialog,
  ProposalDiffDialog,
  ProposalsDialog,
  VersionsDialog,
} from '@/features/skills/dialogs/skill-dialogs'
import { useT } from '@/i18n'

export function SkillsTable({
  canWrite,
  actions,
  title,
  gitopsEnabled = false,
}: {
  canWrite: boolean
  actions?: React.ReactNode
  title?: React.ReactNode
  gitopsEnabled?: boolean
}): JSX.Element {
  const t = useT()
  const skills = useSkillsQuery()
  const proposals = useSkillProposalsQuery()
  const backflow = useBackflowProposalsQuery()
  const gitStatus = useSkillGitStatusQuery()

  const [contentFor, setContentFor] = useState<string | null>(null)
  const [versionsFor, setVersionsFor] = useState<string | null>(null)
  const [bindingsFor, setBindingsFor] = useState<string | null>(null)
  const [proposalsFor, setProposalsFor] = useState<string | null>(null)
  const [proposalDiffId, setProposalDiffId] = useState<string | null>(null)
  const [backflowFor, setBackflowFor] = useState<string | null>(null)
  const [selectedBackflowId, setSelectedBackflowId] = useState<number | null>(null)

  const backflowDiff = useBackflowDiffQuery(selectedBackflowId, selectedBackflowId !== null)

  const proposalsBySkill = useMemo(() => {
    const map = new Map<string, SkillProposal[]>()
    ;(proposals.data ?? []).forEach((proposal) => {
      const list = map.get(proposal.target_skill) ?? []
      list.push(proposal)
      map.set(proposal.target_skill, list)
    })
    return map
  }, [proposals.data])

  const backflowBySkill = useMemo(() => {
    const map = new Map<string, BackflowProposal[]>()
    ;(backflow.data ?? []).forEach((proposal) => {
      const list = map.get(proposal.skill_name) ?? []
      list.push(proposal)
      map.set(proposal.skill_name, list)
    })
    return map
  }, [backflow.data])

  const columns = useMemo(
    () =>
      buildSkillColumns({
        backflowCountFor: (name) => backflowBySkill.get(name)?.length ?? 0,
        canWrite,
        gitopsEnabled,
        onBackflow: setBackflowFor,
        onBindings: setBindingsFor,
        onProposals: setProposalsFor,
        onVersions: setVersionsFor,
        onViewContent: setContentFor,
        proposalCountFor: (name) => proposalsBySkill.get(name)?.length ?? 0,
        t,
      }),
    [canWrite, gitopsEnabled, t, proposalsBySkill, backflowBySkill]
  )

  return (
    <>
      {gitopsEnabled ? <BackflowWorklist gitStatus={gitStatus.data} proposals={backflow.data ?? []} /> : null}
      <DataTable
        actions={actions}
        columns={columns}
        data={skills.data ?? []}
        emptyState={<div className="py-12 text-center text-muted-foreground text-sm">{t('skills.empty')}</div>}
        enableColumnVisibility
        enableGlobalFilter
        getRowId={(row) => row.name}
        isLoading={skills.isPending}
        title={title}
      />

      <ContentDialog onOpenChange={(open) => !open && setContentFor(null)} skillName={contentFor} />
      <VersionsDialog onOpenChange={(open) => !open && setVersionsFor(null)} skillName={versionsFor} />
      <BindingsDialog
        canWrite={canWrite}
        onOpenChange={(open) => !open && setBindingsFor(null)}
        skillName={bindingsFor}
      />
      <ProposalsDialog
        onDiff={(id) => setProposalDiffId(id)}
        onOpenChange={(open) => !open && setProposalsFor(null)}
        proposals={proposalsFor ? (proposalsBySkill.get(proposalsFor) ?? []) : []}
        skillName={proposalsFor}
      />
      <ProposalDiffDialog onOpenChange={(open) => !open && setProposalDiffId(null)} proposalId={proposalDiffId} />
      <BackflowDialog
        diff={backflowDiff.data ?? null}
        diffLoading={selectedBackflowId !== null && backflowDiff.isPending}
        gitopsEnabled={gitopsEnabled}
        onOpenChange={(open) => {
          if (!open) {
            setBackflowFor(null)
            setSelectedBackflowId(null)
          }
        }}
        onViewDiff={setSelectedBackflowId}
        proposals={backflowFor ? (backflowBySkill.get(backflowFor) ?? []) : []}
        skillName={backflowFor}
      />
    </>
  )
}
