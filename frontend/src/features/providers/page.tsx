import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Activity, KeyRound, MoreVertical, Pencil, Plus, Server, Trash2 } from 'lucide-react'

import { Badge } from '@/components/base/badge'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  type ModelListItem,
  type ProviderListItem,
  useConnectivityTestMutation,
  useCreateModelMutation,
  useCreateProviderMutation,
  useDeleteModelMutation,
  useDeleteProviderMutation,
  useModelsQuery,
  useProvidersQuery,
  useUpdateModelMutation,
  useUpdateProviderMutation,
} from '@/features/providers/api'
import {
  buildCreateModelPayload,
  buildCreateProviderPayload,
  buildUpdateModelPayload,
  buildUpdateProviderPayload,
  ENDPOINT_PROTOCOLS,
  emptyModelForm,
  emptyProviderForm,
  MODEL_PROTOCOLS,
  type ModelFormState,
  modelFormFromModel,
  type ProviderFormState,
  providerFormFromProvider,
} from '@/features/providers/shared'
import { useT } from '@/i18n'
import { useAdminApi } from '@/lib/api-client'

type AdminMe = { email: string; id: string; role: string }

function useAdminMeQuery() {
  const api = useAdminApi()
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') })
}

function ProviderFormDialog({
  mode,
  open,
  onOpenChange,
  form,
  setForm,
  busy,
  onSubmit,
}: {
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  form: ProviderFormState
  setForm: (updater: (current: ProviderFormState) => ProviderFormState) => void
  busy: boolean
  onSubmit: () => Promise<void>
}): JSX.Element {
  const t = useT()
  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create' ? t('providers.dialogCreateTitle') : t('providers.dialogEditTitle', { id: form.id })}
          </DialogTitle>
          <DialogDescription>
            {mode === 'create' ? t('providers.dialogCreateDescription') : t('providers.dialogEditDescription')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="provider-id">{t('providers.fieldProviderId')}</Label>
            <Input
              disabled={mode === 'edit'}
              id="provider-id"
              onChange={(event) => setForm((current) => ({ ...current, id: event.target.value }))}
              value={form.id}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="provider-base-url">{t('providers.fieldBaseUrl')}</Label>
            <Input
              id="provider-base-url"
              onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
              value={form.baseUrl}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="provider-api-key">{t('providers.fieldApiKey')}</Label>
            <Input
              id="provider-api-key"
              onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))}
              type="password"
              value={form.apiKey}
            />
          </div>
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('common.cancel')}
          </Button>
          <Button disabled={busy || !form.id} onClick={() => void onSubmit()}>
            {mode === 'create' ? t('providers.createSubmit') : t('providers.editSubmit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ModelFormDialog({
  mode,
  open,
  onOpenChange,
  form,
  setForm,
  busy,
  onSubmit,
}: {
  mode: 'create' | 'edit'
  open: boolean
  onOpenChange: (open: boolean) => void
  form: ModelFormState
  setForm: (updater: (current: ModelFormState) => ModelFormState) => void
  busy: boolean
  onSubmit: () => Promise<void>
}): JSX.Element {
  const t = useT()
  const requiresEndpoint = ENDPOINT_PROTOCOLS.has(form.protocol)
  return (
    <Dialog onOpenChange={onOpenChange} open={open}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create'
              ? t('providers.newModelDialogTitle')
              : t('providers.editModelDialogTitle', { id: form.id })}
          </DialogTitle>
          <DialogDescription>
            {mode === 'create' ? t('providers.newModelDialogDescription') : t('providers.editModelDialogDescription')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="model-id">{t('providers.fieldModelId')}</Label>
            <Input
              disabled={mode === 'edit'}
              id="model-id"
              onChange={(event) => setForm((current) => ({ ...current, id: event.target.value }))}
              value={form.id}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="model-name">{t('providers.fieldModelName')}</Label>
            <Input
              id="model-name"
              onChange={(event) => setForm((current) => ({ ...current, modelName: event.target.value }))}
              value={form.modelName}
            />
          </div>
          <div className="grid gap-2">
            <Label>{t('providers.fieldProtocol')}</Label>
            <Select
              onValueChange={(value) => setForm((current) => ({ ...current, protocol: value ?? current.protocol }))}
              value={form.protocol}
            >
              <SelectTrigger aria-label={t('providers.fieldProtocol')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODEL_PROTOCOLS.map((protocol) => (
                  <SelectItem key={protocol} value={protocol}>
                    {protocol}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {requiresEndpoint ? (
            <div className="grid gap-2">
              <Label htmlFor="model-endpoint">{t('providers.fieldEndpoint')}</Label>
              <Input
                id="model-endpoint"
                onChange={(event) => setForm((current) => ({ ...current, endpoint: event.target.value }))}
                value={form.endpoint}
              />
            </div>
          ) : (
            <div className="grid gap-2">
              <Label htmlFor="model-base-url">{t('providers.fieldBaseUrl')}</Label>
              <Input
                id="model-base-url"
                onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
                value={form.baseUrl}
              />
            </div>
          )}
        </div>
        <DialogFooter>
          <Button onClick={() => onOpenChange(false)} variant="outline">
            {t('common.cancel')}
          </Button>
          <Button disabled={busy || !form.id || !form.modelName} onClick={() => void onSubmit()}>
            {mode === 'create' ? t('providers.createModelSubmit') : t('providers.editSubmit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Own component so each row can hold its delete mutation + confirm state (hooks
// cannot live inside the models `.map`).
function ModelRow({
  model,
  canWrite,
  onEdit,
}: {
  model: ModelListItem
  canWrite: boolean
  onEdit: () => void
}): JSX.Element {
  const t = useT()
  const deleteModel = useDeleteModelMutation(model.id)
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-medium">{model.model_name}</div>
          <div className="text-muted-foreground text-sm">{model.id}</div>
        </div>
        {canWrite ? (
          <div className="flex items-center gap-1">
            <Button
              aria-label={t('providers.editModelLabel', { id: model.id })}
              onClick={onEdit}
              size="icon"
              variant="ghost"
            >
              <Pencil className="size-4" />
            </Button>
            <Button
              aria-label={t('providers.deleteModelLabel', { id: model.id })}
              onClick={() => setConfirmDelete(true)}
              size="icon"
              variant="ghost"
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ) : null}
      </div>
      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('providers.deleteModelTitle', { id: model.id })}</AlertDialogTitle>
            <AlertDialogDescription>{t('providers.deleteModelDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void deleteModel.mutateAsync()}>{t('common.delete')}</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

function ProviderCard({
  provider,
  models,
  canWrite,
  onEdit,
  onCreateModel,
  onEditModel,
}: {
  provider: ProviderListItem
  models: ModelListItem[]
  canWrite: boolean
  onEdit: () => void
  onCreateModel: () => void
  onEditModel: (model: ModelListItem) => void
}): JSX.Element {
  const t = useT()
  const deleteProvider = useDeleteProviderMutation(provider.id)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const connectivity = useConnectivityTestMutation(models[0]?.id ?? provider.id)

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="size-4 text-primary" /> {provider.id}
              {provider.provider ? <Badge variant="outline">{provider.provider}</Badge> : null}
              <Badge variant="secondary">{provider.model_count}</Badge>
            </CardTitle>
            {provider.base_url ? <p className="text-muted-foreground text-sm">{provider.base_url}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {models[0] ? (
              <Button
                aria-label={t('providers.testConnectivityLabel', { id: models[0].id })}
                onClick={() => void connectivity.mutateAsync()}
                size="sm"
                variant="outline"
              >
                <Activity className="size-4" /> {t('providers.test')}
              </Button>
            ) : null}
            {canWrite ? (
              <>
                <Button onClick={onCreateModel} size="sm" variant="secondary">
                  <Plus className="size-4" /> {t('providers.newModel')}
                </Button>
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <Button aria-label={t('providers.actionsLabel', { id: provider.id })} size="icon" variant="ghost">
                        <MoreVertical className="size-4" />
                      </Button>
                    }
                  />
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem aria-label={t('providers.editLabel', { id: provider.id })} onClick={onEdit}>
                      <Pencil /> Edit
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      aria-label={t('providers.deleteLabel', { id: provider.id })}
                      onClick={() => setConfirmDelete(true)}
                      variant="destructive"
                    >
                      <Trash2 /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2 text-sm">
          <KeyRound className="size-3.5 text-muted-foreground" />
          <span className="font-mono">{provider.api_key ?? 'No key configured'}</span>
        </div>
        {provider.description ? <p className="text-sm">{provider.description}</p> : null}
        {connectivity.data ? (
          connectivity.data.reachable ? (
            <p className="text-sm text-success">
              {t('providers.connectivityReachable', {
                latency: connectivity.data.latency_ms ?? '?',
                model: connectivity.data.model ?? models[0]?.model_name ?? '',
              })}
            </p>
          ) : (
            <p className="text-destructive text-sm">
              {connectivity.data.error ?? connectivity.data.details ?? t('providers.connectivityFailed')}
            </p>
          )
        ) : null}
        <div className="space-y-2">
          {models.map((model) => (
            <ModelRow canWrite={canWrite} key={model.id} model={model} onEdit={() => onEditModel(model)} />
          ))}
        </div>
      </CardContent>
      <AlertDialog onOpenChange={setConfirmDelete} open={confirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('providers.deleteTitle', { id: provider.id })}</AlertDialogTitle>
            <AlertDialogDescription>{t('providers.deleteDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void deleteProvider.mutateAsync()}>
              {t('common.delete')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Card>
  )
}

export function ProvidersPage(): JSX.Element {
  const t = useT()
  const me = useAdminMeQuery()
  const providers = useProvidersQuery()
  const models = useModelsQuery()
  const createProvider = useCreateProviderMutation()
  const createModel = useCreateModelMutation()

  const [providerFormOpen, setProviderFormOpen] = useState(false)
  const [providerMode, setProviderMode] = useState<'create' | 'edit'>('create')
  const [providerForm, setProviderForm] = useState<ProviderFormState>(emptyProviderForm())
  const [editingProviderId, setEditingProviderId] = useState('')
  const updateProvider = useUpdateProviderMutation(editingProviderId)

  const [modelFormOpen, setModelFormOpen] = useState(false)
  const [modelMode, setModelMode] = useState<'create' | 'edit'>('create')
  const [modelForm, setModelForm] = useState<ModelFormState>(emptyModelForm())
  const [editingModelId, setEditingModelId] = useState('')
  const updateModel = useUpdateModelMutation(editingModelId)

  const canWrite = me.data?.role !== 'viewer'
  const modelsByProvider = useMemo(() => {
    const grouped = new Map<string, ModelListItem[]>()
    for (const model of models.data ?? []) {
      const current = grouped.get(model.provider_id) ?? []
      current.push(model)
      grouped.set(model.provider_id, current)
    }
    return grouped
  }, [models.data])

  const openCreateProvider = (): void => {
    setProviderMode('create')
    setEditingProviderId('')
    setProviderForm(emptyProviderForm())
    setProviderFormOpen(true)
  }

  const openEditProvider = (provider: ProviderListItem): void => {
    setProviderMode('edit')
    setEditingProviderId(provider.id)
    setProviderForm(providerFormFromProvider(provider))
    setProviderFormOpen(true)
  }

  const submitProvider = async (): Promise<void> => {
    if (providerMode === 'create') {
      await createProvider.mutateAsync(buildCreateProviderPayload(providerForm))
    } else {
      await updateProvider.mutateAsync(buildUpdateProviderPayload(providerForm))
    }
    setProviderFormOpen(false)
  }

  const openCreateModel = (providerId: string): void => {
    setModelMode('create')
    setEditingModelId('')
    setModelForm(emptyModelForm(providerId))
    setModelFormOpen(true)
  }

  const openEditModel = (model: ModelListItem): void => {
    setModelMode('edit')
    setEditingModelId(model.id)
    setModelForm(modelFormFromModel(model))
    setModelFormOpen(true)
  }

  const submitModel = async (): Promise<void> => {
    if (modelMode === 'create') {
      await createModel.mutateAsync(buildCreateModelPayload(modelForm))
    } else {
      await updateModel.mutateAsync(buildUpdateModelPayload(modelForm))
    }
    setModelFormOpen(false)
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="font-semibold text-xl tracking-tight">{t('nav.providers')}</h2>
          <Badge variant="secondary">{providers.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={openCreateProvider}>
            <Plus className="size-4" /> {t('providers.newProvider')}
          </Button>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {providers.data?.map((provider) => (
          <ProviderCard
            canWrite={canWrite}
            key={provider.id}
            models={modelsByProvider.get(provider.id) ?? []}
            onCreateModel={() => openCreateModel(provider.id)}
            onEdit={() => openEditProvider(provider)}
            onEditModel={openEditModel}
            provider={provider}
          />
        ))}
      </div>

      <ProviderFormDialog
        busy={createProvider.isPending || updateProvider.isPending}
        form={providerForm}
        mode={providerMode}
        onOpenChange={setProviderFormOpen}
        onSubmit={submitProvider}
        open={providerFormOpen}
        setForm={setProviderForm}
      />

      <ModelFormDialog
        busy={createModel.isPending || updateModel.isPending}
        form={modelForm}
        mode={modelMode}
        onOpenChange={setModelFormOpen}
        onSubmit={submitModel}
        open={modelFormOpen}
        setForm={setModelForm}
      />
    </div>
  )
}
