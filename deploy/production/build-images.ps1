param(
    [string]$Tag = "",

    [string]$Proxy = "",

    [string]$PypiIndexUrl = "https://pypi.tuna.tsinghua.edu.cn/simple",

    [string]$NpmRegistry = "https://registry.npmmirror.com"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not $Tag) {
    $Tag = (git -C $projectRoot rev-parse --short=12 HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Tag) {
        throw "could not resolve a Git SHA image tag"
    }
}

$proxyArguments = @()
if ($Proxy) {
    $proxyArguments += @(
        "--build-arg", "HTTP_PROXY=$Proxy",
        "--build-arg", "HTTPS_PROXY=$Proxy"
    )
}

Push-Location $projectRoot
try {
    $backendArguments = @(
        "buildx", "build",
        "--platform", "linux/amd64",
        "--build-arg", "PYPI_INDEX_URL=$PypiIndexUrl"
    ) + $proxyArguments + @(
        "--file", "Dockerfile",
        "--tag", "nexusmcp-backend:$Tag",
        "--load", "."
    )
    docker @backendArguments
    if ($LASTEXITCODE -ne 0) {
        throw "backend image build failed"
    }

    $webArguments = @(
        "buildx", "build",
        "--platform", "linux/amd64",
        "--build-arg", "NPM_REGISTRY=$NpmRegistry",
        "--build-arg", "VITE_PUBLIC_DEMO=true",
        "--build-arg", "NGINX_CONFIG=web/nginx/production.conf"
    ) + $proxyArguments + @(
        "--file", "web/Dockerfile",
        "--tag", "nexusmcp-web:$Tag",
        "--load", "."
    )
    docker @webArguments
    if ($LASTEXITCODE -ne 0) {
        throw "web image build failed"
    }
}
finally {
    Pop-Location
}

Write-Host "Built nexusmcp-backend:$Tag and nexusmcp-web:$Tag for linux/amd64."
