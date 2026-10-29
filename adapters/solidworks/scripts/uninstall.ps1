# Removes registration and this add-in's binaries; preserves drawings, models, and receipts.
$ErrorActionPreference = 'Stop'
if (Get-Process SLDWORKS -ErrorAction SilentlyContinue) { throw 'Close SOLIDWORKS before uninstalling.' }
$destination = Join-Path $env:ProgramFiles 'Gongke\SolidWorks'
$assembly = Join-Path $destination 'Gongke.SolidWorks.dll'
if (Test-Path -LiteralPath $assembly) {
    & (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe') $assembly /unregister
    if ($LASTEXITCODE -ne 0) { throw 'COM unregistration failed.' }
}
$guid = '{507DA194-5B1B-4B32-B4A8-B3EA18B036FA}'
foreach ($key in @("HKLM:\SOFTWARE\SolidWorks\Addins\$guid", "HKCU:\Software\SolidWorks\AddInsStartup\$guid")) {
    if (Test-Path $key) { Remove-Item $key -Recurse }
}
foreach ($name in @('Gongke.SolidWorks.dll','Newtonsoft.Json.dll')) {
    $path = Join-Path $destination $name
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path }
}
