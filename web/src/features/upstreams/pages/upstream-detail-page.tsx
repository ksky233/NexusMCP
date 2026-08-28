import { ArrowLeft, Ban, Pencil } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { InlineError, ErrorState, LoadingState } from "@/components/common/query-state";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { StatusPill } from "@/components/ui/status-pill";
import {
  useDisableUpstream,
  useUpdateUpstream,
  useUpstream,
} from "@/features/upstreams/hooks/use-upstreams";
import { UpstreamForm } from "@/features/upstreams/parts/upstream-form";
import type { UpdateUpstreamRequest } from "@/generated/api/types.gen";
import { formatDateTime, humanize, statusTone } from "@/lib/display";

export function UpstreamDetailPage() {
  const upstreamId = useParams().upstreamId ?? "";
  const [editing, setEditing] = useState(false);
  const [disableOpen, setDisableOpen] = useState(false);
  const upstream = useUpstream(upstreamId);
  const update = useUpdateUpstream(upstreamId);
  const disable = useDisableUpstream(upstreamId);

  if (upstream.isPending) return <LoadingState label="Loading upstream detail…" />;
  if (upstream.isError)
    return <ErrorState error={upstream.error} onRetry={() => void upstream.refetch()} />;

  const data = upstream.data;
  return (
    <section className="page-enter">
      <Link
        className="mb-7 inline-flex items-center gap-2 text-xs text-slate/60 hover:text-ink"
        to="/upstreams"
      >
        <ArrowLeft aria-hidden="true" className="size-3.5" /> Back to upstreams
      </Link>
      <PageHeader
        actions={
          <>
            <Button onClick={() => setEditing((value) => !value)} size="small" variant="secondary">
              <Pencil aria-hidden="true" className="size-3.5" /> Edit
            </Button>
            <Button
              disabled={data.status === "disabled"}
              onClick={() => setDisableOpen(true)}
              size="small"
              variant="danger"
            >
              <Ban aria-hidden="true" className="size-3.5" /> Disable
            </Button>
          </>
        }
        description={data.description ?? "No description provided."}
        eyebrow="Registry · HTTP/OpenAPI"
        title={`${data.namespace}.${data.name}`}
      />

      {editing ? (
        <div className="mb-6">
          <UpstreamForm
            error={update.error}
            initialValues={{
              namespace: data.namespace,
              name: data.name,
              description: data.description ?? "",
              owner: data.owner,
              endpoint: data.endpoint,
              auth_scheme:
                data.auth_scheme === "bearer" || data.auth_scheme === "api_key"
                  ? data.auth_scheme
                  : "none",
              config_json: JSON.stringify(data.config, null, 2),
            }}
            mode="edit"
            onCancel={() => setEditing(false)}
            onSubmit={async (body) => {
              await update.mutateAsync(body as UpdateUpstreamRequest);
              setEditing(false);
            }}
            pending={update.isPending}
          />
        </div>
      ) : null}

      {disable.error ? (
        <div className="mb-5">
          <InlineError error={disable.error} />
        </div>
      ) : null}

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <article className="panel p-6 sm:p-7">
          <p className="component-label">Connection</p>
          <dl className="mt-6 grid gap-x-8 gap-y-5 sm:grid-cols-2">
            <Definition label="Endpoint" mono value={data.endpoint} />
            <Definition label="Owner" value={data.owner} />
            <Definition label="Transport" value={data.transport_type.toUpperCase()} />
            <Definition label="Auth scheme" value={data.auth_scheme ?? "none"} />
            <Definition label="Protocol minimum" value={data.protocol_min ?? "—"} />
            <Definition label="Protocol maximum" value={data.protocol_max ?? "—"} />
          </dl>
        </article>
        <article className="panel p-6 sm:p-7">
          <div className="flex items-center justify-between gap-4">
            <p className="component-label">Lifecycle</p>
            <StatusPill tone={statusTone(data.status)}>{humanize(data.status)}</StatusPill>
          </div>
          <dl className="mt-6 space-y-5">
            <Definition label="Created" value={formatDateTime(data.created_at)} />
            <Definition label="Updated" value={formatDateTime(data.updated_at)} />
            <Definition label="Tenant" mono value={data.tenant_id} />
          </dl>
        </article>
      </div>

      <article className="panel mt-5 p-6 sm:p-7">
        <p className="component-label">Non-sensitive config</p>
        <pre className="mt-5 overflow-x-auto border border-slate/15 bg-canvas p-4 font-mono text-xs leading-6 text-slate">
          {JSON.stringify(data.config, null, 2)}
        </pre>
      </article>

      <ConfirmDialog
        confirmLabel={disable.isPending ? "Disabling…" : "Disable upstream"}
        danger
        description="New tool calls will no longer resolve through this upstream. Published history and audit evidence remain available."
        onConfirm={() => {
          void disable.mutateAsync().then(() => setDisableOpen(false));
        }}
        onOpenChange={setDisableOpen}
        open={disableOpen}
        title="Disable this upstream?"
      />
    </section>
  );
}

function Definition({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-[0.14em] text-slate/45">{label}</dt>
      <dd
        className={mono ? "mt-2 break-all font-mono text-xs text-slate" : "mt-2 text-sm text-slate"}
      >
        {value}
      </dd>
    </div>
  );
}
