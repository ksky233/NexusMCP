FROM node:22.18.0-alpine@sha256:1b2479dd35a99687d6638f5976fd235e26c5b37e8122f786fcd5fe231d63de5b AS builder

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG VITE_PUBLIC_DEMO=false

WORKDIR /workspace/web

RUN corepack enable && corepack prepare pnpm@10.15.1 --activate
RUN pnpm config set registry "$NPM_REGISTRY"

COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY contracts /workspace/contracts
COPY benchmarks /workspace/benchmarks
COPY evals /workspace/evals
COPY web ./

ENV VITE_PUBLIC_DEMO=$VITE_PUBLIC_DEMO
RUN pnpm api:generate && pnpm build

FROM nginxinc/nginx-unprivileged:1.30.4-alpine@sha256:93722936b82ec8a1178d48448e619226680d2de3706a1640800e186cd5fa7fd3

ARG NGINX_CONFIG=web/nginx/default.conf

COPY ${NGINX_CONFIG} /etc/nginx/conf.d/default.conf
COPY --from=builder /workspace/web/dist /usr/share/nginx/html

EXPOSE 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1
