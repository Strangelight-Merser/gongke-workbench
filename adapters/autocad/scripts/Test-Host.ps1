# Developer/field acceptance runner. Uses a generated fixture and new paths only.
# It does not launch AutoCAD or execute arbitrary CAD command strings.
#Requires -Version 5.1
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$FixtureDxf,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$HostDescriptor
)
$ErrorActionPreference = 'Stop'
$FixtureDxf = (Resolve-Path $FixtureDxf).Path
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
if (-not $HostDescriptor) {
    $descriptors = @(Get-ChildItem (Join-Path $env:LOCALAPPDATA 'Gongke\hosts\autocad-*.json') -ErrorAction SilentlyContinue)
    if ($descriptors.Count -ne 1) { throw 'Choose one running AutoCAD host descriptor.' }
    $HostDescriptor = $descriptors[0].FullName
}
$hostInfo = Get-Content -Raw $HostDescriptor | ConvertFrom-Json
$records = New-Object System.Collections.Generic.List[object]
function Invoke-Bridge([string]$Method, [hashtable]$Parameters) {
    $requestId = [guid]::NewGuid().ToString('N')
    # 发送前保留原 ID，即使超时也能从 evidence 查询，不能另发新 ID。
    $record = @{ request_id=$requestId; method=$Method; params=$Parameters; response=$null }
    $records.Add($record)
    $pipe = New-Object System.IO.Pipes.NamedPipeClientStream('.', $hostInfo.pipe_name, [System.IO.Pipes.PipeDirection]::InOut)
    try {
        $pipe.Connect(5000)
        $reader = New-Object System.IO.StreamReader($pipe, [System.Text.Encoding]::UTF8)
        $encoding = New-Object System.Text.UTF8Encoding($false)
        $writer = New-Object System.IO.StreamWriter($pipe, $encoding)
        $writer.AutoFlush = $true
        $request = @{ id=$requestId; token=$hostInfo.token; method=$Method; params=$Parameters }
        $writer.WriteLine(($request | ConvertTo-Json -Depth 20 -Compress))
        $read = $reader.ReadLineAsync()
        if (-not $read.Wait(30000)) { throw 'Host response timeout; inspect operation.status before any retry.' }
        $response = $read.Result | ConvertFrom-Json
        if ($response.id -ne $requestId) { throw 'Protocol request ID mismatch.' }
        $record.response = $response
        return $response
    } finally { $pipe.Dispose() }
}
function Result([object]$Response) {
    if ($Response.error) { throw ($Response.error | ConvertTo-Json -Compress) }
    return $Response.result
}
function Op { return [guid]::NewGuid().ToString('N') }
$before = (Get-FileHash $FixtureDxf -Algorithm SHA256).Hash
$imported = Join-Path $OutputDirectory ('imported-' + (Op) + '.dwg')
$copy = Join-Path $OutputDirectory ('revision-' + (Op) + '.dwg')
$evidence = Join-Path $OutputDirectory ('host-evidence-' + (Op) + '.json')
$passed = $false
try {
    $description = Result (Invoke-Bridge 'host.describe' @{})
    $importParams = @{operation_id=(Op); source_path=$FixtureDxf; target_path=$imported}
    $importResult = Result (Invoke-Bridge 'drawing.import_dxf' $importParams)
    $duplicate = Result (Invoke-Bridge 'drawing.import_dxf' $importParams)
    if ($duplicate.status -ne 'completed' -or $duplicate.response.result.path -ne $imported) { throw 'Duplicate import did not return durable receipt.' }
    $importedHash = (Get-FileHash $imported -Algorithm SHA256).Hash
    # 同指纹、不同路径的未登记副本不获得原生写权限。
    $unregistered = Join-Path $OutputDirectory ('unregistered-' + (Op) + '.dwg')
    Copy-Item $imported $unregistered
    $original = Result (Invoke-Bridge 'document.open' @{operation_id=(Op); path=$unregistered})
    $originalSnapshot = Result (Invoke-Bridge 'document.snapshot' @{document_id=$original.document_id})
    $originalText = @($originalSnapshot.entities | Where-Object {$_.type -eq 'TEXT'})[0]
    $denied = Invoke-Bridge 'drawing.edit_text' @{operation_id=(Op); document_id=$original.document_id;
        expected_revision=$originalSnapshot.revision; handle=$originalText.handle; text='MUST_NOT_BE_APPLIED'}
    if ($denied.error.code -ne 'working_copy_required') { throw 'Native original protection failed.' }
    $document = Result (Invoke-Bridge 'document.open' @{operation_id=(Op); path=$imported})
    if (-not $document.is_working_copy -or $document.fingerprint -ne $importResult.native_fingerprint) { throw 'Imported native identity/permission mismatch.' }
    $snapshot = Result (Invoke-Bridge 'document.snapshot' @{document_id=$document.document_id})
    foreach ($kind in @('LINE','LWPOLYLINE','CIRCLE','ARC','TEXT','MTEXT','DIMENSION')) {
        if (@($snapshot.entities | Where-Object {$_.type -eq $kind}).Count -lt 1) { throw "Missing native entity: $kind" }
    }
    $text = @($snapshot.entities | Where-Object {$_.type -eq 'TEXT' -and $_.text -eq 'GONGKE_NATIVE_FIXTURE'})[0]
    if (-not $text) { throw 'Synthetic text target not found.' }
    $edit = Result (Invoke-Bridge 'drawing.edit_text' @{operation_id=(Op); document_id=$document.document_id;
        expected_revision=$snapshot.revision; handle=$text.handle; text='GONGKE_NATIVE_EDIT_VERIFIED'})
    if ($edit.entity.text -ne 'GONGKE_NATIVE_EDIT_VERIFIED') { throw 'Text readback mismatch.' }
    $stale = Invoke-Bridge 'drawing.edit_text' @{operation_id=(Op); document_id=$document.document_id;
        expected_revision=$snapshot.revision; handle=$text.handle; text='MUST_NOT_BE_APPLIED'}
    if ($stale.error.code -ne 'stale_snapshot') { throw 'Stale snapshot was not rejected.' }
    $snapshot = Result (Invoke-Bridge 'document.snapshot' @{document_id=$document.document_id})
    $dimension = @($snapshot.entities | Where-Object {$_.type -eq 'DIMENSION'})[0]
    $position = @(($dimension.text_position[0] + 5), ($dimension.text_position[1] + 5), $dimension.text_position[2])
    $move = Result (Invoke-Bridge 'drawing.move_dimension_text' @{operation_id=(Op); document_id=$document.document_id;
        expected_revision=$snapshot.revision; handle=$dimension.handle; position=$position})
    if ($move.entity.measurement -ne $dimension.measurement -or $move.entity.text_override -ne $dimension.text_override) { throw 'Dimension measurement/override changed.' }
    $snapshot = Result (Invoke-Bridge 'document.snapshot' @{document_id=$document.document_id})
    Result (Invoke-Bridge 'document.save_copy' @{operation_id=(Op); document_id=$document.document_id;
        expected_revision=$snapshot.revision; target_path=$copy}) | Out-Null
    if ((Get-FileHash $imported -Algorithm SHA256).Hash -ne $importedHash) { throw 'Original DWG was overwritten.' }
    $reopened = Result (Invoke-Bridge 'document.open' @{operation_id=(Op); path=$copy})
    $final = Result (Invoke-Bridge 'document.snapshot' @{document_id=$reopened.document_id})
    if (@($final.entities | Where-Object {$_.type -eq 'TEXT' -and $_.text -eq 'GONGKE_NATIVE_EDIT_VERIFIED'}).Count -ne 1) { throw 'Saved text did not persist.' }
    $finalDimension = @($final.entities | Where-Object {$_.type -eq 'DIMENSION'})[0]
    if ($finalDimension.measurement -ne $dimension.measurement -or $finalDimension.text_override -ne $dimension.text_override) { throw 'Saved dimension measurement/override mismatch.' }
    for ($index=0; $index -lt 3; $index++) {
        if ([math]::Abs($finalDimension.text_position[$index] - $position[$index]) -gt 1e-8) { throw 'Saved dimension text position mismatch.' }
    }
    if ((Get-FileHash $unregistered -Algorithm SHA256).Hash -ne $importedHash) { throw 'Unregistered drawing was overwritten.' }
    if ((Get-FileHash $FixtureDxf -Algorithm SHA256).Hash -ne $before) { throw 'DXF source changed.' }
    $passed = $true
} finally {
    # No discovery token or user drawing contents are included outside the synthetic fixture results.
    @{ passed=$passed; level='target_host'; host=$description; fixture=$FixtureDxf; new_dwg=$copy;
       records=$records; native_undo_verified=$false; manual_edit_verified=$false } |
       ConvertTo-Json -Depth 40 | Set-Content -Encoding UTF8 $evidence
    Write-Output $evidence
}
