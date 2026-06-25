import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  KeyRound,
  MoreVertical,
  Pencil,
  Plus,
  Server,
  Trash2,
} from 'lucide-react';

import { useAdminApi } from '@/lib/api-client';
import { useT } from '@/i18n';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import {
  type ProviderListItem,
  useConnectivityTestMutation,
  useCreateProviderMutation,
  useDeleteProviderMutation,
  useProvidersQuery,
  useUpdatePricingMutation,
  useUpdateProviderMutation,
} from '@/features/providers/api';

type AdminMe = { email: string; id: string; role: string };

type ProviderFormState = {
  apiKey: string;
  baseUrl: string;
  description: string;
  id: string;
  model: string;
  protocol: string;
  provider: string;
};

function useAdminMeQuery() {
  const api = useAdminApi();
  return useQuery({ queryKey: ['admin-me'], queryFn: () => api.get<AdminMe>('/admin/me') });
}

function emptyForm(): ProviderFormState {
  return {
    apiKey: '',
    baseUrl: '',
    description: '',
    id: '',
    model: '',
    protocol: '',
    provider: '',
  };
}

function priceInputValue(value: number | string | null): string {
  return typeof value === 'number' ? String(value) : '';
}

function priceLabel(value: number | string | null, unsetLabel: string): string {
  return value === null || value === undefined || value === '' ? unsetLabel : String(value);
}

// ─────────────────────────── Create / edit dialog ───────────────────────────

