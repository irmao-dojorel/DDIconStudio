# Gera dist\DDIconStudio (pasta portatil com o .exe, assets e icons) e dist\DDIconStudio-<versao>.zip.
# Uso: powershell -ExecutionPolicy Bypass -File scripts\build.ps1 [-Python caminho\python.exe]
param([string]$Python = (Join-Path $env:LOCALAPPDATA 'DDIconStudio\venv\Scripts\python.exe'))
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$versao = (Select-String -Path 'pyproject.toml' -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$dist = Join-Path $root 'dist'
$out = Join-Path $dist 'DDIconStudio'
foreach ($p in @($out, (Join-Path $root 'build'))) { if (Test-Path $p) { Remove-Item $p -Recurse -Force } }

& $Python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'pip falhou.' }
$Flet = Join-Path (Split-Path $Python -Parent) 'flet.exe'
& $Flet pack --yes --onedir --name DDIconStudio --distpath dist --icon assets\app_icon.ico `
    --product-name DDIconStudio --file-description "DDIconStudio - icones de vocacao (Dragon's Dogma 2)" `
    --product-version $versao --file-version "$versao.0" `
    --pyinstaller-build-args=--paths=src src\ddiconstudio\__main__.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller falhou.' }
Remove-Item (Join-Path $root 'build'), (Join-Path $root 'DDIconStudio.spec') -Recurse -Force -ErrorAction SilentlyContinue

# assets de fabrica ao lado do .exe (editaveis); as bibliotecas do usuario vao vazias.
# referencias\, tools\, tests\, icons\ e config.json nao entram no pacote.
$bibliotecas = 'silhuetas', 'padroes_banner'
New-Item -ItemType Directory -Force (Join-Path $out 'assets') | Out-Null
Get-ChildItem (Join-Path $root 'assets') | Where-Object { $bibliotecas -notcontains $_.Name } |
    Copy-Item -Destination (Join-Path $out 'assets') -Recurse -Force
foreach ($b in $bibliotecas) { New-Item -ItemType Directory -Force (Join-Path $out "assets\$b") | Out-Null }
New-Item -ItemType Directory -Force (Join-Path $out 'icons') | Out-Null
Copy-Item (Join-Path $root 'LEIA-ME.txt') $out -Force

$zip = Join-Path $dist "DDIconStudio-$versao.zip"
if (Test-Path $zip) { Remove-Item $zip }
# o antivirus costuma travar por alguns segundos os arquivos recem-criados pelo PyInstaller
for ($tentativa = 1; ; $tentativa++) {
    try { Compress-Archive -Path $out -DestinationPath $zip -Force; break }
    catch { if ($tentativa -ge 5) { throw }; Start-Sleep -Seconds 5 }
}
"Pacote: $out"
"Zip:    $zip"
