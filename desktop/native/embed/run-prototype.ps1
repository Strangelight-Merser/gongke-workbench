param([switch]$Fixture)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build.ps1') -Fixture:$Fixture
$desktop = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $desktop
try {
    if (!(Test-Path 'node_modules/electron')) { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci 失败' } }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw '桌面构建失败' }
    if ($Fixture) { $env:GONGKE_FREECAD_EXE = Join-Path $PSScriptRoot 'fixture/publish/FreeCAD.exe' }
    & './node_modules/.bin/electron.cmd' 'dist-electron/embed/prototype.cjs'
    if ($LASTEXITCODE -ne 0) { throw 'Electron 原型异常退出，请查看诊断目录' }
} finally { Pop-Location }
