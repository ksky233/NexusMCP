# NexusMCP Control Plane Web

Local Development Admin SPA for the NexusMCP Control Plane. This application is not a Production Authentication
surface and does not store credentials or tokens in the browser.

## Runtime

- Node.js `22.18.0`;
- pnpm `10.15.1`;
- React `19.2.8`;
- Vite `8.2.2`;
- TypeScript `5.9.3`;
- Hey API `0.99.0`;
- TanStack Query `5.102.8`.

Versions are exact in `package.json` and `pnpm-lock.yaml`. TypeScript stays on `5.9.3` because Hey API `0.99.0`
currently fails at runtime with TypeScript 7 Compiler API even though installation can resolve.

## Commands

```powershell
pnpm install --frozen-lockfile
pnpm api:generate
pnpm format:check
pnpm typecheck
pnpm lint
pnpm test
pnpm build
pnpm dev
```

Development assumes the FastAPI application is available on `127.0.0.1:8000`. Vite proxies `/admin` and `/health`
to that process.

## Contract Boundary

```text
../contracts/admin.openapi.json
  → openapi-ts.config.ts
    → src/generated/api
      → Feature API
        → Feature Query Hook
          → Page
```

`src/generated/api` is committed, deterministic generated code. Do not modify it manually. Generated TypeScript,
SDK, Fetch Client and Zod response schemas participate in Type Check; Lint/Format exclude the directory because the
generator owns its source style.

The generated Client derives `/admin` from the browser's current Origin. It does not read an API Host from build-time
environment variables, so the same static Artifact works behind any Same-Origin reverse proxy.

## State Ownership

- Server state: TanStack Query;
- route/filter/page state: React Router URL;
- future forms: React Hook Form + Zod;
- dialog and expanded-row state: local component state;
- no Zustand until real cross-page browser-owned state appears.

Pages never call the Generated SDK directly. A Feature API Wrapper owns timeout and transport invocation, while a
Feature Query Hook owns Query Key, Retry, Stale Time and Polling.

## Error Boundary

Expected backend errors must be `application/problem+json`. The client classifies:

- Problem Details;
- network failure;
- timeout;
- abort;
- invalid Content-Type/Problem Envelope;
- successful response schema drift through generated Zod validators.

UI branches on stable `status/code`, displays safe `detail`, and preserves `request_id` for log correlation.
