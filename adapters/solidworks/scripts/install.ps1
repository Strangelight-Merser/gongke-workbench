# Run in an elevated 64-bit PowerShell after build.ps1. Does not launch SOLIDWORKS.
param([string]$BuildDirectory = (Join-Path $PSScriptRoot '..\bin\Release\net48'), [switch]$NoStartup)
$ErrorActionPreference = 'Stop'
if (![Environment]::Is64BitProcess) { throw 'Use 64-bit PowerShell.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (!(New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'COM add-in registration requires an elevated PowerShell.' }
if (Get-Process SLDWORKS -ErrorAction SilentlyContinue) { throw 'Close SOLIDWORKS before installing the add-in.' }
$destination = Join-Path $env:ProgramFiles 'Gongke\SolidWorks'
foreach ($name in @('Gongke.SolidWorks.dll','Newtonsoft.Json.dll')) {
    if (!(Test-Path -LiteralPath (Join-Path $BuildDirectory $name))) { throw "Build artifact missing: $name" }
}
New-Item -ItemType Directory -Force -Path $destination | Out-Null
foreach ($name in @('Gongke.SolidWorks.dll','Newtonsoft.Json.dll')) { Copy-Item -LiteralPath (Join-Path $BuildDirectory $name) -Destination $destination -Force }
$regasm = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe'
& $regasm (Join-Path $destination 'Gongke.SolidWorks.dll') /codebase
if ($LASTEXITCODE -ne 0) { throw 'COM registration failed.' }
$guid = '{507DA194-5B1B-4B32-B4A8-B3EA18B036FA}'
$addin = "HKLM:\SOFTWARE\SolidWorks\Addins\$guid"
New-Item -Force $addin | Out-Null
$registration = [Microsoft.Win32.Registry]::LocalMachine.OpenSubKey("SOFTWARE\SolidWorks\Addins\$guid", $true)
try { $registration.SetValue('', 0, [Microsoft.Win32.RegistryValueKind]::DWord) } finally { $registration.Dispose() }
New-ItemProperty $addin -Name Title -Value 'Gongke Workbench' -PropertyType String -Force | Out-Null
New-ItemProperty $addin -Name Description -Value 'Gongke native document and engineering command connection' -PropertyType String -Force | Out-Null
$startup = "HKCU:\Software\SolidWorks\AddInsStartup\$guid"
New-Item -Force $startup | Out-Null
$registration = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey("Software\SolidWorks\AddInsStartup\$guid", $true)
try { $registration.SetValue('', [int](!$NoStartup), [Microsoft.Win32.RegistryValueKind]::DWord) } finally { $registration.Dispose() }
Write-Host 'Installed. Open SOLIDWORKS and enable Gongke Workbench in Tools > Add-ins if it is not loaded.'
