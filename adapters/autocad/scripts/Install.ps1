#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [string]$AutoCADPath,
    [string]$PackageRoot = $PSScriptRoot
)
$ErrorActionPreference = 'Stop'
if (Get-Process acad -ErrorAction SilentlyContinue) {
    throw 'Close AutoCAD before installing its native bridge.'
}
if (-not $AutoCADPath) {
    $candidates = @(Get-ChildItem 'HKLM:\SOFTWARE\Autodesk\AutoCAD\R25.1' -ErrorAction SilentlyContinue |
        ForEach-Object { (Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue).AcadLocation } |
        Where-Object { $_ -and (Test-Path (Join-Path $_ 'acad.exe')) } | Select-Object -Unique)
    if ($candidates.Count -ne 1) { throw 'AutoCAD 2026 installation was not uniquely detected. The installer needs its installation path.' }
    $AutoCADPath = $candidates[0]
}
$exe = Join-Path $AutoCADPath 'acad.exe'
if (-not (Test-Path $exe)) { throw 'acad.exe not found at the detected installation.' }
$version = (Get-Item $exe).VersionInfo
if ($version.FileMajorPart -ne 25 -or $version.FileMinorPart -ne 1) {
    throw 'This bridge package targets Windows AutoCAD 2026 (R25.1).'
}
# Inspect the installed host assembly's TargetFrameworkAttribute without loading it
# into the installer process. The Autodesk 25.1.0/25.1.1 assemblies declare 8/10.
$hostAssembly = Join-Path $AutoCADPath 'AcMgd.dll'
if (-not (Test-Path $hostAssembly)) { throw 'Cannot verify AutoCAD runtime: AcMgd.dll is missing.' }
$assemblyData = [System.Text.Encoding]::UTF8.GetString([System.IO.File]::ReadAllBytes($hostAssembly))
$frameworkMarkers = [regex]::Matches($assemblyData, '\.NETCoreApp,Version=v(\d+)\.\d+')
$majors = @($frameworkMarkers | ForEach-Object { [int]$_.Groups[1].Value } | Select-Object -Unique)
if ($majors.Count -ne 1 -or $majors[0] -notin @(8, 10)) { throw 'AutoCAD runtime is unsupported or ambiguous.' }
$runtime = "net$($majors[0]).0-windows"
$source = Join-Path $PackageRoot "$runtime\Gongke.AutoCAD.bundle"
$manifest = Get-Content -Raw (Join-Path $PackageRoot 'build-manifest.json') | ConvertFrom-Json
$expected = @($manifest.packages | Where-Object { $_.runtime -eq $runtime })
if ($expected.Count -ne 1) { throw 'No matching compiled runtime package.' }
$dll = Join-Path $source 'Contents\Windows\Gongke.AutoCAD.Addin.dll'
if ((Get-FileHash $dll -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expected[0].sha256) { throw 'Native bridge package checksum mismatch.' }
$parent = Join-Path $env:ProgramFiles 'Autodesk\ApplicationPlugins'
$destination = Join-Path $parent 'Gongke.AutoCAD.bundle'
New-Item -ItemType Directory -Force $parent | Out-Null
if (Test-Path $destination) {
    [xml]$existing = Get-Content -Raw (Join-Path $destination 'PackageContents.xml')
    if ($existing.ApplicationPackage.UpgradeCode -ne '{E4667D19-4BD7-4A6F-A837-8C7312D91C80}') { throw 'Existing bundle does not belong to this product.' }
}
# Program Files ApplicationPlugins is trusted by AutoCAD; no security-variable changes.
Copy-Item $source $parent -Recurse -Force
[ordered]@{ installed = $true; bundle = $destination; runtime = $runtime; autocad_version = $version.FileVersion;
    host_tested = $false; next_step = 'Start AutoCAD and connect from the workbench.' } | ConvertTo-Json
