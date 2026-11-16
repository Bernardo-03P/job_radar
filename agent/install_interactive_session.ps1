$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python do projeto não encontrado.' }
$taskName = 'JobRadar-Interactive-Session'
$description = 'Managed by Job Radar interactive idle session'
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $existing.Description -ne $description) { throw 'Outra tarefa usa este nome.' }
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-ScheduledTaskPrincipal -UserId $identity.User.Value -LogonType Interactive -RunLevel Limited
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument '-m agent.interactive_session --worker' -WorkingDirectory $projectRoot
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
# Sem gatilhos: só é iniciada por uma solicitação formal autenticada no helper.
Register-ScheduledTask -TaskName $taskName -Description $description -Action $action -Principal $principal -Settings $settings -Force | Select-Object TaskName,State
