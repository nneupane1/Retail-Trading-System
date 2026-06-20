param(
  [switch]$ConfirmInstallScheduler
)
if (-not $ConfirmInstallScheduler) {
  Write-Error "Explicit confirmation required: -ConfirmInstallScheduler"
  exit 1
}
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode install_scheduler_task --confirm-install-scheduler
