from __future__ import annotations

from structural_compounding_lab.diagnostics.usdt_signal_usdc_execution_freeze_manifest import CLASSIFICATION, run


def test_usdt_signal_usdc_execution_freeze_manifest_gates_pass(tmp_path) -> None:
    manifest = run(tmp_path)
    assert manifest["final_classification"] == CLASSIFICATION
    assert manifest["frozen_allocator_candidate"]["variant_id"] == "early_two_1pct_each_total_2pct"
    assert manifest["frozen_allocator_candidate"]["max_total_open_risk_from_start"] == 0.02
    assert manifest["execution_guard"]["required_before_any_order_adapter"] is True
    assert manifest["execution_guard"]["latest_public_guard_order_sent"] is False
    assert manifest["real_money_allowed"] is False
    assert (tmp_path / "usdt_signal_usdc_execution_freeze_manifest.json").exists()
    assert (tmp_path / "USDT_SIGNAL_USDC_EXECUTION_FREEZE_REPORT.md").exists()
