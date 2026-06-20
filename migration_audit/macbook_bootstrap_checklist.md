# MacBook Bootstrap Checklist

- [ ] `git clone <repo-url>`
- [ ] `cd Retail-Trading-System`
- [ ] `python3 -m venv .venv`
- [ ] `source .venv/bin/activate`
- [ ] `python -m pip install --upgrade pip`
- [ ] `python -m pip install -r requirements.txt`
- [ ] inspect `MIGRATION_PLAN.md` before running rebuild commands
- [ ] export `STRUCTURAL_COMPOUNDING_LAB_ROOT` only if using an external structural-lab root on Mac
- [ ] run the BTC rebuild step
- [ ] run the artifact rebuild chain in order
- [ ] run `python -m unittest structural_compounding_lab.tests.test_fresh_btcusdt_data_updater -v`
- [ ] run `python -m unittest structural_compounding_lab.tests.test_shadow_forward_watchtower -v`
- [ ] run `python -m unittest structural_compounding_lab.tests.test_shadow_forward_pilot_automation -v`
- [ ] run `python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode self_check`
- [ ] run `python -m structural_compounding_lab.shadow_forward.shadow_forward_pilot_automation --mode daily_status`
- [ ] confirm no live, paper, order, or broker path exists
