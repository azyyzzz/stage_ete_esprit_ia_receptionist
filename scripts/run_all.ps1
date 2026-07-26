<#
.SYNOPSIS
    Helper script to run the whole project locally (venv, Ollama, indexing, servers).

.DESCRIPTION
    - Creates a Python virtualenv at `.venv` if missing.
    - Optionally installs `requirements.txt`.
    - Optionally pulls the Ollama model `qwen2.5:7b-instruct`.
    - Starts Ollama server if not already listening on port 11434.
    - Runs the RAG ingest (indexer).
    - Launches the backend and extraction_app in separate PowerShell windows.

.EXAMPLE
    # Create venv, install deps, pull model, then start everything
    .\scripts\run_all.ps1 -InstallDeps -PullModel

    # Just start servers (assumes deps + Ollama already ok)
    .\scripts\run_all.ps1
#>

param(
    [switch]$InstallDeps,
    [switch]$PullModel,
    [string]$OllamaPath
)

Set-StrictMode -Version Latest
cd (Split-Path -Parent $MyInvocation.MyCommand.Path)\.. | Out-Null
$Root = (Get-Location).ProviderPath

$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) {
    Write-Host "Creating virtualenv at $Root\.venv..."
    python -m venv .venv
}

if ($InstallDeps) {
    Write-Host "Installing requirements..."
    & $Python -m pip install --upgrade pip
    & $Python -m pip install -r (Join-Path $Root 'requirements.txt')
}

# Resolve Ollama executable
if (-not $OllamaPath) {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { $OllamaPath = $cmd.Source }
    else {
        $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        if (Test-Path $candidate) { $OllamaPath = $candidate }
    }
}

if (-not $OllamaPath) {
    Write-Warning "Ollama executable not found in PATH nor in $env:LOCALAPPDATA.\nPlease install Ollama from https://ollama.com and re-run."
} else {
    if ($PullModel) {
        Write-Host "Pulling model qwen2.5:7b-instruct (may take a while)..."
        & $OllamaPath pull qwen2.5:7b-instruct
    }

    # Start Ollama serve if not listening on 11434
    $isListening = (Test-NetConnection -ComputerName 127.0.0.1 -Port 11434).TcpTestSucceeded
    if (-not $isListening) {
        Write-Host "Starting Ollama server..."
        Start-Process -FilePath $OllamaPath -ArgumentList 'serve' -WindowStyle Normal
        Start-Sleep -Seconds 3
    } else {
        Write-Host "Ollama appears to be already listening on port 11434."
    }
}

Write-Host "Running RAG ingest (index building)..."
& $Python -m modules.rag.ingest

Write-Host "Launching backend and extraction_app in separate PowerShell windows..."

$backendCmd = "& '$Python' -m uvicorn backend.main:app --reload"
Start-Process -FilePath powershell -ArgumentList '-NoExit','-Command',$backendCmd -WindowStyle Normal

$extractionCmd = "& '$Python' -m uvicorn extraction_app.main:app --reload --port 8001"
Start-Process -FilePath powershell -ArgumentList '-NoExit','-Command',$extractionCmd -WindowStyle Normal

Write-Host "Done. Backend -> http://127.0.0.1:8000  Extraction -> http://127.0.0.1:8001"
