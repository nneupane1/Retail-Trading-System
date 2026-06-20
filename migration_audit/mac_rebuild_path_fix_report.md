# Mac Rebuild Path Fix Report

## Detected project root

`/Users/mac/Documents/Retail-Trading-System`

Detection uses the optional `STRUCTURAL_COMPOUNDING_LAB_ROOT` override, the
current working directory, `git rev-parse --show-toplevel`, and pathlib parent
discovery. No Mac username or clone location is hardcoded in runtime code.

## Runnable files checked

- `structural_compounding_lab/common/project_paths.py`
- `structural_compounding_lab/config/settings.py`
- `structural_compounding_lab/shadow_forward/shadow_forward_observer.py`
- `structural_compounding_lab/shadow_forward/shadow_forward_watchtower.py`
- `structural_compounding_lab/shadow_forward/fresh_btcusdt_data_updater.py`
- `structural_compounding_lab/shadow_forward/shadow_forward_pilot_automation.py`
- `common/structural_lab_locator.py`
- `config/structural_compounding_lab_project.json`
- `tests/test_dashboard_telemetry.py`

## Paths fixed

- Removed the Windows-only external project root from
  `config/structural_compounding_lab_project.json`.
- Shadow-forward CLI package roots now resolve from the detected clone root.
- Relative CLI source, config, canonical, and output overrides now resolve from
  the detected clone root.
- The canonical BTCUSDT path resolves to
  `structural_compounding_lab/data_storage/BTCUSDT/1m/btcusdt_1m_canonical_shadow_forward.csv`.
- Missing updater state now reports that expected canonical path explicitly
  instead of treating an empty path as the current directory.
- Generated artifacts resolve below `structural_compounding_lab/output/`.
- Dashboard structural-lab discovery now prefers the explicit environment
  override, current Git clone, cwd parents, and local repository before a
  manifest fallback.
- Windows Task Scheduler inspection/install/remove is now guarded on non-Windows
  platforms, so Mac self-check and status commands do not invoke `schtasks`.
- Windows drive-letter fixtures in `tests/test_dashboard_telemetry.py` were
  replaced with platform-neutral pathlib values.
- The generic structural backtest CLI now resolves relative `--source-csv` and
  `--output-dir` values from the detected project root.

## Intentionally unchanged

- `structural_compounding_lab/docs/windows_task_scheduler_shadow_watchtower.md`
  is a Windows-specific historical/operator document.
- `migration_audit/windows_path_audit.csv` records the original Windows audit.
- Generated and historical reports under `structural_compounding_lab/output/`
  are not rewritten merely because they preserve Windows provenance.
- `scripts/generate_migration_audit.py` retains Windows patterns because its
  purpose is to detect those patterns.
- `data/downloader.py` retains a Windows/OneDrive diagnostic message because it
  is explanatory text, not an executable path.

## Verification

- Detected Git root: `/Users/mac/Documents/Retail-Trading-System`
- Python used: project `.venv311` (`3.11.15`)
- Project path tests: passed (`4`)
- Fresh BTCUSDT updater tests: passed (`6`)
- Shadow-forward watchtower tests: passed (`6`)
- Shadow-forward pilot automation tests: passed (`6`)
- Shadow-forward observer tests: passed (`3`)
- Dashboard and telemetry tests: passed (`15`)
- `git diff --check`: passed
- Root discovery from `/tmp` with the repository on `PYTHONPATH`: passed

Required operational commands both executed successfully from the Mac project
root:

```bash
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode self_check
python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status
```

The commands resolved all output paths beneath
`structural_compounding_lab/output/shadow_forward_pilot_automation_001/`.
Current self-check classification is `AUTOMATION_SELF_CHECK_PASSED`. Daily
status is `YELLOW` only because the scheduler has not been installed. The
canonical BTCUSDT tape is fresh through `2026-06-20T20:59:00`, has `273,420`
rows, and has zero gaps and zero duplicate timestamps.
`paper_validation_ready` remains `false`.
