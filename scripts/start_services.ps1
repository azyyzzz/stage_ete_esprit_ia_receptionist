<#
.SYNOPSIS
    Start the backend API and extraction app for day-to-day use.

.DESCRIPTION
    - Resolves the project root from this script's location.
    - Starts Ollama if it is installed and not already listening.
    - Launches backend and extraction_app in separate PowerShell windows.
    - Does not reinstall dependencies, pull models, or rebuild the index.
#>

Set-StrictMode -Version Latest
Set-Location (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) '..')
$Root = (Get-Location).ProviderPath

$OllamaPath = $null
$cmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($cmd) {
    $OllamaPath = $cmd.Source
} else {
    $candidate = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $candidate) {
        $OllamaPath = $candidate
    }
}

if ($OllamaPath) {
    $isListening = (Test-NetConnection -ComputerName 127.0.0.1 -Port 11434).TcpTestSucceeded
    if (-not $isListening) {
        Write-Host "Starting Ollama server..."
        Start-Process -FilePath $OllamaPath -ArgumentList 'serve' -WindowStyle Normal
        Start-Sleep -Seconds 3
    }
} else {
    Write-Warning "Ollama executable not found. The API will start, but RAG requests will fail until Ollama is running."
}

$python = Join-Path $Root '.venv\Scripts\python.exe'
$backendCmd = "& '$python' -m uvicorn backend.main:app --reload"
$extractionCmd = "& '$python' -m uvicorn extraction_app.main:app --reload --port 8001"

Start-Process -FilePath powershell -ArgumentList '-NoExit','-Command',$backendCmd -WindowStyle Normal
Start-Process -FilePath powershell -ArgumentList '-NoExit','-Command',$extractionCmd -WindowStyle Normal

Write-Host "Started backend -> http://127.0.0.1:8000 and extraction app -> http://127.0.0.1:8001"