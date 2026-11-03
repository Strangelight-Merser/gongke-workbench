$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'build.ps1') -Fixture
Push-Location (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
try {
    if (!(Test-Path 'node_modules/electron')) { npm ci; if ($LASTEXITCODE -ne 0) { throw 'npm ci 失败' } }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw '桌面构建失败' }
    node 'native/embed/test-windows.cjs'
    if ($LASTEXITCODE -ne 0) { throw '窗口冒烟失败，查看 out/embed-fixture/result.json' }
} finally { Pop-Location }
