import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import type { ReactNode } from "react";
import { z } from "zod";

import { InlineError } from "@/components/common/query-state";
import { Button } from "@/components/ui/button";
import { FieldHelp, FieldLabel, Input, Select, Textarea } from "@/components/ui/form-controls";
import type { RegisterUpstreamRequest, UpdateUpstreamRequest } from "@/generated/api/types.gen";

const upstreamSchema = z.object({
  namespace: z
    .string()
    .trim()
    .min(1, "Namespace is required")
    .max(64)
    .regex(/^[a-z][a-z0-9_-]*$/, "Use lowercase letters, digits, underscore or hyphen"),
  name: z.string().trim().min(1, "Name is required").max(128),
  description: z.string().trim().max(2_000),
  owner: z.string().trim().min(1, "Owner is required").max(128),
  endpoint: z
    .string()
    .trim()
    .url("Enter a valid HTTP URL")
    .refine((value) => value.startsWith("http://") || value.startsWith("https://"), {
      message: "Endpoint must use HTTP or HTTPS",
    }),
  auth_scheme: z.enum(["none", "bearer", "api_key"]),
  config_json: z.string().superRefine((value, context) => {
    try {
      const parsed: unknown = JSON.parse(value);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        context.addIssue({ code: "custom", message: "Config must be a JSON object" });
      }
    } catch {
      context.addIssue({ code: "custom", message: "Config must be valid JSON" });
    }
  }),
});

type UpstreamFormValues = z.infer<typeof upstreamSchema>;

export function UpstreamForm({
  mode,
  initialValues,
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  mode: "register" | "edit";
  initialValues?: Partial<UpstreamFormValues>;
  pending: boolean;
  error?: unknown;
  onCancel: () => void;
  onSubmit: (body: RegisterUpstreamRequest | UpdateUpstreamRequest) => Promise<void>;
}) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<UpstreamFormValues>({
    resolver: zodResolver(upstreamSchema),
    defaultValues: {
      namespace: initialValues?.namespace ?? "",
      name: initialValues?.name ?? "",
      description: initialValues?.description ?? "",
      owner: initialValues?.owner ?? "",
      endpoint: initialValues?.endpoint ?? "",
      auth_scheme: initialValues?.auth_scheme ?? "none",
      config_json: initialValues?.config_json ?? "{}",
    },
  });

  const submit = handleSubmit(async (values) => {
    const common = {
      description: values.description || null,
      owner: values.owner,
      endpoint: values.endpoint,
      auth_scheme: values.auth_scheme,
      config: JSON.parse(values.config_json) as Record<string, unknown>,
    };
    await onSubmit(
      mode === "register"
        ? {
            ...common,
            namespace: values.namespace,
            name: values.name,
            service_type: "http",
            transport_type: "http",
          }
        : common,
    );
  });

  return (
    <form className="panel p-6 sm:p-7" onSubmit={(event) => void submit(event)}>
      <div className="grid gap-5 sm:grid-cols-2">
        {mode === "register" ? (
          <>
            <Field name="namespace" error={errors.namespace?.message} label="Namespace">
              <Input
                id="namespace"
                autoComplete="off"
                aria-invalid={Boolean(errors.namespace)}
                {...register("namespace")}
              />
            </Field>
            <Field name="name" error={errors.name?.message} label="Name">
              <Input
                id="name"
                autoComplete="off"
                aria-invalid={Boolean(errors.name)}
                {...register("name")}
              />
            </Field>
          </>
        ) : null}
        <Field name="owner" error={errors.owner?.message} label="Owner">
          <Input
            id="owner"
            autoComplete="organization"
            aria-invalid={Boolean(errors.owner)}
            {...register("owner")}
          />
        </Field>
        <Field name="auth_scheme" error={errors.auth_scheme?.message} label="Auth scheme">
          <Select
            id="auth_scheme"
            aria-invalid={Boolean(errors.auth_scheme)}
            {...register("auth_scheme")}
          >
            <option value="none">None</option>
            <option value="bearer">Bearer Secret Reference</option>
            <option value="api_key">API Key Secret Reference</option>
          </Select>
        </Field>
        <Field
          className="sm:col-span-2"
          name="endpoint"
          error={errors.endpoint?.message}
          label="Endpoint"
        >
          <Input
            id="endpoint"
            aria-invalid={Boolean(errors.endpoint)}
            placeholder="https://internal.example.test"
            {...register("endpoint")}
          />
        </Field>
        <Field
          className="sm:col-span-2"
          name="description"
          error={errors.description?.message}
          label="Description"
        >
          <Textarea
            id="description"
            aria-invalid={Boolean(errors.description)}
            {...register("description")}
          />
        </Field>
        <Field
          className="sm:col-span-2"
          name="config_json"
          error={errors.config_json?.message}
          label="Non-sensitive config JSON"
        >
          <Textarea
            aria-invalid={Boolean(errors.config_json)}
            className="font-mono text-xs"
            id="config_json"
            spellCheck={false}
            {...register("config_json")}
          />
        </Field>
      </div>
      {error ? (
        <div className="mt-5">
          <InlineError error={error} />
        </div>
      ) : null}
      <div className="mt-7 flex justify-end gap-3 border-t border-slate/15 pt-5">
        <Button disabled={pending} onClick={onCancel} type="button" variant="secondary">
          Cancel
        </Button>
        <Button disabled={pending} type="submit">
          {pending ? "Saving…" : mode === "register" ? "Register upstream" : "Save changes"}
        </Button>
      </div>
    </form>
  );
}

function Field({
  name,
  label,
  error,
  className,
  children,
}: {
  name: string;
  label: string;
  error?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={className}>
      <FieldLabel htmlFor={name}>{label}</FieldLabel>
      {children}
      {error ? <FieldHelp error>{error}</FieldHelp> : null}
    </div>
  );
}
