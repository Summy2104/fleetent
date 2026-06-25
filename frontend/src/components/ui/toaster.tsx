import { useEffect, useState } from 'react';
import { CheckCircle2, Info, X, XCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import { TOAST_EVENT, type ToastInput, type ToastVariant } from '@/lib/toast';

type ActiveToast = ToastInput & { id: number; variant: ToastVariant };

const ICONS: Record<ToastVariant, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  info: Info,
};

const ACCENT: Record<ToastVariant, string> = {
  success: 'text-success',
  error: 'text-destructive',
  info: 'text-primary',
};

const DEFAULT_DURATION = 4500;

export function Toaster(): JSX.Element {
  const [toasts, setToasts] = useState<ActiveToast[]>([]);

  useEffect(() => {
    let counter = 0;
    const onToast = (event: Event): void => {
      const detail = (event as CustomEvent<ToastInput>).detail;
      const id = ++counter;
      const variant = detail.variant ?? 'info';
      setToasts((current) => [...current, { ...detail, id, variant }]);
      const duration = detail.duration ?? DEFAULT_DURATION;
      if (duration > 0) {
        window.setTimeout(() => setToasts((current) => current.filter((t) => t.id !== id)), duration);
      }
    };
    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, []);

  const dismiss = (id: number): void => setToasts((current) => current.filter((t) => t.id !== id));

  return (
    <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-full max-w-sm flex-col items-end gap-2">
      {toasts.map((toast) => {
        const Icon = ICONS[toast.variant];
        return (
          <div
            key={toast.id}
            role="status"
            className="pointer-events-auto flex w-full items-start gap-3 rounded-lg border border-border bg-popover p-4 text-popover-foreground shadow-soft animate-fade-in"
          >
            <Icon className={cn('mt-0.5 size-5 shrink-0', ACCENT[toast.variant])} />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{toast.title}</p>
              {toast.description ? (
                <p className="mt-0.5 break-words text-sm text-muted-foreground">{toast.description}</p>
              ) : null}
            </div>
            <button
              type="button"
              aria-label="Dismiss"
              className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => dismiss(toast.id)}
            >
              <X className="size-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
