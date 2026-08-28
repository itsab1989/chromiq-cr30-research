# Resume CR30 research on Windows. Prints state, then hands over to Claude Code.
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

Write-Host "=== chromiq-cr30-research @ $Repo ===" -ForegroundColor Cyan
Write-Host "`n--- git ---"; git log --oneline -5; git status --short
Write-Host "`n--- hardware lease ---"
if (Test-Path .hardware-lock\LEASE) { Get-Content .hardware-lock\LEASE } else { Write-Host "  free" }

Write-Host "`n--- device ---"
$dev = Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_1A86&PID_7523' }
if ($dev) {
    $dev | Format-Table -AutoSize Status, Class, FriendlyName, InstanceId
    if ($dev.Status -ne 'OK') {
        Write-Host "  Device present but not started. Record the exact error;" -ForegroundColor Yellow
        Write-Host "  a driver problem here is NOT a CR30 protocol problem." -ForegroundColor Yellow
    }
    Get-CimInstance Win32_SerialPort | Format-Table -AutoSize DeviceID, Description
} else {
    Write-Host "  VID_1A86&PID_7523 not present -- is the CR30 plugged into the VM?"
}

Write-Host "`n--- NOTE ---" -ForegroundColor Yellow
Write-Host "  USB works on macOS with no driver install. Windows is NOT on the"
Write-Host "  critical path for USB. Use it to sniff ColorQC2 for the undecoded"
Write-Host "  parameter commands, or to confirm portability -- see PLATFORM_SUPPORT.md."

Write-Host "`n--- STATUS.md (head) ---"; Get-Content STATUS.md -TotalCount 20
Write-Host "`n--- next experiment ---"
Select-String -Path SESSION_HANDOFF.md -Pattern '## Exact next experiment' -Context 0,14 |
    ForEach-Object { $_.Context.PostContext }

Write-Host "`n=== launching Claude Code ===" -ForegroundColor Cyan
claude "Read CLAUDE.md, STATUS.md and SESSION_HANDOFF.md in this repository in full before doing anything else, then follow the session start protocol in CLAUDE.md. Do not modify the ChromIQ repository."
