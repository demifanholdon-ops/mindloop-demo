param(
    [string]$ProjectPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 18+ is required and was not found in PATH."
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm was not found in PATH."
}
if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    throw "Codex CLI was not found in PATH. Install or enable it before running this script."
}

$nodeMajor = [int]((node --version).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 18) {
    throw "Node.js 18+ is required; found $(node --version)."
}

Push-Location $ProjectPath
try {
    npm install
    npm run build
} finally {
    Pop-Location
}

$configDirectory = Join-Path $env:USERPROFILE ".codex"
$configPath = Join-Path $configDirectory "config.toml"
New-Item -ItemType Directory -Force -Path $configDirectory | Out-Null

$existing = if (Test-Path $configPath) { Get-Content -Raw $configPath } else { "" }
if ($existing -match '(?m)^\[mcp_servers\.evomap\]\s*$') {
    throw "An evomap MCP entry already exists in $configPath. It was left unchanged; review it before replacing it."
}

if (Test-Path $configPath) {
    Copy-Item $configPath "$configPath.bak" -Force
}

$entrypoint = Join-Path $ProjectPath "dist\index.js"
function ConvertTo-TomlBasicString([string]$value) {
    return $value.Replace("\", "\\").Replace('"', '\"')
}

$entrypointToml = ConvertTo-TomlBasicString $entrypoint
$projectPathToml = ConvertTo-TomlBasicString $ProjectPath
$block = @"

[mcp_servers.evomap]
command = "node"
args = ["$entrypointToml"]
cwd = "$projectPathToml"
env_vars = ["EVOMAP_API_KEY"]
startup_timeout_sec = 20
tool_timeout_sec = 60
enabled = true
"@

Add-Content -Path $configPath -Value $block -Encoding utf8

Write-Host "EvoMap MCP configuration added without changing existing Codex settings."
if (-not [Environment]::GetEnvironmentVariable("EVOMAP_API_KEY", "User")) {
    Write-Warning 'EVOMAP_API_KEY is not set for the Windows user. Set it, then fully restart VS Code.'
}

codex mcp list
codex mcp get evomap
