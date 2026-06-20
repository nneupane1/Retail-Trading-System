param(
  [switch]$ConfirmRemoveScheduler
)
if (-not $ConfirmRemoveScheduler) {
  Write-Error "Explicit confirmation required: -ConfirmRemoveScheduler"
  exit 1
}
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode remove_scheduler_task --confirm-remove-scheduler
