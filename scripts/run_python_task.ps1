param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("server", "test")]
    [string]$Task
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$condaExe = $env:CONDA_EXE
if (-not $condaExe -or -not (Test-Path -LiteralPath $condaExe)) {
    $condaExe = (Get-Command conda.exe -ErrorAction Stop).Source
}
$condaRoot = Split-Path -Parent (Split-Path -Parent $condaExe)
$condaHook = Join-Path $condaRoot "shell\condabin\conda-hook.ps1"
if (-not (Test-Path -LiteralPath $condaHook)) {
    throw "未找到 Conda PowerShell hook：$condaHook"
}

. $condaHook
conda activate pytorch_env
if ($env:CONDA_DEFAULT_ENV -ne "pytorch_env") {
    throw "无法激活 Conda 环境 pytorch_env"
}

Set-Location (Split-Path -Parent $PSScriptRoot)
if ($Task -eq "server") {
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
} else {
    python -m pytest -q
}
