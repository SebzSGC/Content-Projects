$ErrorActionPreference = "Stop"
$root = "d:\rea-projects\vidforge"
$rt = Join-Path $root "runtime"
New-Item -ItemType Directory -Force -Path "$rt\uv", "$rt\ffmpeg", "$rt\python", "$rt\browsers" | Out-Null

# 1. Descargar uv portable (x86_64-pc-windows-msvc)
$uvExe = "$rt\uv\uv.exe"
if (-not (Test-Path $uvExe)) {
    Write-Host "Descargando uv portable..."
    $uvZip = "$rt\uv\uv.zip"
    Invoke-WebRequest -Uri "https://github.com/astral-sh/uv/releases/latest/download/uv-x86_64-pc-windows-msvc.zip" -OutFile $uvZip
    Expand-Archive -Path $uvZip -DestinationPath "$rt\uv" -Force
    Remove-Item $uvZip -Force
}
& $uvExe --version

# 2. Instalar Python 3.12 aislado en runtime/python
$env:UV_PYTHON_INSTALL_DIR = "$rt\python"
$env:UV_CACHE_DIR = "$rt\uv-cache"
Write-Host "Aprovisionando Python 3.12 aislado..."
& $uvExe python install 3.12

# 3. Descargar FFmpeg & FFprobe (BtbN GPL win64 shared/static con NVENC)
$ffmpegExe = "$rt\ffmpeg\ffmpeg.exe"
if (-not (Test-Path $ffmpegExe)) {
    Write-Host "Descargando FFmpeg portable con soporte NVENC..."
    $ffZip = "$rt\ffmpeg\ffmpeg.zip"
    Invoke-WebRequest -Uri "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip" -OutFile $ffZip
    Expand-Archive -Path $ffZip -DestinationPath "$rt\ffmpeg\extracted" -Force
    $binDir = Get-ChildItem "$rt\ffmpeg\extracted" -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1 -ExpandProperty DirectoryName
    Copy-Item "$binDir\ffmpeg.exe" "$rt\ffmpeg\ffmpeg.exe" -Force
    Copy-Item "$binDir\ffprobe.exe" "$rt\ffmpeg\ffprobe.exe" -Force
    Remove-Item "$rt\ffmpeg\extracted" -Recurse -Force
    Remove-Item $ffZip -Force
}
& $ffmpegExe -hide_banner -version | Select-Object -First 2

# 4. Detectar navegador local (Edge / Chrome) o Chrome Headless Shell
$edgePaths = @(
    "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe",
    "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe"
)
foreach ($p in $edgePaths) {
    if (Test-Path $p) {
        Write-Host "Navegador Chromium detectado para Headless: $p"
    }
}
