param(
  [Parameter(Mandatory=$true)][string]$Server,
  [Parameter(Mandatory=$true)][string]$Token,
  [Parameter(Mandatory=$true)][string]$Destination
)

$ErrorActionPreference = 'Stop'
$AgentRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Launcher = (Get-Command py).Source
$VenvPython = Join-Path $AgentRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPython)) {
  & $Launcher -3.12 -m venv (Join-Path $AgentRoot '.venv')
}
& $VenvPython -m pip install -r (Join-Path $AgentRoot 'requirements.txt')
$TaskName = 'Postcards Studio Sync'
$Arguments = "`"$AgentRoot\agent.py`" --server `"$Server`" --token `"$Token`" --destination `"$Destination`" --application `"http://127.0.0.1:8787`" --interval 30"
$Action = New-ScheduledTaskAction -Execute $VenvPython -Argument $Arguments
$CurrentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $CurrentUser
# Запуск от текущего пользователя сохраняет доступ к NAS, выданный этому аккаунту.
$Principal = New-ScheduledTaskPrincipal -UserId $CurrentUser -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force
Write-Host "Installed scheduled task: $TaskName"
