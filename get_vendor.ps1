$ErrorActionPreference = "Stop"
$root   = Split-Path -Parent $MyInvocation.MyCommand.Path
$vendor = Join-Path $root "vendor"
New-Item -ItemType Directory -Force -Path $vendor | Out-Null

function Find-Tesseract {
  @("$env:ProgramFiles\Tesseract-OCR",
    "${env:ProgramFiles(x86)}\Tesseract-OCR",
    "$env:LOCALAPPDATA\Programs\Tesseract-OCR") |
    Where-Object { Test-Path (Join-Path $_ "tesseract.exe") } |
    Select-Object -First 1
}

# --- Tesseract ---
$tessDst = Join-Path $vendor "tesseract"
$src = Find-Tesseract
if (-not $src) {
  Write-Host "Tesseract not found, installing via winget..."
  try { winget install --id UB-Mannheim.TesseractOCR -e --accept-source-agreements --accept-package-agreements } catch {}
  $src = Find-Tesseract
}
if ($src) {
  New-Item -ItemType Directory -Force -Path $tessDst | Out-Null
  Copy-Item (Join-Path $src "*") $tessDst -Recurse -Force
  Write-Host "Tesseract -> $tessDst"
} else {
  Write-Warning "Tesseract not found. Install: winget install UB-Mannheim.TesseractOCR (or choco install tesseract), then re-run."
}

# --- языковые данные ---
$td = Join-Path $tessDst "tessdata"
New-Item -ItemType Directory -Force -Path $td | Out-Null
foreach ($lang in @("rus", "eng", "osd")) {
  $f = Join-Path $td "$lang.traineddata"
  if (-not (Test-Path $f)) {
    Write-Host "Downloading $lang.traineddata..."
    Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/main/$lang.traineddata" -OutFile $f
  }
}

# --- Poppler (для сканированных PDF) ---
$popDst = Join-Path $vendor "poppler"
if (-not (Test-Path (Join-Path $popDst "bin\pdftoppm.exe"))) {
  $zip = Join-Path $env:TEMP "poppler.zip"
  $tmp = Join-Path $env:TEMP "poppler_x"
  Write-Host "Downloading Poppler..."
  Invoke-WebRequest "https://github.com/oschwartz10612/poppler-windows/releases/download/v24.08.0-0/Release-24.08.0-0.zip" -OutFile $zip
  if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
  Expand-Archive $zip -DestinationPath $tmp -Force
  $lib = Get-ChildItem $tmp -Recurse -Directory -Filter "Library" | Select-Object -First 1
  if ($lib) {
    New-Item -ItemType Directory -Force -Path $popDst | Out-Null
    Copy-Item (Join-Path $lib.FullName "*") $popDst -Recurse -Force
    Write-Host "Poppler -> $popDst"
  } else { Write-Warning "Poppler layout unexpected; unpack manually to vendor\poppler\bin" }
}
Write-Host "vendor ready."
