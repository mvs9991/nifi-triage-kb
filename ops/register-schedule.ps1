# Registers Windows scheduled tasks (current user, no admin needed):
#   nifikb-build   refreshes the knowledge base every N minutes
#   nifikb-report  (optional) builds and sends the daily health report at a fixed time ([report] in nifikb.toml)
#
#   powershell -ExecutionPolicy Bypass -File ops\register-schedule.ps1 [-EveryMinutes 60] [-ReportAt 08:00]
# Remove with:  Unregister-ScheduledTask -TaskName nifikb-build -Confirm:$false  (same for nifikb-report)
param([int]$EveryMinutes = 60, [string]$ReportAt = "")

$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

$build = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot "build.cmd")
$every = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $EveryMinutes)
Register-ScheduledTask -TaskName "nifikb-build" -Action $build -Trigger $every -Settings $settings `
    -Description "Refresh the NiFi knowledge base (python -m nifikb build)" -Force | Out-Null
Write-Host "Scheduled nifikb-build every $EveryMinutes minutes."

if ($ReportAt) {
    $report = New-ScheduledTaskAction -Execute (Join-Path $PSScriptRoot "report.cmd")
    $daily = New-ScheduledTaskTrigger -Daily -At $ReportAt
    Register-ScheduledTask -TaskName "nifikb-report" -Action $report -Trigger $daily -Settings $settings `
        -Description "Daily NiFi health report (python -m nifikb report --send)" -Force | Out-Null
    Write-Host "Scheduled nifikb-report daily at $ReportAt."
}
Write-Host "Log: $(Join-Path $PSScriptRoot 'build.log')"
