# Read-only diagnosis. Tokens and document contents are not printed.
$ErrorActionPreference = 'Stop'
$guid = '{507DA194-5B1B-4B32-B4A8-B3EA18B036FA}'
$hosts = Join-Path $env:LOCALAPPDATA 'Gongke\hosts'
$results = @()
if (Test-Path $hosts) {
    foreach ($file in Get-ChildItem -LiteralPath $hosts -Filter 'solidworks-*.json') {
        $endpoint = Get-Content -Raw -LiteralPath $file.FullName | ConvertFrom-Json
        $item = [ordered]@{ pid=$endpoint.pid; session_id=$endpoint.session_id; reachable=$false }
        $pipe = New-Object IO.Pipes.NamedPipeClientStream('.', $endpoint.pipe_name, [IO.Pipes.PipeDirection]::InOut)
        try {
            $pipe.Connect(3000)
            $writer = New-Object IO.StreamWriter($pipe, (New-Object Text.UTF8Encoding($false)))
            $writer.AutoFlush = $true
            $reader = New-Object IO.StreamReader($pipe)
            $writer.WriteLine((@{id='diagnose';method='host.info';params=@{};token=$endpoint.token} | ConvertTo-Json -Compress))
            $read = $reader.ReadLineAsync()
            if (!$read.Wait(15000)) { throw 'Host did not reach idle within 15 seconds.' }
            $reply = $read.Result | ConvertFrom-Json
            $item.reachable = [bool]$reply.result
            $item.response = $reply
        } catch { $item.error = $_.Exception.Message } finally { $pipe.Dispose() }
        $results += $item
    }
}
[ordered]@{ windows_64_bit=[Environment]::Is64BitOperatingSystem; powershell_64_bit=[Environment]::Is64BitProcess;
    addin_registered=(Test-Path "HKLM:\SOFTWARE\SolidWorks\Addins\$guid");
    host_processes=@(Get-Process SLDWORKS -ErrorAction SilentlyContinue | Select-Object Id,ProcessName);
    endpoints=$results; native_validation='not_run_by_this_diagnostic' } | ConvertTo-Json -Depth 12
