$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$setup = @(Get-ChildItem "$root/desktop/release/gongke-*-windows-x64-setup.exe")
if ($setup.Count -ne 1) { throw 'Expected one NSIS installer' }
$install = Join-Path $env:RUNNER_TEMP '中文 安装目录/构想引擎'
$p = Start-Process -FilePath $setup[0].FullName -ArgumentList @('/S', '/allusers', "/D=$install") -Wait -PassThru
if ($p.ExitCode -ne 0) { throw "NSIS failed: $($p.ExitCode)" }
$exe = Join-Path $install '构想引擎.exe'
if (!(Test-Path -LiteralPath $exe)) { throw 'Installed executable missing' }
# 使用真实本地账户及 LoadUserProfile，不能把 USERPROFILE 环境变量冒充中文用户名。
$username = '学生验收'
$password = [guid]::NewGuid().ToString('N') + '!aA9'
$secure = ConvertTo-SecureString $password -AsPlainText -Force
New-LocalUser -Name $username -Password $secure -AccountNeverExpires | Out-Null
Add-LocalGroupMember -Group (Get-LocalGroup -SID 'S-1-5-32-545') -Member $username
$credential = [pscredential]::new("$env:COMPUTERNAME\$username", $secure)
$evidence = Join-Path $root 'out/installer-validation'
New-Item -ItemType Directory -Force $evidence | Out-Null
# CI checkout、安装路径和证据目录明确授予此测试账户；不修改系统或用户其他目录权限。
foreach ($directory in @($root, $install, $evidence)) {
    & icacls $directory /grant "${username}:(OI)(CI)M" /T /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot grant acceptance account access' }
}
$node = (Get-Command node.exe).Source
$script = Join-Path $evidence 'run.ps1'
@"
`$ErrorActionPreference = 'Stop'
`$env:USERNAME = [Environment]::UserName
`$env:USERPROFILE = [Environment]::GetFolderPath('UserProfile')
`$env:APPDATA = [Environment]::GetFolderPath('ApplicationData')
`$env:LOCALAPPDATA = [Environment]::GetFolderPath('LocalApplicationData')
`$env:GONGKE_TEST_EXECUTABLE = '$($exe.Replace("'", "''"))'
`$env:GONGKE_INSTALL_EVIDENCE = '$($evidence.Replace("'", "''"))'
& '$($node.Replace("'", "''"))' '$($root.Replace("'", "''"))/desktop/tests/windows-installed.cjs' *> '$($evidence.Replace("'", "''"))/acceptance.log'
exit `$LASTEXITCODE
"@ | Set-Content -LiteralPath $script -Encoding utf8BOM
try {
    Start-Service seclogon
    $test = Start-Process powershell.exe -Credential $credential -LoadUserProfile -WorkingDirectory $evidence -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', "`"$script`"") -PassThru
    if (!$test.WaitForExit(300000)) { Stop-Process -Id $test.Id; throw 'Installed acceptance exceeded five minutes' }
    if ($test.ExitCode -ne 0) { throw "Installed acceptance failed: $($test.ExitCode); see $evidence" }
    $result = Get-Content "$evidence/result.json" -Raw | ConvertFrom-Json
    if (!$result.ok) { throw 'Installed acceptance did not pass' }
} finally {
    Remove-LocalUser -Name $username
}
