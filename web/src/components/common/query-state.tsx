import { AlertTriangle, Inbox, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { asApiClientError } from "@/lib/api/api-error";

export function LoadingState({ label = "Loading control plane data…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle aria-hidden="true" className="size-5 animate-spin text-accent" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="state-panel flex-col text-center">
      <span className="rounded-xl bg-surface-strong p-3 text-ink-muted">
        <Inbox aria-hidden="true" className="size-6" />
      </span>
      <div>
        <h2 className="font-semibold text-ink">{title}</h2>
        <p className="mt-1 max-w-lg text-sm text-ink-muted">{description}</p>
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const normalized = asApiClientError(error);
  return (
    <div className="state-panel flex-col items-start" role="alert">
      <span className="rounded-xl bg-danger-soft p-3 text-danger">
        <AlertTriangle aria-hidden="true" className="size-6" />
      </span>
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-danger">
          {normalized.code}
        </p>
        <h2 className="mt-1 font-semibold text-ink">Unable to load this view</h2>
        <p className="mt-1 max-w-xl text-sm text-ink-muted">{normalized.message}</p>
        {normalized.requestId ? (
          <p className="mt-3 font-mono text-xs text-ink-subtle">
            Request ID: {normalized.requestId}
          </p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          Try again
        </Button>
      ) : null}
    </div>
  );
}
