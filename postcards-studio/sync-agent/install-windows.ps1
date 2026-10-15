param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$Token,
  [Parameter(Mandatory=$true)][string]$Destination,
  [string]$Application = ''
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ResolvedDestination = [System.IO.Path]::GetFullPath($Destination)
if (-not (Test-Path -LiteralPath $ResolvedDestination -PathType Container)) {
  New-Item -ItemType Directory -Path $ResolvedDestination -Force | Out-Null
}
$Launcher = (Get-Command py).Source
$VenvPython = Join-Path $AgentRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
  & $Launcher -3.12 -m venv (Join-Path $AgentRoot '.venv')
}
& $VenvPython -m pip install -r (Join-Path $AgentRoot 'requirements.txt')
$TaskName = 'Postcards Studio Sync'
$ConfigRoot = Join-Path $env:LOCALAPPDATA 'PostcardsStudio'
New-Item -ItemType Directory -Path $ConfigRoot -Force | Out-Null
$TokenFile = Join-Path $ConfigRoot 'sync-token'
[System.IO.File]::WriteAllText($TokenFile, $Token, [System.Text.UTF8Encoding]::new($false))
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $TokenFile /inheritance:r /grant:r "${CurrentUser}:(R)" | Out-Null
$Arguments = "`"$AgentRoot\agent.py`" --server `"$Server`" --token-file `"$TokenFile`" --destination `"$ResolvedDestination`" --application `"$Application`" --interval 30"
$Action = New-ScheduledTaskAction -Execute $VenvPython -Argument $Arguments
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
# Запуск от текущего пользователя сохраняет доступ к NAS, выданный этому аккаунту.
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
Write-Host "Installed scheduled task: $TaskName"
Write-Host "Release destination: $ResolvedDestination"
