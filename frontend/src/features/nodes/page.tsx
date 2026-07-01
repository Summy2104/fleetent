import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Clock, Copy, Pin, PinOff, Plus, Server, Tag, Trash2 } from 'lucide-react'

import { Badge } from '@/components/base/badge'
import { SimpleSelect } from '@/components/base/simple-select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import {
  type NodeAgentOption,
  useDeleteNodeMutation,
  useNodeAgentsQuery,
  useNodePlacementsQuery,
  useNodesQuery,
  usePinAgentMutation,
  useRegisterNodeMutation,
  useUnpinAgentMutation,
} from '@/features/nodes/api'
import { useT } from '@/i18n'
import { useAdminApi } from '@/lib/api-client'

type AdminMe = { email: string; id: string; role: string }

type PlacementView = {
  agent_id: number
  agent_name: string
}

function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

function parseLabels(value: string): Record<string, string> {
  return value
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
    .reduce<Record<string, string>>((acc, item) => {
      const [key, rawValue] = item.split('=')
      const trimmedKey = key?.trim()
      const trimmedValue = rawValue?.trim()
      if (trimmedKey && trimmedValue) {
        acc[trimmedKey] = trimmedValue
      }
      return acc
    }, {})
}

function formatLabels(labels: Record<string, string>): string[] {
  return Object.entries(labels).map(([key, value]) => `${key}=${value}`)
}

// ─────────────────────────── Register node dialog ───────────────────────────

function RegisterNodeDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}): JSX.Element {
  const t = useT()
  const registerNode = useRegisterNodeMutation()
  const [nodeId, setNodeId] = useState('')
  const [nodeName, setNodeName] = useState('')
  const [labels, setLabels] = useState('')
  const [serviceKey, setServiceKey] = useState<string | null>(null)

  const reset = (): void => {
    setNodeId('')
    setNodeName('')
    setLabels('')
  }

  const onRegister = async (): Promise<void> => {
    const result = await registerNode.mutateAsync({
      labels: parseLabels(labels),
      name: nodeName || undefined,
      node_id: nodeId,
    })
    setServiceKey(result.service_key_plaintext_once)
    reset()
  }

  const handleOpenChange = (next: boolean): void => {
    if (!next) {
      setServiceKey(null)
      reset()
    }
    onOpenChange(next)
  }

  return (
    <Dialog onOpenChange={handleOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('nodes.registerNode')}</DialogTitle>
          <DialogDescription>{t('nodes.registerNodeDescription')}</DialogDescription>
        </DialogHeader>

        {serviceKey ? (
          <div className="space-y-3 rounded-md border border-warning/40 bg-warning/10 p-4">
            <p className="font-medium text-foreground text-sm">{t('nodes.serviceKeyShownOnce')}</p>
            <code className="block max-h-40 overflow-y-auto break-all rounded-md border border-border bg-background/60 p-3 font-mono text-foreground text-xs">
              {serviceKey}
            </code>
            <p className="text-muted-foreground text-xs">{t('nodes.serviceKeyCopyHint')}</p>
            <div className="flex gap-2">
              <Button onClick={() => void navigator.clipboard?.writeText(serviceKey)} size="sm" variant="outline">
                <Copy className="size-4" /> {t('nodes.copyKey')}
              </Button>
              <Button onClick={() => handleOpenChange(false)} size="sm" variant="secondary">
                {t('nodes.done')}
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="grid gap-4">
              <div className="grid gap-2">
                <Label htmlFor="node-id">{t('nodes.nodeId')}</Label>
                <Input id="node-id" onChange={(event) => setNodeId(event.target.value)} value={nodeId} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-name">{t('nodes.nodeName')}</Label>
                <Input id="node-name" onChange={(event) => setNodeName(event.target.value)} value={nodeName} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="node-labels">{t('nodes.labels')}</Label>
                <Input
                  id="node-labels"
                  onChange={(event) => setLabels(event.target.value)}
                  placeholder="region=us, rack=r1"
                  value={labels}
                />
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => handleOpenChange(false)} variant="outline">
                {t('nodes.cancel')}
              </Button>
              <Button disabled={!nodeId || registerNode.isPending} onClick={() => void onRegister()}>
                {t('nodes.registerNode')}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Pin agent dialog ───────────────────────────

function PinAgentDialog({
  nodeId,
  open,
  onOpenChange,
  availableAgents,
}: {
  nodeId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  availableAgents: NodeAgentOption[]
}): JSX.Element {
  const t = useT()
  const pin = usePinAgentMutation(nodeId)
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>('')

  const onPin = async (): Promise<void> => {
    if (!selectedAgentId) return
    await pin.mutateAsync({ agent_id: Number(selectedAgentId) })
    setSelectedAgentId('')
    onOpenChange(false)
  }

  return (
    <Dialog
      onOpenChange={(next) => {
        if (!next) setSelectedAgentId('')
        onOpenChange(next)
      }}
      open={open}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('nodes.pinAgentTo', { nodeId })}</DialogTitle>
          <DialogDescription>{t('nodes.pinAgentDescription')}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2">
          <Label htmlFor={`pin-agent-${nodeId}`}>{t('nodes.agent')}</Label>
          <SimpleSelect
            onValueChange={setSelectedAgentId}
            options={availableAgents.map((agent) => ({ value: String(agent.agent_id), label: agent.agent_name }))}
            placeholder={t('nodes.selectAgent')}
            triggerAriaLabel={t('nodes.agent')}
            triggerId={`pin-agent-${nodeId}`}
            value={selectedAgentId}
          />
          {!availableAgents.length ? (
            <p className="text-muted-foreground text-sm">{t('nodes.allAgentsPinned')}</p>
          ) : null}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('nodes.cancel')}
          </Button>
          <Button disabled={!selectedAgentId || pin.isPending} onClick={() => void onPin()}>
            {t('nodes.pinAgent')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ─────────────────────────── Node card ───────────────────────────

function NodeCard({
  agentOptions,
  canWrite,
  nodeId,
  nodeName,
  labels,
  lastSeenAt,
  registeredAt,
}: {
  agentOptions: NodeAgentOption[]
  canWrite: boolean
  nodeId: string
  nodeName: string | null
  labels: Record<string, string>
  lastSeenAt: string | null
  registeredAt: string
}): JSX.Element {
  const t = useT()
  const remove = useDeleteNodeMutation(nodeId)
  const unpin = useUnpinAgentMutation(nodeId)
  const placementsQuery = useNodePlacementsQuery(nodeId)

  const [pinOpen, setPinOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  const placements: PlacementView[] = useMemo(
    () =>
      (placementsQuery.data ?? []).map((placement) => ({
        agent_id: placement.agent_id,
        agent_name: placement.agent_name ?? String(placement.agent_id),
      })),
    [placementsQuery.data]
  )

  const availableAgents = useMemo(
    () => agentOptions.filter((agent) => !placements.some((placement) => placement.agent_id === agent.agent_id)),
    [agentOptions, placements]
  )

  const labelsText = formatLabels(labels)

  return (
    <Card aria-label={`node ${nodeId}`} className="overflow-hidden">
      <CardHeader>
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-secondary text-muted-foreground">
              <Server className="size-5" />
            </span>
            <div className="min-w-0 space-y-1">
              <CardTitle className="truncate">{nodeName ?? nodeId}</CardTitle>
              <p className="truncate font-mono text-muted-foreground text-xs">{nodeId}</p>
            </div>
          </div>
          {canWrite ? (
            <Button
              aria-label={t('nodes.deleteNode', { nodeId })}
              onClick={() => setConfirmDelete(true)}
              size="icon"
              variant="ghost"
            >
              <Trash2 className="size-4" />
            </Button>
          ) : null}
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        <div className="flex flex-col gap-1.5 text-muted-foreground text-xs sm:flex-row sm:gap-6">
          <span className="inline-flex items-center gap-1.5">
            <Clock className="size-3.5" /> {t('nodes.registered', { date: registeredAt })}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <Clock className="size-3.5" /> {t('nodes.lastSeen', { date: lastSeenAt ?? t('nodes.neverReported') })}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Tag className="size-3.5 text-muted-foreground" />
          {labelsText.length > 0 ? (
            labelsText.map((label) => (
              <Badge key={label} variant="secondary">
                {label}
              </Badge>
            ))
          ) : (
            <span className="text-muted-foreground text-sm">{t('nodes.noLabels')}</span>
          )}
        </div>

        <Separator />

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-semibold text-foreground text-sm">{t('nodes.agentPlacement')}</h3>
            {canWrite ? (
              <Button onClick={() => setPinOpen(true)} size="sm" variant="outline">
                <Pin className="size-4" /> {t('nodes.pinAgentTo', { nodeId })}
              </Button>
            ) : null}
          </div>

          {placements.length > 0 ? (
            <div className="space-y-2">
              <p className="font-medium text-foreground text-sm">{t('nodes.pinnedAgents')}</p>
              {placements.map((placement) => (
                <div
                  className="flex items-center justify-between gap-3 rounded-md border border-border bg-secondary/40 px-3 py-2"
                  key={placement.agent_id}
                >
                  <span className="text-sm">{placement.agent_name}</span>
                  {canWrite ? (
                    <Button
                      aria-label={t('nodes.unpinFrom', { name: placement.agent_name, nodeId })}
                      onClick={() => void unpin.mutateAsync(placement.agent_id)}
                      size="sm"
                      variant="ghost"
                    >
                      <PinOff className="size-4" /> {t('nodes.unpin')}
                    </Button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">{t('nodes.noAgentsPinned')}</p>
          )}
        </section>
      </CardContent>

      {canWrite ? (
        <PinAgentDialog availableAgents={availableAgents} nodeId={nodeId} onOpenChange={setPinOpen} open={pinOpen} />
      ) : null}

      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('nodes.deleteNodeConfirmTitle', { nodeId })}</AlertDialogTitle>
            <AlertDialogDescription>{t('nodes.deleteNodeConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('nodes.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void remove.mutateAsync()}>{t('nodes.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

// ─────────────────────────── Page ───────────────────────────

export function NodesPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const nodes = useNodesQuery()
  const agents = useNodeAgentsQuery()
  const [registerOpen, setRegisterOpen] = useState(false)

  const canWrite = me.data?.role !== 'viewer'

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('nodes.title')}</h2>
          <Badge variant="secondary">{nodes.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={() => setRegisterOpen(true)}>
            <Plus className="size-4" /> {t('nodes.registerNode')}
          </Button>
        ) : null}
      </div>

      <p className="max-w-2xl text-muted-foreground text-sm">{t('nodes.pageDescription')}</p>

      <div className="grid gap-4 lg:grid-cols-2">
        {nodes.data?.map((node) => (
          <NodeCard
            agentOptions={agents.data ?? []}
            canWrite={canWrite}
            key={node.id}
            labels={node.labels}
            lastSeenAt={node.last_seen_at}
            nodeId={node.id}
            nodeName={node.name}
            registeredAt={node.registered_at}
          />
        ))}
        {nodes.data && nodes.data.length === 0 ? (
          <div className="rounded-lg border border-border border-dashed py-12 text-center text-muted-foreground text-sm lg:col-span-2">
            {t('nodes.empty')}
          </div>
        ) : null}
      </div>

      {canWrite ? <RegisterNodeDialog onOpenChange={setRegisterOpen} open={registerOpen} /> : null}
    </div>
  )
}
