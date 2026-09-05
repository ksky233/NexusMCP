# NexusMCP Production Demo Deployment

Target: Tencent Cloud OpenCloudOS 9 `linux/amd64`, Docker Compose V2.

## Runtime topology

```text
dearloom Edge Nginx :443
→ nexusmcp-web:8080
→ backend:8000
   ├── postgres:5432
   └── demo-upstreams:9000
```

Only the existing Edge Nginx publishes public ports. The local-only `127.0.0.1:18080` binding is retained for direct
server diagnostics.

## Build images

Run from the repository root:

```powershell
.\deploy\production\build-images.ps1 -Tag local
```

Omitting `-Tag` uses the current twelve-character Git SHA for a real release. A proxy can be passed explicitly:

```powershell
.\deploy\production\build-images.ps1 -Tag local -Proxy 'http://host.docker.internal:7890'
```

## Local rehearsal

```powershell
Copy-Item .\deploy\production\.env.example .\deploy\production\.env
# Edit random values and optional SiliconFlow Key.

docker compose `
  --env-file .\deploy\production\.env `
  -f .\deploy\production\docker-compose.yml `
  up -d
```

Open `http://127.0.0.1:18080`. The first Backend startup applies Alembic migrations and creates the fixed Public Demo
Tenant. Use these internal Upstream endpoints in the Web Control Plane:

```text
http://demo-upstreams:9000/employee-directory
http://demo-upstreams:9000/operations
http://demo-upstreams:9000/inventory
```

The corresponding local OpenAPI sources are:

```text
employee_directory/openapi.json
operations/openapi.json
inventory/openapi.json
```

The public-demo-only “重置演示工作区” action clears persisted business rows and recreates the fixed Tenant. It does
not drop the database, Alembic version table or pgvector extension.

## Export a server release

Build with the default Git SHA tag, then export the same tag:

```powershell
.\deploy\production\build-images.ps1
.\deploy\production\export-release.ps1
```

The ignored `deploy/production/release/nexusmcp-linux-amd64-<sha>` directory contains both Images, Compose files,
the non-secret environment template and `SHA256SUMS`.

## Server Edge network

Before applying the Edge overlay once:

```bash
docker network create dearloom-edge
```

The existing TLS Nginx container must also join `dearloom-edge`. Its `nexusmcp.dearloom.me` server block can then proxy
to:

```nginx
location / {
    proxy_pass http://nexusmcp-web:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Start NexusMCP with both Compose files:

```bash
docker compose \
  --env-file .env \
  -f docker-compose.yml \
  -f docker-compose.edge.yml \
  up -d
```

Do not switch the public Host route until the local-only URL, Backend readiness, Demo Upstreams and reset flow all pass.
