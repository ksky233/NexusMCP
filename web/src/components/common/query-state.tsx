import { AlertTriangle, Inbox, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { asApiClientError } from "@/lib/api/api-error";

export function LoadingState({ label = "正在加载控制台数据…" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <LoaderCircle aria-hidden="true" className="size-4 animate-spin stroke-[1.5] text-slate" />
      <span>{label}</span>
    </div>
  );
}

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="state-panel flex-col text-center">
      <Inbox aria-hidden="true" className="size-7 stroke-[1.25] text-slate/55" />
      <div>
        <h2 className="mt-3 text-lg font-light text-ink">{title}</h2>
        <p className="mt-2 max-w-lg text-sm leading-6 text-slate/65">{description}</p>
      </div>
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const normalized = asApiClientError(error);
  return (
    <div className="state-panel flex-col items-start" role="alert">
      <AlertTriangle aria-hidden="true" className="size-6 stroke-[1.35] text-wine" />
      <div>
        <p className="component-label !text-wine">{normalized.code}</p>
        <h2 className="mt-3 text-lg font-light text-ink">当前页面加载失败</h2>
        <p className="mt-2 max-w-xl text-sm leading-6 text-slate/68">{normalized.message}</p>
        {normalized.requestId ? (
          <p className="mt-4 font-mono text-xs text-slate/55">Request ID：{normalized.requestId}</p>
        ) : null}
      </div>
      {onRetry ? (
        <Button variant="secondary" onClick={onRetry}>
          重新尝试
        </Button>
      ) : null}
    </div>
  );
}

export function InlineError({ error }: { error: unknown }) {
  const normalized = asApiClientError(error);
  return (
    <div
      className="rounded-[8px] border border-wine/45 bg-wine/6 px-4 py-3 text-sm text-wine"
      role="alert"
    >
      <span className="font-mono text-xs">{normalized.code}</span>
      <span className="mx-2 text-wine/35">·</span>
      <span>{normalized.message}</span>
      {normalized.requestId ? (
        <span className="mt-1 block font-mono text-xs text-wine/70">
          Request ID：{normalized.requestId}
        </span>
      ) : null}
    </div>
  );
}
