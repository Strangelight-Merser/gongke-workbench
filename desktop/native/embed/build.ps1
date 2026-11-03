param([switch]$Fixture)
$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot 'Gongke.Embed.csproj'
dotnet publish $project -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o (Join-Path $PSScriptRoot 'publish')
if ($LASTEXITCODE -ne 0) { throw 'Windows 窗口组件构建失败' }
if ($Fixture) {
    dotnet publish (Join-Path $PSScriptRoot 'fixture/Fixture.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -o (Join-Path $PSScriptRoot 'fixture/publish')
    if ($LASTEXITCODE -ne 0) { throw '替身窗口构建失败' }
}
