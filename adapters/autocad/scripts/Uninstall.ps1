#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if (Get-Process acad -ErrorAction SilentlyContinue) { throw 'Close AutoCAD before uninstalling its native bridge.' }
$destination = Join-Path $env:ProgramFiles 'Autodesk\ApplicationPlugins\Gongke.AutoCAD.bundle'
if (Test-Path $destination) {
    [xml]$existing = Get-Content -Raw (Join-Path $destination 'PackageContents.xml')
    if ($existing.ApplicationPackage.UpgradeCode -ne '{E4667D19-4BD7-4A6F-A837-8C7312D91C80}') { throw 'Bundle identity mismatch.' }
    Remove-Item $destination -Recurse -Force
}
[ordered]@{ uninstalled = $true; user_drawings_preserved = $true } | ConvertTo-Json
