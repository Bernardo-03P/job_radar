$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python do projeto não encontrado.' }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot '.runtime\automation-install.json'))) {
    throw 'Configure primeiro o cron existente do projeto.'
}
$taskName = 'JobRadar-Local-Startup'
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existingTask -and ($existingTask.Description -ne 'Managed by Job Radar local runtime')) {
    throw 'Já existe outra tarefa com este nome; ela não foi alterada.'
}
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$runtimePath = Join-Path $projectRoot '.runtime'
[IO.Directory]::CreateDirectory($runtimePath) | Out-Null
if ($existingTask) {
    Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $runtimePath 'startup-task-backup.xml') -Encoding Unicode
}
$safeUser = [System.Security.SecurityElement]::Escape($identity.User.Value)
$safePython = [System.Security.SecurityElement]::Escape($pythonPath)
$safeRoot = [System.Security.SecurityElement]::Escape($projectRoot)
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Managed by Job Radar local runtime</Description></RegistrationInfo>
  <Triggers><LogonTrigger><Repetition><Interval>PT15M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><Enabled>true</Enabled><UserId>$safeUser</UserId><Delay>PT30S</Delay></LogonTrigger></Triggers>
  <Principals><Principal id="Author"><UserId>$safeUser</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Enabled>true</Enabled><Hidden>true</Hidden></Settings>
  <Actions Context="Author"><Exec><Command>$safePython</Command><Arguments>-m agent.runtime --ensure --queue-due --watch</Arguments><WorkingDirectory>$safeRoot</WorkingDirectory></Exec></Actions>
</Task>
"@
$taskPath = Join-Path $runtimePath 'startup-task.xml'
$xml | Set-Content -LiteralPath $taskPath -Encoding Unicode
Register-ScheduledTask -TaskName $taskName -Xml $xml -Force | Select-Object TaskName, State
