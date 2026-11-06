# Inicia ClipsApp completo en desarrollo (Servidor Python 8790 + Web Studio Next.js 3040)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> Iniciando clipsserver en http://127.0.0.1:8790 ..." -ForegroundColor Yellow
$ServerProc = Start-Process -FilePath "$Root\.venv\Scripts\python.exe" `
  -ArgumentList "-m", "clipsserver.main", "serve" `
  -WorkingDirectory $Root -PassThru

try {
  Write-Host "==> Iniciando Next.js Studio en http://127.0.0.1:3040 ..." -ForegroundColor Green
  Set-Location "$Root\apps\web"
  & npm.cmd run dev
} finally {
  if ($ServerProc -and !$ServerProc.HasExited) {
    Stop-Process -Id $ServerProc.Id -Force
  }
}
