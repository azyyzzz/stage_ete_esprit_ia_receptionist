<#
.SYNOPSIS
    Installe Tesseract OCR + le pack de langue francaise (binaire systeme
    requis par extraction_app pour l'OCR d'images et de PDF sans texte
    natif -- pytesseract n'est qu'un wrapper Python, voir
    extraction_app/README.md).

.DESCRIPTION
    A lancer UNE SEULE FOIS, manuellement. Utilise winget (deja present sur
    Windows 10/11 a jour) pour le binaire. L'installeur Windows officiel
    n'embarque PAS le pack francais (seul l'anglais l'est) : ce script le
    telecharge separement dans tessdata/ a la racine du projet (pas dans
    le dossier d'installation Tesseract, qui exige des droits admin en
    ecriture) -- extraction_app/services/pdf_extractor.py le detecte et
    l'utilise automatiquement s'il est present.

.EXAMPLE
    .\scripts\install_tesseract.ps1
#>

Set-StrictMode -Version Latest
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TessdataDir = Join-Path $ProjectRoot "tessdata"
$FraPath = Join-Path $TessdataDir "fra.traineddata"

$existing = Get-Command tesseract -ErrorAction SilentlyContinue
$defaultPath = "C:\Program Files\Tesseract-OCR\tesseract.exe"
if (-not $existing -and (Test-Path $defaultPath)) {
    Write-Host "Tesseract deja installe (non trouve sur le PATH de cette session) : $defaultPath"
} elseif ($existing) {
    Write-Host "Tesseract deja installe : $($existing.Source)"
} else {
    Write-Host "Installation de Tesseract OCR via winget (package UB-Mannheim.TesseractOCR)..."
    winget install --id UB-Mannheim.TesseractOCR --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "winget a signale une erreur (code $LASTEXITCODE). Installation manuelle : https://github.com/UB-Mannheim/tesseract/wiki"
        exit 1
    }
    Write-Host "Installation terminee. Un NOUVEAU terminal sera necessaire pour que le PATH mis a jour soit pris en compte."
}

if (Test-Path $FraPath) {
    Write-Host "Pack de langue francaise deja present : $FraPath"
} else {
    Write-Host "Telechargement du pack de langue francaise (tessdata/fra.traineddata, ~14 Mo)..."
    New-Item -ItemType Directory -Force -Path $TessdataDir | Out-Null
    Invoke-WebRequest -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/fra.traineddata" -OutFile $FraPath
    Write-Host "Pack francais installe : $FraPath"
}

Write-Host ""
Write-Host "Verification :"
if ($existing) {
    tesseract --version
} else {
    & $defaultPath --version
}
