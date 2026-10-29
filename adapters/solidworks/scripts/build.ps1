param([string]$InteropDirectory = "$env:ProgramFiles\SOLIDWORKS Corp\SOLIDWORKS\api\redist")
$ErrorActionPreference = 'Stop'
$project = Join-Path $PSScriptRoot '..\Gongke.SolidWorks.csproj'
foreach ($name in @('sldworks','swconst','swpublished')) {
    $path = Join-Path $InteropDirectory "SolidWorks.Interop.$name.dll"
    if (!(Test-Path -LiteralPath $path)) { throw "Missing official SOLIDWORKS reference: $path. Pass -InteropDirectory from the installed api/redist folder." }
}
if (!(Get-Command dotnet -ErrorAction SilentlyContinue)) { throw 'Install Microsoft .NET SDK 8, then rerun this script.' }
& dotnet build $project -c Release "-p:SolidWorksInteropDir=$InteropDirectory" --nologo
if ($LASTEXITCODE -ne 0) { throw 'SOLIDWORKS add-in build failed.' }
& dotnet run --project (Join-Path $PSScriptRoot '..\tests\ProtocolChecks.csproj') -c Release
if ($LASTEXITCODE -ne 0) { throw 'Protocol checks failed.' }
Write-Host 'Build complete. This does not verify execution in SOLIDWORKS.'