function ProviderFormDialog({
  mode,
  open,
  onOpenChange,
  form,
  setForm,
  busy,
  onSubmit,
}: {
  mode: 'create' | 'edit';
  open: boolean;
  onOpenChange: (open: boolean) => void;
  form: ProviderFormState;
  setForm: (updater: (current: ProviderFormState) => ProviderFormState) => void;
  busy: boolean;
  onSubmit: () => Promise<void>;
}): JSX.Element {
  const t = useT();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create' ? t('providers.dialogCreateTitle') : t('providers.dialogEditTitle', { id: form.id })}
          </DialogTitle>
          <DialogDescription>
            {mode === 'create'
              ? t('providers.dialogCreateDescription')
              : t('providers.dialogEditDescription')}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-2">
            <Label htmlFor="provider-id">{t('providers.fieldProviderId')}</Label>
            <Input
              id="provider-id"
              disabled={mode === 'edit'}
              value={form.id}
              onChange={(event) => setForm((current) => ({ ...current, id: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="provider-base-url">{t('providers.fieldBaseUrl')}</Label>
            <Input
              id="provider-base-url"
              value={form.baseUrl}
              onChange={(event) => setForm((current) => ({ ...current, baseUrl: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="provider-model">{t('providers.fieldModel')}</Label>
            <Input
              id="provider-model"
              value={form.model}
              onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="provider-api-key">{t('providers.fieldApiKey')}</Label>
            <Input
              id="provider-api-key"
              type="password"
              placeholder={mode === 'edit' ? t('providers.apiKeyPlaceholder') : ''}
              value={form.apiKey}
              onChange={(event) => setForm((current) => ({ ...current, apiKey: event.target.value }))}
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="provider-description">{t('providers.fieldDescription')}</Label>
            <Input
              id="provider-description"
              value={form.description}
              onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="grid gap-2">
              <Label htmlFor="provider-vendor">{t('providers.fieldVendor')}</Label>
              <Input
                id="provider-vendor"
                value={form.provider}
                onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
              />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="provider-protocol">{t('providers.fieldProtocol')}</Label>
              <Input
                id="provider-protocol"
                value={form.protocol}
                onChange={(event) => setForm((current) => ({ ...current, protocol: event.target.value }))}
              />
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            disabled={busy || !form.id || (mode === 'create' && (!form.baseUrl || !form.model))}
            onClick={() => void onSubmit()}
          >
            {mode === 'create' ? t('providers.createSubmit') : t('providers.editSubmit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ─────────────────────────── Provider card ───────────────────────────

function ProviderCard({
  provider,
  canWrite,
  onEdit,
}: {
  provider: ProviderListItem;
  canWrite: boolean;
  onEdit: () => void;
}): JSX.Element {
  const t = useT();
  const connectivityTest = useConnectivityTestMutation(provider.id);
  const deleteProvider = useDeleteProviderMutation(provider.id);
  const updatePricing = useUpdatePricingMutation(provider.id);

  const [inputPrice, setInputPrice] = useState(priceInputValue(provider.input_price_per_1k));
  const [outputPrice, setOutputPrice] = useState(priceInputValue(provider.output_price_per_1k));
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setInputPrice(priceInputValue(provider.input_price_per_1k));
    setOutputPrice(priceInputValue(provider.output_price_per_1k));
  }, [provider.input_price_per_1k, provider.output_price_per_1k]);

  const connectivityMessage = connectivityTest.data
    ? connectivityTest.data.reachable
      ? t('providers.connectivityReachable', {
          latency: connectivityTest.data.latency_ms ?? '?',
          model: connectivityTest.data.model ?? provider.model,
        })
      : connectivityTest.data.error ?? t('providers.connectivityFailed')
    : null;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              <Server className="size-4 text-primary" /> {provider.id}
              {provider.provider ? <Badge variant="outline">{provider.provider}</Badge> : null}
            </CardTitle>
            <p className="truncate text-sm text-muted-foreground">{provider.base_url}</p>
            <p className="truncate text-sm text-muted-foreground">{provider.model}</p>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              aria-label={t('providers.testConnectivityLabel', { id: provider.id })}
              onClick={() => void connectivityTest.mutateAsync()}
              disabled={connectivityTest.isPending}
            >
              <Activity className="size-4" /> {t('providers.test')}
            </Button>
            {canWrite ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" aria-label={t('providers.actionsLabel', { id: provider.id })}>
                    <MoreVertical className="size-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem aria-label={t('providers.editLabel', { id: provider.id })} onSelect={onEdit}>
                    <Pencil /> {t('common.edit')}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    destructive
                    aria-label={t('providers.deleteLabel', { id: provider.id })}
                    onSelect={() => setConfirmDelete(true)}
                  >
                    <Trash2 /> {t('common.delete')}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <KeyRound className="size-3.5" />
            <span className="font-mono">{provider.api_key ?? t('providers.noKeyConfigured')}</span>
          </span>
          <Badge variant={provider.api_key_set ? 'success' : 'outline'}>
            {provider.api_key_set ? t('providers.keySet') : t('providers.noKey')}
          </Badge>
        </div>

        {provider.description ? <p className="text-sm text-foreground">{provider.description}</p> : null}

        {connectivityMessage ? (
          <p
            className={cn(
              'text-sm',
              connectivityTest.data?.reachable ? 'text-success' : 'text-destructive'
            )}
          >
            {connectivityMessage}
          </p>
        ) : null}

        <Separator />

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-foreground">{t('providers.pricingHeading')}</h3>
            <span className="text-xs text-muted-foreground">
              {t('providers.pricingSummary', {
                input: priceLabel(provider.input_price_per_1k, t('providers.priceUnset')),
                output: priceLabel(provider.output_price_per_1k, t('providers.priceUnset')),
              })}
            </span>
          </div>
          {canWrite ? (
            <div className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
              <div className="grid gap-1.5">
                <Label className="text-xs text-muted-foreground">{t('providers.inputPriceLabel')}</Label>
                <Input
                  aria-label={t('providers.inputPriceLabel')}
                  value={inputPrice}
                  onChange={(event) => setInputPrice(event.target.value)}
                />
              </div>
              <div className="grid gap-1.5">
                <Label className="text-xs text-muted-foreground">{t('providers.outputPriceLabel')}</Label>
                <Input
                  aria-label={t('providers.outputPriceLabel')}
                  value={outputPrice}
                  onChange={(event) => setOutputPrice(event.target.value)}
                />
              </div>
              <Button
                variant="secondary"
                aria-label={t('providers.savePricingLabel', { id: provider.id })}
                disabled={updatePricing.isPending}
                onClick={() =>
                  void updatePricing.mutateAsync({
                    input_price_per_1k: inputPrice === '' ? null : Number(inputPrice),
                    output_price_per_1k: outputPrice === '' ? null : Number(outputPrice),
                  })
                }
              >
                {t('providers.savePricing')}
              </Button>
            </div>
          ) : null}
        </div>
      </CardContent>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
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
  );
}

// ─────────────────────────── Page ───────────────────────────

export function ProvidersPage(): JSX.Element {
  const t = useT();
  const me = useAdminMeQuery();
  const providers = useProvidersQuery();
  const createProvider = useCreateProviderMutation();

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<'create' | 'edit'>('create');
  const [form, setForm] = useState<ProviderFormState>(emptyForm);
  const [formOpen, setFormOpen] = useState(false);

  const canWrite = me.data?.role !== 'viewer';
  const updateProvider = useUpdateProviderMutation(selectedId ?? '');

  const openCreate = (): void => {
    setMode('create');
    setForm(emptyForm());
    setSelectedId(null);
    setFormOpen(true);
  };

  const startEdit = (provider: ProviderListItem): void => {
    setSelectedId(provider.id);
    setMode('edit');
    setForm({
      apiKey: '',
      baseUrl: provider.base_url,
      description: provider.description ?? '',
      id: provider.id,
      model: provider.model,
      protocol: provider.protocol ?? '',
      provider: provider.provider ?? '',
    });
    setFormOpen(true);
  };

  const onSubmit = async (): Promise<void> => {
    if (mode === 'create') {
      await createProvider.mutateAsync({
        api_key: form.apiKey || undefined,
        base_url: form.baseUrl,
        description: form.description || undefined,
        id: form.id,
        model: form.model,
        protocol: form.protocol || undefined,
        provider: form.provider || undefined,
      });
      setFormOpen(false);
      return;
    }

    if (!selectedId) {
      return;
    }

    await updateProvider.mutateAsync({
      api_key: form.apiKey || undefined,
      base_url: form.baseUrl || undefined,
      description: form.description || undefined,
      model: form.model || undefined,
      protocol: form.protocol || undefined,
      provider: form.provider || undefined,
    });
    setFormOpen(false);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h2 className="text-xl font-semibold tracking-tight">{t('nav.providers')}</h2>
          <Badge variant="secondary">{providers.data?.length ?? 0}</Badge>
        </div>
        {canWrite ? (
          <Button onClick={openCreate}>
            <Plus className="size-4" /> {t('providers.newProvider')}
          </Button>
        ) : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {providers.data?.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            canWrite={canWrite}
            onEdit={() => startEdit(provider)}
          />
        ))}
      </div>

      {providers.data && providers.data.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
          {t('providers.emptyState')}
        </div>
      ) : null}

      <ProviderFormDialog
        mode={mode}
        open={formOpen}
        onOpenChange={setFormOpen}
        form={form}
        setForm={setForm}
        busy={createProvider.isPending || updateProvider.isPending}
        onSubmit={onSubmit}
      />
    </div>
  );
}
