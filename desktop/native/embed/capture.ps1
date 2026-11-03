param([string]$Output = (Join-Path $PSScriptRoot '../../../out/embed-capture'))
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CaptureDpi {
    [DllImport("user32.dll")] public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr value);
}
'@
$oldDpi = [CaptureDpi]::SetThreadDpiAwarenessContext([IntPtr](-4))
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bitmap = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
try {
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save((Join-Path $Output "$stamp.png"), [System.Drawing.Imaging.ImageFormat]::Png)
} finally { $graphics.Dispose(); $bitmap.Dispose() }
Get-Process | Where-Object { $_.ProcessName -in @('FreeCAD','SLDWORKS','Gongke.Embed','GongkeEmbedPrototype','electron','构想引擎') } |
    Select-Object Id, ProcessName, MainWindowHandle, MainWindowTitle, Responding |
    ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Output "$stamp-processes.json")
[CaptureDpi]::SetThreadDpiAwarenessContext($oldDpi) | Out-Null
Write-Output $Output
