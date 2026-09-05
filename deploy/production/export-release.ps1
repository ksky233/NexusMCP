param(
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

if (-not $Tag) {
    $Tag = (git -C $projectRoot rev-parse --short=12 HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Tag) {
        throw "could not resolve a Git SHA image tag"
    }
}

$backendImage = "nexusmcp-backend:$Tag"
$webImage = "nexusmcp-web:$Tag"
docker image inspect $backendImage $webImage *> $null
if ($LASTEXITCODE -ne 0) {
    throw "release images were not found; run build-images.ps1 with the same tag first"
}

$releaseRoot = Join-Path $PSScriptRoot "release"
$releaseDirectory = Join-Path $releaseRoot "nexusmcp-linux-amd64-$Tag"
if (Test-Path -LiteralPath $releaseDirectory) {
    throw "release directory already exists: $releaseDirectory"
}

New-Item -ItemType Directory -Path $releaseDirectory -Force | Out-Null
$imageArchive = Join-Path $releaseDirectory "nexusmcp-images.tar"

docker save --output $imageArchive $backendImage $webImage
if ($LASTEXITCODE -ne 0) {
    throw "docker image export failed"
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docker-compose.yml") -Destination $releaseDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "docker-compose.edge.yml") -Destination $releaseDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot ".env.example") -Destination $releaseDirectory
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "README.md") -Destination $releaseDirectory

$checksumLines = Get-ChildItem -LiteralPath $releaseDirectory -File |
    Sort-Object Name |
    ForEach-Object {
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$hash  $($_.Name)"
    }
[IO.File]::WriteAllLines(
    (Join-Path $releaseDirectory "SHA256SUMS"),
    $checksumLines,
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Exported release bundle: $releaseDirectory"
