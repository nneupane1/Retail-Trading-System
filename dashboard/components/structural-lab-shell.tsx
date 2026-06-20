"use client";

import { useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import useSWR from "swr";
import clsx from "clsx";
import {
  ArrowRight,
  BarChart3,
  CandlestickChart,
  Database,
  Layers3,
  Settings2,
  ShieldAlert,
  Vault,
  Waves,
} from "lucide-react";
import { CandlePanel } from "@/components/candle-panel";
import { MiniLineChart } from "@/components/mini-line-chart";
import { TradeFrequencyPnlPanel, type TradeFrequencyPnlPayload } from "@/components/trade-frequency-pnl-panel";

type StructuralView =
  | "overview"
  | "market-replay"
  | "structure-map"
  | "profit-vault"
  | "trade-review"
  | "settings";

type Row = Record<string, any>;

type StructuralSnapshot = {
  lab: {
    name: string;
    root_path: string;
    output_path: string;
    has_run: boolean;
    empty_state?: string | null;
  };
  summary: Record<string, any>;
  summary_metrics: Record<string, any>;
  settings: Record<string, any>;
  symbols_config: Record<string, any>;
  profit_vault: Record<string, any>;
  report_markdown: string;
  artifact_freshness: Record<string, Record<string, any>>;
  available_symbols: string[];
  available_timeframes: string[];
  trade_rows: Row[];
  trade_frequency_pnl?: TradeFrequencyPnlPayload;
  setup_rows: Row[];
  level_rows: Row[];
  liquidity_rows: Row[];
  cooldown_rows: Row[];
  pyramiding_rows: Row[];
  equity_rows: Row[];
  overview: {
    base_capital: number;
    active_trading_capital: number;
    locked_profit: number;
    floating_profit: number;
    current_equity: number;
    current_compounding_cycle: string;
    cooldown_state: string;
    total_return_pct: number;
    max_drawdown_pct: number;
    win_rate: number;
    profit_factor: number;
    profit_lock_count?: number;
    add_on_event_count?: number;
    cooldown_release_count?: number;
    r_multiple_summary: string;
  };
  structural_state?: {
    latest_trade?: Row;
    latest_setup?: Row;
    latest_cooldown_event?: Row;
    latest_pyramiding_event?: Row;
  };
  chart_points: {
    equity: Array<{ label?: string; value: number }>;
    locked_profit: Array<{ label?: string; value: number }>;
  };
  daily_structural_opportunity?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    top_opportunity_by_day?: Row[];
    candidate_rows?: Row[];
    participation_distribution?: Record<string, any>;
    sr_zone_report?: Record<string, any>;
    breakout_retest_report?: Record<string, any>;
    missed_report?: Record<string, any>;
    too_tight_report?: Record<string, any>;
    noise_chasing_report?: Record<string, any>;
    high_r_report?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  five_year_full_capital_audit?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    long_short_breakdown?: Row[];
    monthly_summary?: Row[];
    asymmetric_payoff?: Record<string, any>;
    moonshot_contribution?: Record<string, any>;
    scaling_safety?: Record<string, any>;
    failure_modes?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  long_short_edge_repair?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    long_edge_breakdown?: Row[];
    short_edge_breakdown?: Row[];
    archetype_expectancy_breakdown?: Row[];
    personality_expectancy_breakdown?: Row[];
    long_failure_modes?: Row[];
    short_success_modes?: Row[];
    moonshot_repeatability?: Row[];
    moonshot_dependency?: Record<string, any>;
    long_filters_research_candidates?: Record<string, any>;
    short_preservation_rules?: Record<string, any>;
    edge_repair_recommendation?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  long_damage_control_patch?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    patch_variant_summary?: Row[];
    patch_variant_trade_replay?: Row[];
    disabled_long_archetype_impact?: Row[];
    preserved_short_edge_impact?: Row[];
    moonshot_dependency_after_patch?: Record<string, any>;
    full_capital_compounding_after_patch?: Row[];
    drawdown_after_patch?: Row[];
    best_patch_candidate?: Record<string, any>;
    rejected_patch_candidates?: Row[] | Record<string, any>;
    research_only_patch_recommendation?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  frozen_patch_validation?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    frozen_patch_rules?: Record<string, any>;
    validation_window_summary?: Row[];
    year_by_year_validation?: Row[];
    regime_validation_summary?: Row[];
    walk_forward_validation?: Row[];
    out_of_sample_validation?: Row[];
    frozen_patch_trade_replay?: Row[];
    full_active_capital_validation_curve?: Row[];
    drawdown_validation_report?: Row[];
    moonshot_dependency_validation?: Record<string, any>;
    long_short_validation_breakdown?: Row[];
    validation_failure_modes?: Row[];
    promotion_gate_report?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  frozen_patch_forensic_integrity?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    artifact_lineage?: Record<string, any>;
    data_coverage?: Record<string, any>;
    sample_reuse?: Record<string, any>;
    leakage_risk?: Record<string, any>;
    frozen_rule_origin?: Record<string, any>;
    source_history_availability?: Record<string, any>;
    validation_gap?: Record<string, any>;
    required_next_replay_plan?: Record<string, any>;
    no_go_risks?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  broad_historical_structural_replay?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    source_data_coverage?: Record<string, any>;
    replay_window_manifest?: Record<string, any>;
    yearly_trade_counts?: Row[];
    monthly_trade_counts?: Row[];
    replay_health_report?: Record<string, any>;
    replay_failure_report?: Record<string, any>;
    data_gap_report?: Record<string, any>;
    no_future_leakage_checks?: Record<string, any>;
    generated_ledger_manifest?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  broad_frozen_patch_validation?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    raw_vs_patch?: Record<string, any>;
    raw_vs_patch_rows?: Row[];
    yearly_raw_vs_patch?: Row[];
    monthly_raw_vs_patch?: Row[];
    long_short_raw_vs_patch?: Record<string, any>;
    archetype_raw_vs_patch?: Row[];
    disabled_trade_impact?: Row[];
    preserved_trade_impact?: Row[];
    moonshot_dependency?: Record<string, any>;
    execution_cost_sensitivity?: Record<string, any>;
    drawdown_comparison?: Row[];
    profit_vault_comparison?: Record<string, any>;
    patch_survival_by_year?: Record<string, any>;
    no_go_risks?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  native_sr_aware_strict_stress_monte_carlo?: {
    summary?: Record<string, any>;
    status?: Record<string, any>;
    report_markdown?: string;
    frozen_variant?: Record<string, any>;
    pf_42_sanity?: Record<string, any>;
    pre_entry_rule_integrity?: Record<string, any>;
    stress_test_matrix?: Row[];
    rolling_5y_stress_summary?: Row[];
    monte_carlo_summary?: Record<string, any>;
    monte_carlo_distribution?: Row[];
    monte_carlo_drawdown_distribution?: Row[];
    mission_gap_report?: Record<string, any>;
    promotion_gate_report?: Record<string, any>;
    monte_carlo_ruin_risk?: Record<string, any>;
    next_research_recommendation?: Record<string, any>;
    metadata?: Record<string, any>;
  };
  warnings: string[];
};

const API_URL = process.env.NEXT_PUBLIC_DASHBOARD_API_URL ?? "http://127.0.0.1:8000";

const VIEWS: Array<{
  key: StructuralView;
  label: string;
  href: string;
  icon: React.ReactNode;
  eyebrow: string;
}> = [
  {
    key: "overview",
    label: "Overview",
    href: "/structural-lab",
    icon: <BarChart3 className="h-4 w-4" />,
    eyebrow: "capital rhythm",
  },
  {
    key: "market-replay",
    label: "Market Replay",
    href: "/structural-lab/market-replay",
    icon: <CandlestickChart className="h-4 w-4" />,
    eyebrow: "candle theatre",
  },
  {
    key: "structure-map",
    label: "Structure Map",
    href: "/structural-lab/structure-map",
    icon: <Layers3 className="h-4 w-4" />,
    eyebrow: "levels and liquidity",
  },
  {
    key: "profit-vault",
    label: "Profit Vault",
    href: "/structural-lab/profit-vault",
    icon: <Vault className="h-4 w-4" />,
    eyebrow: "compounding discipline",
  },
  {
    key: "trade-review",
    label: "Trade Review",
    href: "/structural-lab/trade-review",
    icon: <Waves className="h-4 w-4" />,
    eyebrow: "forensics tape",
  },
  {
    key: "settings",
    label: "Settings",
    href: "/structural-lab/settings",
    icon: <Settings2 className="h-4 w-4" />,
    eyebrow: "research config",
  },
];

const fetcher = async <T,>(url: string): Promise<T> => {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
};

function formatMoney(value: unknown) {
  return new Intl.NumberFormat("en-DE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 2,
  }).format(Number(value ?? 0));
}

function formatPct(value: unknown, digits = 2) {
  return `${(Number(value ?? 0) * 100).toFixed(digits)}%`;
}

function formatTime(value: unknown) {
  if (!value) {
    return "n/a";
  }
  const asDate = new Date(String(value));
  if (Number.isNaN(asDate.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(asDate);
}

function toneForArtifact(status: string | undefined) {
  if (status === "healthy") {
    return "border-emerald-400/20 bg-emerald-400/10 text-emerald-200";
  }
  if (status === "stale" || status === "missing") {
    return "border-orange-400/20 bg-orange-400/10 text-orange-200";
  }
  return "border-white/10 bg-white/5 text-white/70";
}

function EmptyState({
  title,
  body,
}: {
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[28px] border border-dashed border-white/14 bg-white/5 px-5 py-10 text-center">
      <div className="text-lg font-semibold text-white">{title}</div>
      <p className="mx-auto mt-3 max-w-2xl text-sm leading-7 text-white/62">{body}</p>
    </div>
  );
}

function Section({
  eyebrow,
  title,
  children,
  className,
}: {
  eyebrow: string;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section
      className={clsx(
        "relative overflow-hidden rounded-[30px] border border-white/10 bg-[linear-gradient(180deg,rgba(10,16,30,0.88),rgba(7,11,23,0.78))] p-5 shadow-[0_24px_80px_rgba(5,10,28,0.32)]",
        className,
      )}
    >
      <div className="mb-4">
        <div className="text-[11px] uppercase tracking-[0.3em] text-cyan-200/72">{eyebrow}</div>
        <h2 className="mt-2 text-xl font-semibold text-white">{title}</h2>
      </div>
      {children}
    </section>
  );
}

function MetricCard({
  label,
  value,
  subtext,
  tone = "cyan",
}: {
  label: string;
  value: string;
  subtext?: string;
  tone?: "cyan" | "green" | "orange";
}) {
  const toneClass =
    tone === "green"
      ? "border-emerald-300/22 bg-[linear-gradient(180deg,rgba(9,45,38,0.72),rgba(8,20,23,0.9))]"
      : tone === "orange"
        ? "border-orange-300/22 bg-[linear-gradient(180deg,rgba(52,31,18,0.78),rgba(24,16,21,0.92))]"
        : "border-cyan-300/22 bg-[linear-gradient(180deg,rgba(8,45,62,0.72),rgba(7,19,34,0.9))]";
  return (
    <div className={clsx("rounded-[24px] border px-4 py-4", toneClass)}>
      <div className="text-[10px] uppercase tracking-[0.28em] text-white/55">{label}</div>
      <div className="mt-3 text-3xl font-semibold text-white">{value}</div>
      {subtext ? <div className="mt-2 text-sm text-white/60">{subtext}</div> : null}
    </div>
  );
}

function TableEmpty({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm text-white/58">
      {message}
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="overflow-x-auto rounded-[24px] border border-white/10 bg-[#040915] p-4 text-xs leading-6 text-white/72">
      {JSON.stringify(value ?? {}, null, 2)}
    </pre>
  );
}

export function StructuralLabShell({
  view = "overview",
}: {
  view?: StructuralView;
}) {
  const { data, error, isLoading } = useSWR<StructuralSnapshot>(
    `${API_URL}/api/structural-lab/snapshot`,
    fetcher,
    { refreshInterval: 10000, revalidateOnFocus: false },
  );

  const availableSymbols = data?.available_symbols?.length ? data.available_symbols : ["BTCUSDT"];
  const availableTimeframes = data?.available_timeframes?.length ? data.available_timeframes : ["1h", "4h", "12h", "1d"];
  const [symbol, setSymbol] = useState("BTCUSDT");
  const [timeframe, setTimeframe] = useState("1h");

  const selectedSymbol = availableSymbols.includes(symbol) ? symbol : availableSymbols[0];
  const selectedTimeframe = availableTimeframes.includes(timeframe) ? timeframe : availableTimeframes[0];
  const overview = data?.overview;
  const warningList = data?.warnings ?? [];
  const activeView = VIEWS.find((item) => item.key === view) ?? VIEWS[0];
  const compactHero = view !== "overview";
  const tradeRows = data?.trade_rows ?? [];
  const levelRows = data?.level_rows ?? [];
  const liquidityRows = data?.liquidity_rows ?? [];
  const setupRows = data?.setup_rows ?? [];
  const cooldownRows = data?.cooldown_rows ?? [];
  const pyramidingRows = data?.pyramiding_rows ?? [];
  const latestTrade = tradeRows[tradeRows.length - 1] ?? null;
  const latestSetup = setupRows[setupRows.length - 1] ?? null;
  const latestCooldownEvent = data?.structural_state?.latest_cooldown_event ?? null;
  const latestPyramidingEvent = data?.structural_state?.latest_pyramiding_event ?? null;
  const dailyOpportunity = data?.daily_structural_opportunity;
  const dailyOpportunitySummary = dailyOpportunity?.summary ?? {};
  const dailyOpportunityRows = dailyOpportunity?.top_opportunity_by_day ?? [];
  const dailyOpportunityMetadata = dailyOpportunity?.metadata ?? {};
  const fiveYearAudit = data?.five_year_full_capital_audit;
  const fiveYearSummary = fiveYearAudit?.summary ?? {};
  const fiveYearMetadata = fiveYearAudit?.metadata ?? {};
  const fiveYearBreakdown = fiveYearAudit?.long_short_breakdown ?? [];
  const fiveYearMoonshot = fiveYearAudit?.moonshot_contribution ?? {};
  const fiveYearScalingSafety = fiveYearAudit?.scaling_safety ?? {};
  const fiveYearFailureModes = fiveYearAudit?.failure_modes ?? {};
  const longShortRepair = data?.long_short_edge_repair;
  const longShortRepairSummary = longShortRepair?.summary ?? {};
  const longShortRepairRecommendation = longShortRepair?.edge_repair_recommendation ?? {};
  const longShortRepairArchetypes = longShortRepair?.archetype_expectancy_breakdown ?? [];
  const longDamageControlPatch = data?.long_damage_control_patch;
  const longDamageControlPatchSummary = longDamageControlPatch?.summary ?? {};
  const longDamageControlPatchBest = longDamageControlPatch?.best_patch_candidate ?? {};
  const longDamageControlPatchVariants = longDamageControlPatch?.patch_variant_summary ?? [];
  const frozenPatchValidation = data?.frozen_patch_validation;
  const frozenPatchValidationSummary = frozenPatchValidation?.summary ?? {};
  const frozenPatchPromotionGate = frozenPatchValidation?.promotion_gate_report ?? {};
  const frozenPatchValidationWindows = frozenPatchValidation?.validation_window_summary ?? [];
  const frozenPatchYearRows = frozenPatchValidation?.year_by_year_validation ?? [];
  const frozenPatchWalkForward = frozenPatchValidation?.walk_forward_validation ?? [];
  const frozenPatchForensicIntegrity = data?.frozen_patch_forensic_integrity;
  const frozenPatchForensicSummary = frozenPatchForensicIntegrity?.summary ?? {};
  const frozenPatchForensicLineage = frozenPatchForensicIntegrity?.artifact_lineage ?? {};
  const frozenPatchForensicCoverage = frozenPatchForensicIntegrity?.data_coverage ?? {};
  const frozenPatchForensicSampleReuse = frozenPatchForensicIntegrity?.sample_reuse ?? {};
  const frozenPatchForensicLeakage = frozenPatchForensicIntegrity?.leakage_risk ?? {};
  const frozenPatchForensicGap = frozenPatchForensicIntegrity?.validation_gap ?? {};
  const frozenPatchForensicNextReplay = frozenPatchForensicIntegrity?.required_next_replay_plan ?? {};
  const frozenPatchForensicNoGoRisks = frozenPatchForensicIntegrity?.no_go_risks ?? {};
  const broadHistoricalReplay = data?.broad_historical_structural_replay;
  const broadHistoricalReplaySummary = broadHistoricalReplay?.summary ?? {};
  const broadHistoricalReplayCoverage = broadHistoricalReplay?.source_data_coverage ?? {};
  const broadHistoricalReplayHealth = broadHistoricalReplay?.replay_health_report ?? {};
  const broadHistoricalReplayLeakage = broadHistoricalReplay?.no_future_leakage_checks ?? {};
  const broadHistoricalReplayManifest = broadHistoricalReplay?.generated_ledger_manifest ?? {};
  const broadFrozenPatchValidation = data?.broad_frozen_patch_validation;
  const broadFrozenPatchSummary = broadFrozenPatchValidation?.summary ?? {};
  const broadFrozenPatchRawVsPatch = broadFrozenPatchValidation?.raw_vs_patch ?? {};
  const broadFrozenPatchYearly = broadFrozenPatchValidation?.yearly_raw_vs_patch ?? [];
  const broadFrozenPatchMoonshot = broadFrozenPatchValidation?.moonshot_dependency ?? {};
  const broadFrozenPatchExecution = broadFrozenPatchValidation?.execution_cost_sensitivity ?? {};
  const broadFrozenPatchNoGo = broadFrozenPatchValidation?.no_go_risks ?? {};
  const nativeStrictStress = data?.native_sr_aware_strict_stress_monte_carlo;
  const nativeStrictStressSummary = nativeStrictStress?.summary ?? {};
  const nativeStrictStressFrozen = nativeStrictStress?.frozen_variant ?? {};
  const nativeStrictStressPf = nativeStrictStress?.pf_42_sanity ?? {};
  const nativeStrictStressIntegrity = nativeStrictStress?.pre_entry_rule_integrity ?? {};
  const nativeStrictStressMonteCarlo = nativeStrictStress?.monte_carlo_summary ?? {};
  const nativeStrictStressMissionGap = nativeStrictStress?.mission_gap_report ?? {};
  const nativeStrictStressPromotion = nativeStrictStress?.promotion_gate_report ?? {};
  const nativeStrictStressNextStep = nativeStrictStress?.next_research_recommendation ?? {};
  const nativeStrictStressMeta = nativeStrictStress?.metadata ?? {};
  const nativeStrictStressReferenceMode =
    nativeStrictStressSummary?.monte_carlo_reference_mode && nativeStrictStressMonteCarlo?.modes
      ? nativeStrictStressMonteCarlo.modes[nativeStrictStressSummary.monte_carlo_reference_mode] ?? {}
      : {};

  const latestArtifacts = useMemo(() => {
    const freshness = data?.artifact_freshness ?? {};
    return Object.entries(freshness);
  }, [data?.artifact_freshness]);

  const overviewContent = (
    <div className="grid gap-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Base Capital"
          value={formatMoney(overview?.base_capital)}
          subtext="Research base that future cycles reset back to after profit locking."
        />
        <MetricCard
          label="Active Trading Capital"
          value={formatMoney(overview?.active_trading_capital)}
          subtext={`Cycle ${overview?.current_compounding_cycle ?? "cycle-0"}`}
          tone="green"
        />
        <MetricCard
          label="Locked Profit"
          value={formatMoney(overview?.locked_profit)}
          subtext="Protected vault capital that is not automatically re-risked."
          tone="orange"
        />
        <MetricCard
          label="Floating Profit"
          value={formatMoney(overview?.floating_profit)}
          subtext={`Cooldown ${overview?.cooldown_state ?? "inactive"}`}
          tone="cyan"
        />
      </div>

      <Section eyebrow="Native strict validation" title="Native SR-Aware Strict Stress + Monte Carlo">
        {nativeStrictStressMeta?.read_only && nativeStrictStressSummary?.variant_name ? (
          <div className="grid gap-4 xl:grid-cols-[1.1fr_0.9fr]">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              <MetricCard
                label="Frozen variant"
                value={String(nativeStrictStressFrozen?.variant_name ?? nativeStrictStressSummary?.variant_name ?? "n/a")}
                subtext={`${nativeStrictStressFrozen?.trade_count ?? nativeStrictStressSummary?.trade_count ?? 0} trades`}
              />
              <MetricCard
                label="PF sanity"
                value={String(nativeStrictStressPf?.classification ?? nativeStrictStressSummary?.pf_sanity_verdict ?? "n/a")}
                subtext={`reported PF ${Number(nativeStrictStressFrozen?.profit_factor ?? nativeStrictStressSummary?.normal_profit_factor ?? 0).toFixed(2)}`}
                tone="orange"
              />
              <MetricCard
                label="Integrity"
                value={String(nativeStrictStressIntegrity?.classification ?? nativeStrictStressSummary?.pre_entry_integrity_verdict ?? "n/a")}
                subtext="pre-entry only / read-only research"
                tone="green"
              />
              <MetricCard
                label="Normal equity"
                value={formatMoney(nativeStrictStressSummary?.normal_ending_equity)}
                subtext={`DD ${formatPct(nativeStrictStressSummary?.normal_max_drawdown_pct ?? 0)}`}
                tone="green"
              />
              <MetricCard
                label="MC p50"
                value={formatMoney(nativeStrictStressReferenceMode?.median_ending_equity)}
                subtext={`p25 ${formatMoney(nativeStrictStressReferenceMode?.p25_ending_equity)}`}
              />
              <MetricCard
                label="MC > €1M"
                value={formatPct(nativeStrictStressReferenceMode?.probability_end_above_1m ?? 0)}
                subtext={`> €500k ${formatPct(nativeStrictStressReferenceMode?.probability_end_above_500k ?? 0)}`}
                tone="cyan"
              />
            </div>
            <div className="grid gap-4">
              <div className="rounded-[24px] border border-white/10 bg-white/5 px-4 py-4 text-sm leading-7 text-white/68">
                <div className="text-[10px] uppercase tracking-[0.28em] text-cyan-200/72">Promotion gate</div>
                <div className="mt-3 text-lg font-semibold text-white">
                  {String(nativeStrictStressPromotion?.classification ?? nativeStrictStressSummary?.promotion_gate_classification ?? "n/a")}
                </div>
                <div className="mt-3 text-white/62">
                  Mission gap: {String(nativeStrictStressMissionGap?.verdict ?? nativeStrictStressSummary?.mission_gap_verdict ?? "n/a")}
                </div>
                <div className="mt-3 text-white/62">
                  Ruin risk: {formatPct(nativeStrictStressReferenceMode?.probability_ruin_or_equity_below_50pct_start ?? 0)}
                </div>
                <div className="mt-3 text-white/62">
                  Next action: {String(nativeStrictStressNextStep?.next_action ?? nativeStrictStressSummary?.next_research_action ?? "n/a")}
                </div>
              </div>
              <div className="rounded-[24px] border border-white/10 bg-white/5 px-4 py-4 text-sm leading-7 text-white/68">
                <div className="text-[10px] uppercase tracking-[0.28em] text-cyan-200/72">Reference mode</div>
                <div className="mt-3 text-white/62">
                  {String(nativeStrictStressSummary?.monte_carlo_reference_mode ?? "monthly_block_bootstrap")}
                </div>
                <div className="mt-2 text-white/62">
                  Simulations {String(nativeStrictStressSummary?.monte_carlo_simulation_count ?? 0)}
                </div>
                <div className="mt-2 text-white/62">
                  Rolling 5Y avg {formatMoney(nativeStrictStressSummary?.rolling_5y_average_ending_equity)}
                </div>
              </div>
            </div>
          </div>
        ) : (
          <TableEmpty message="No native strict stress + Monte Carlo audit found yet." />
        )}
      </Section>

      <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <Section eyebrow="Compounding curve" title="Equity And Vault Rhythm">
          {data?.chart_points?.equity?.length ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <div className="mb-2 text-sm text-white/62">Equity curve</div>
                <MiniLineChart points={data.chart_points.equity} tone="cyan" className="h-[210px]" />
              </div>
              <div>
                <div className="mb-2 text-sm text-white/62">Locked-profit progression</div>
                <MiniLineChart
                  points={data.chart_points.locked_profit.length ? data.chart_points.locked_profit : [{ value: 0 }, { value: 0 }]}
                  tone="orange"
                  className="h-[210px]"
                />
              </div>
            </div>
          ) : (
            <EmptyState
              title="No structural backtest run found yet"
              body="Once equity.csv and profit_vault.json exist, this panel will show the compounding curve, the protected-vault staircase, and the reset points between cycles."
            />
          )}
        </Section>

        <Section eyebrow="Validation summary" title="Structural KPI Stack">
          <div className="grid gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/50">Total return</div>
              <div className="mt-2 text-2xl font-semibold text-white">{formatPct(overview?.total_return_pct)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/50">Max drawdown</div>
              <div className="mt-2 text-2xl font-semibold text-white">{formatPct(overview?.max_drawdown_pct)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/50">Win rate</div>
              <div className="mt-2 text-2xl font-semibold text-white">{formatPct(overview?.win_rate)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/50">Profit factor</div>
              <div className="mt-2 text-2xl font-semibold text-white">{Number(overview?.profit_factor ?? 0).toFixed(2)}</div>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/66">
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/50">R multiple summary</div>
              <div className="mt-2 leading-6">{overview?.r_multiple_summary ?? "No R-multiple summary yet."}</div>
            </div>
          </div>
        </Section>
      </div>

      <Section eyebrow="5-Year Full Capital Audit" title="Long/Short Full Active Capital Compounding">
        {Object.keys(fiveYearSummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <MetricCard
                label="Classification"
                value={String(fiveYearSummary.compounding_readiness_classification ?? "n/a")}
                subtext={fiveYearMetadata.classification ?? "research-only"}
                tone={
                  String(fiveYearSummary.compounding_readiness_classification ?? "").includes("NOT_READY")
                    ? "orange"
                    : "green"
                }
              />
              <MetricCard
                label="Ending capital"
                value={formatMoney(fiveYearSummary.ending_capital_under_full_active_capital_model)}
                subtext={`Start ${formatMoney(fiveYearSummary.starting_capital)}`}
                tone="green"
              />
              <MetricCard
                label="5Y conservative"
                value={formatMoney(fiveYearSummary.projected_5_year_capital_conservative)}
                subtext="40% of observed average monthly return"
              />
              <MetricCard
                label="5Y base case"
                value={formatMoney(fiveYearSummary.projected_5_year_capital_base_case)}
                subtext="Observed median monthly return"
                tone="green"
              />
              <MetricCard
                label="5Y aggressive"
                value={formatMoney(fiveYearSummary.projected_5_year_capital_aggressive)}
                subtext={fiveYearSummary.projection_is_extrapolation ? "extrapolation, not proof" : "research projection"}
                tone="orange"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <MetricCard label="Max drawdown" value={formatPct(fiveYearSummary.max_drawdown_pct)} subtext={formatMoney(fiveYearSummary.max_drawdown_eur)} tone="orange" />
              <MetricCard label="Worst day" value={formatMoney(fiveYearSummary.worst_day_pnl)} subtext={`${Number(fiveYearSummary.worst_day_R ?? 0).toFixed(2)}R`} tone="orange" />
              <MetricCard label="Best day" value={formatMoney(fiveYearSummary.best_day_pnl)} subtext={`${Number(fiveYearSummary.best_day_R ?? 0).toFixed(2)}R`} tone="green" />
              <MetricCard label="Trades / active day" value={String(Number(fiveYearSummary.average_trades_per_active_day ?? 0).toFixed(2))} subtext={`${String(fiveYearSummary.average_trades_per_day ?? 0)} per day`} />
              <MetricCard label="Moonshots 5R+" value={String(fiveYearSummary.moonshot_5R_plus_count ?? 0)} subtext={`${String(fiveYearSummary.moonshot_8R_plus_count ?? 0)} / ${String(fiveYearSummary.moonshot_10R_plus_count ?? 0)} at 8R+ / 10R+`} tone="green" />
              <MetricCard label="3 wins cover 7 losses" value={fiveYearSummary.can_3_winners_cover_7_losers ? "yes" : "no"} subtext={`moonshot pct ${formatPct(fiveYearSummary.moonshot_profit_contribution_pct)}`} tone={fiveYearSummary.can_3_winners_cover_7_losers ? "green" : "orange"} />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Direction contribution" title="Long / Short Expectancy Split" className="p-0">
                {fiveYearBreakdown.length ? (
                  <div className="overflow-x-auto px-5 py-5">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-white/45">
                        <tr>
                          <th className="pb-3 pr-4 font-medium">Side</th>
                          <th className="pb-3 pr-4 font-medium">Trades</th>
                          <th className="pb-3 pr-4 font-medium">Win rate</th>
                          <th className="pb-3 pr-4 font-medium">Avg R</th>
                          <th className="pb-3 pr-4 font-medium">Total R</th>
                          <th className="pb-3 pr-4 font-medium">PF</th>
                          <th className="pb-3 pr-4 font-medium">5R+ / 8R+ / 10R+</th>
                        </tr>
                      </thead>
                      <tbody>
                        {fiveYearBreakdown.map((row, index) => (
                          <tr key={`${row.side ?? index}`} className="border-t border-white/6">
                            <td className="py-3 pr-4 font-medium text-white">{String(row.side ?? "n/a").toUpperCase()}</td>
                            <td className="py-3 pr-4 text-white/68">{row.trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{formatPct(row.win_rate)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.avg_R ?? 0).toFixed(3)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.total_R ?? 0).toFixed(3)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.profit_factor ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4 text-white/68">
                              {String(row.moonshot_5R_plus_count ?? 0)} / {String(row.moonshot_8R_plus_count ?? 0)} / {String(row.moonshot_10R_plus_count ?? 0)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <TableEmpty message="No 5-year long/short compounding breakdown available yet." />
                )}
              </Section>

              <div className="grid gap-5">
                <Section eyebrow="Compounding safety" title="Survival / Vault / Cooldown">
                  <div className="grid gap-3">
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      full-capital survival: <span className="font-medium text-white">{fiveYearSummary.whether_full_active_capital_model_survives_observed_trade_sequence ? "true" : "false"}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      cooldown count: <span className="font-medium text-white">{String(fiveYearSummary.cooldown_count ?? 0)}</span> | profit locks: <span className="font-medium text-white">{String(fiveYearSummary.profit_lock_count ?? 0)}</span>
                    </div>
                    <div className="rounded-2xl border border-cyan-400/18 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100">
                      profit vault delta vs no-vault: {formatMoney(fiveYearScalingSafety.profit_vault_delta_vs_no_vault_eur ?? 0)} | no-vault ending {formatMoney(fiveYearScalingSafety.ending_equity_without_profit_vault ?? 0)}
                    </div>
                    <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 text-sm text-orange-100">
                      longest loss streak {String(fiveYearScalingSafety.longest_loss_streak ?? 0)} | longest stop streak {String(fiveYearScalingSafety.longest_stop_streak ?? 0)}
                    </div>
                  </div>
                </Section>

                <Section eyebrow="Payoff geometry" title="Few Winners Vs Many Losses">
                  <div className="grid gap-3">
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      moonshot contribution: <span className="font-medium text-white">{formatPct(fiveYearMoonshot.moonshot_profit_contribution_pct ?? fiveYearSummary.moonshot_profit_contribution_pct)}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      few winners covered many losses: <span className="font-medium text-white">{String(fiveYearAudit?.asymmetric_payoff?.few_winners_cover_many_losses_count ?? 0)}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      moonshot-saved blocks: <span className="font-medium text-white">{String(fiveYearAudit?.asymmetric_payoff?.moonshot_saved_block_count ?? 0)}</span>
                    </div>
                    <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 text-sm text-orange-100">
                      failure warnings: {(fiveYearFailureModes.warnings ?? []).length ? String((fiveYearFailureModes.warnings ?? []).join(" | ")) : "none"}
                    </div>
                  </div>
                </Section>
              </div>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No 5-year full-capital audit found yet"
            body="Once `five_year_compounding_audit_001` exists, this section will show the full active-capital long/short replay curve, directional contribution, moonshot dependence, and whether a few high-R winners can overpower frequent -1R losses."
          />
        )}
      </Section>

      <Section eyebrow="Long vs Short Edge Repair Audit" title="Directional Edge Forensics">
        {Object.keys(longShortRepairSummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <MetricCard
                label="Long total R"
                value={Number(longShortRepairSummary.long_total_R ?? 0).toFixed(2)}
                subtext={`PF ${Number(longShortRepairSummary.long_profit_factor ?? 0).toFixed(2)}`}
                tone="orange"
              />
              <MetricCard
                label="Short total R"
                value={Number(longShortRepairSummary.short_total_R ?? 0).toFixed(2)}
                subtext={`PF ${Number(longShortRepairSummary.short_profit_factor ?? 0).toFixed(2)}`}
                tone="green"
              />
              <MetricCard
                label="Long win rate"
                value={formatPct(longShortRepairSummary.long_win_rate)}
                subtext={`${String(longShortRepairSummary.long_trade_count ?? 0)} trades`}
                tone="orange"
              />
              <MetricCard
                label="Short win rate"
                value={formatPct(longShortRepairSummary.short_win_rate)}
                subtext={`${String(longShortRepairSummary.short_trade_count ?? 0)} trades`}
                tone="green"
              />
              <MetricCard
                label="Moonshot contribution"
                value={formatPct(longShortRepairSummary.moonshot_profit_contribution_pct_of_net)}
                subtext={`${String(longShortRepairSummary.moonshot_5R_plus_count ?? 0)} at 5R+`}
                tone="orange"
              />
              <MetricCard
                label="Next patch"
                value={String(longShortRepairSummary.recommended_next_research_patch ?? "n/a")}
                subtext="research-only recommendation"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-[24px] border border-emerald-300/20 bg-emerald-400/10 px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.22em] text-emerald-100/72">Best long archetype</div>
                <div className="mt-3 text-sm leading-6 text-white">{String(longShortRepairSummary.best_long_archetype ?? "n/a")}</div>
              </div>
              <div className="rounded-[24px] border border-orange-300/20 bg-orange-400/10 px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.22em] text-orange-100/72">Worst long archetype</div>
                <div className="mt-3 text-sm leading-6 text-white">{String(longShortRepairSummary.worst_long_archetype ?? "n/a")}</div>
              </div>
              <div className="rounded-[24px] border border-emerald-300/20 bg-emerald-400/10 px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.22em] text-emerald-100/72">Best short archetype</div>
                <div className="mt-3 text-sm leading-6 text-white">{String(longShortRepairSummary.best_short_archetype ?? "n/a")}</div>
              </div>
              <div className="rounded-[24px] border border-orange-300/20 bg-orange-400/10 px-4 py-4">
                <div className="text-[10px] uppercase tracking-[0.22em] text-orange-100/72">Worst short archetype</div>
                <div className="mt-3 text-sm leading-6 text-white">{String(longShortRepairSummary.worst_short_archetype ?? "n/a")}</div>
              </div>
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Patch guidance" title="Read-only recommendation" className="p-0">
                <div className="space-y-3 px-5 py-5 text-sm text-white/68">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">Current problem</div>
                    <div className="mt-2 leading-6 text-white/80">{String(longShortRepairRecommendation.current_problem ?? "n/a")}</div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">Recommended patch</div>
                    <div className="mt-2 text-lg font-semibold text-cyan-100">{String(longShortRepairRecommendation.recommended_next_research_patch ?? "n/a")}</div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 leading-7">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">Moonshot stress</div>
                    <div className="mt-2">
                      Profit without moonshots: {formatMoney(longShortRepairSummary.profit_without_moonshots)}<br />
                      10R+ capped to 5R: {formatMoney(longShortRepairSummary.profit_with_10R_plus_capped_to_5R)}<br />
                      All 5R+ capped to 3R: {formatMoney(longShortRepairSummary.profit_with_all_5R_plus_capped_to_3R)}
                    </div>
                  </div>
                </div>
              </Section>

              <Section eyebrow="Expectancy map" title="Top archetype breakdown" className="p-0">
                {longShortRepairArchetypes.length ? (
                  <div className="overflow-x-auto px-5 py-5">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-white/45">
                        <tr>
                          <th className="pb-3 pr-4 font-medium">Side</th>
                          <th className="pb-3 pr-4 font-medium">Pullback</th>
                          <th className="pb-3 pr-4 font-medium">Personality</th>
                          <th className="pb-3 pr-4 font-medium">Trades</th>
                          <th className="pb-3 pr-4 font-medium">Total R</th>
                          <th className="pb-3 pr-4 font-medium">Label</th>
                        </tr>
                      </thead>
                      <tbody>
                        {longShortRepairArchetypes.slice(0, 10).map((row, index) => (
                          <tr key={`${row.side ?? "n/a"}-${row.pullback_type ?? "n/a"}-${index}`} className="border-t border-white/6">
                            <td className="py-3 pr-4 font-medium text-white">{String(row.side ?? "n/a").toUpperCase()}</td>
                            <td className="py-3 pr-4 text-white/68">{row.pullback_type ?? "n/a"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.personality_label ?? "n/a"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.total_R ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4 text-white/68">{row.expectancy_label ?? "n/a"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <TableEmpty message="No long-vs-short edge repair audit has been generated yet." />
                )}
              </Section>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No long-vs-short edge repair audit found yet"
            body="Once `long_short_edge_repair_audit_001` exists, this section will show the asymmetric expectancy split, moonshot dependency stress, the best and worst archetypes on both sides, and the next research-only repair patch."
          />
        )}
      </Section>

      <Section eyebrow="Long Damage Control Patch Audit" title="Short Preservation / Long Damage Control">
        {Object.keys(longDamageControlPatchSummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <MetricCard
                label="Best patch candidate"
                value={String(longDamageControlPatchSummary.best_patch_candidate ?? "n/a")}
                subtext={String(longDamageControlPatchSummary.recommended_research_only_patch ?? "research-only")}
                tone="green"
              />
              <MetricCard
                label="Baseline ending capital"
                value={formatMoney(longDamageControlPatchSummary.baseline_ending_capital)}
                subtext={`PF ${Number(longDamageControlPatchSummary.baseline_profit_factor ?? 0).toFixed(2)}`}
                tone="orange"
              />
              <MetricCard
                label="Best patch ending capital"
                value={formatMoney(longDamageControlPatchSummary.best_patch_ending_capital)}
                subtext={`PF ${Number(longDamageControlPatchSummary.best_patch_profit_factor ?? 0).toFixed(2)}`}
                tone="green"
              />
              <MetricCard
                label="Baseline max DD"
                value={formatPct(longDamageControlPatchSummary.baseline_max_drawdown_pct)}
                subtext={`R ${Number(longDamageControlPatchSummary.baseline_total_R ?? 0).toFixed(2)}`}
                tone="orange"
              />
              <MetricCard
                label="Best patch max DD"
                value={formatPct(longDamageControlPatchSummary.best_patch_max_drawdown_pct)}
                subtext={`R ${Number(longDamageControlPatchSummary.best_patch_total_R ?? 0).toFixed(2)}`}
                tone="green"
              />
              <MetricCard
                label="Moonshot dependency"
                value={String(longDamageControlPatchSummary.moonshot_dependency_after_patch ?? "n/a")}
                subtext={String(longDamageControlPatchSummary.readiness_classification_after_patch ?? "n/a")}
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Long R removed"
                value={Number(longDamageControlPatchSummary.long_R_removed ?? 0).toFixed(2)}
                subtext="drag removed by patch"
                tone="green"
              />
              <MetricCard
                label="Short R preserved"
                value={Number(longDamageControlPatchSummary.short_R_preserved ?? 0).toFixed(2)}
                subtext={`${String(longDamageControlPatchBest.short_edge_preserved_pct ?? "n/a")} baseline share`}
                tone="green"
              />
              <MetricCard
                label="Trade count after patch"
                value={String(longDamageControlPatchSummary.trade_count_after_patch ?? 0)}
                subtext={`profit sans moonshots ${formatMoney(longDamageControlPatchSummary.profit_without_moonshots_after_patch)}`}
              />
              <MetricCard
                label="Readiness after patch"
                value={String(longDamageControlPatchSummary.readiness_classification_after_patch ?? "n/a")}
                subtext="research-only classification"
                tone="cyan"
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Patch recommendation" title="Read-only candidate view" className="p-0">
                <div className="space-y-3 px-5 py-5 text-sm text-white/68">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">Recommended patch</div>
                    <div className="mt-2 text-lg font-semibold text-cyan-100">
                      {String(longDamageControlPatchSummary.recommended_research_only_patch ?? "n/a")}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 leading-7">
                    Baseline ending capital: {formatMoney(longDamageControlPatchSummary.baseline_ending_capital)}<br />
                    Best patch ending capital: {formatMoney(longDamageControlPatchSummary.best_patch_ending_capital)}<br />
                    Baseline PF: {Number(longDamageControlPatchSummary.baseline_profit_factor ?? 0).toFixed(2)}<br />
                    Best patch PF: {Number(longDamageControlPatchSummary.best_patch_profit_factor ?? 0).toFixed(2)}
                  </div>
                  <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 leading-7 text-orange-100">
                    This is diagnostic-only replay. No strategy, paper, live, allocator, or config mutation is exposed here.
                  </div>
                </div>
              </Section>

              <Section eyebrow="Variant scoreboard" title="Patch variants" className="p-0">
                {longDamageControlPatchVariants.length ? (
                  <div className="overflow-x-auto px-5 py-5">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-white/45">
                        <tr>
                          <th className="pb-3 pr-4 font-medium">Variant</th>
                          <th className="pb-3 pr-4 font-medium">Trades</th>
                          <th className="pb-3 pr-4 font-medium">End cap</th>
                          <th className="pb-3 pr-4 font-medium">PF</th>
                          <th className="pb-3 pr-4 font-medium">Max DD</th>
                          <th className="pb-3 pr-4 font-medium">Dependency</th>
                        </tr>
                      </thead>
                      <tbody>
                        {longDamageControlPatchVariants.map((row, index) => (
                          <tr key={`${row.variant_name ?? index}`} className="border-t border-white/6">
                            <td className="py-3 pr-4 font-medium text-white">{row.variant_name ?? "n/a"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{formatMoney(row.ending_capital)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.profit_factor ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4 text-white/68">{formatPct(row.max_drawdown_pct)}</td>
                            <td className="py-3 pr-4 text-white/68">{row.moonshot_dependency_label ?? "n/a"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <TableEmpty message="No long damage control patch audit has been generated yet." />
                )}
              </Section>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No long damage control patch audit found yet"
            body="Once `long_damage_control_patch_audit_001` exists, this section will compare baseline versus research-only long-filter / short-preservation patch variants, including compounding, drawdown, and moonshot dependency."
          />
        )}
      </Section>

      <Section eyebrow="Frozen Patch Multi-Year Validation" title="Frozen Patch Proof Audit">
        {Object.keys(frozenPatchValidationSummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
              <MetricCard
                label="Frozen patch candidate"
                value={String(frozenPatchValidationSummary.frozen_patch_candidate ?? "n/a")}
                subtext={String(frozenPatchValidationSummary.promotion_gate_classification ?? "research-only")}
                tone="green"
              />
              <MetricCard
                label="Current sample end cap"
                value={formatMoney(longDamageControlPatchSummary.best_patch_ending_capital)}
                subtext="patch-audit sample"
                tone="cyan"
              />
              <MetricCard
                label="Validation ending capital"
                value={formatMoney(frozenPatchValidationSummary.validation_ending_capital)}
                subtext={`${String(frozenPatchValidationSummary.validation_window_count ?? 0)} validation windows`}
                tone="green"
              />
              <MetricCard
                label="Pass / fail windows"
                value={`${String(frozenPatchValidationSummary.year_window_pass_count ?? 0)} / ${String(frozenPatchValidationSummary.year_window_fail_count ?? 0)}`}
                subtext="year-by-year labels"
                tone="cyan"
              />
              <MetricCard
                label="Worst validation DD"
                value={formatPct(frozenPatchValidationSummary.max_validation_drawdown)}
                subtext={String(frozenPatchValidationSummary.worst_validation_window ?? "n/a")}
                tone="orange"
              />
              <MetricCard
                label="Walk-forward pass rate"
                value={formatPct(frozenPatchValidationSummary.walk_forward_pass_rate)}
                subtext={String(frozenPatchPromotionGate.classification ?? "n/a")}
                tone="cyan"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Best validation window"
                value={String(frozenPatchValidationSummary.best_validation_window ?? "n/a")}
                subtext={String(frozenPatchValidationSummary.recommended_next_action ?? "n/a")}
                tone="green"
              />
              <MetricCard
                label="Worst validation window"
                value={String(frozenPatchValidationSummary.worst_validation_window ?? "n/a")}
                subtext={String(frozenPatchValidationSummary.patch_appears_overfit ? "overfit risk flagged" : "overfit risk not dominant")}
                tone="orange"
              />
              <MetricCard
                label="Moonshot dependency"
                value={String(frozenPatchValidationSummary.moonshot_dependency_in_validation ?? "n/a")}
                subtext={`sans moonshots ${formatMoney(frozenPatchValidationSummary.profit_without_moonshots_in_validation)}`}
                tone="cyan"
              />
              <MetricCard
                label="Promotion gate"
                value={String(frozenPatchValidationSummary.promotion_gate_classification ?? "n/a")}
                subtext="read-only research gate"
                tone="orange"
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Frozen rules" title="Candidate and gate truth" className="p-0">
                <div className="space-y-3 px-5 py-5 text-sm text-white/68">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">Promotion gate classification</div>
                    <div className="mt-2 text-lg font-semibold text-cyan-100">{String(frozenPatchPromotionGate.classification ?? "n/a")}</div>
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 leading-7">
                    Validation ending capital: {formatMoney(frozenPatchValidationSummary.validation_ending_capital)}<br />
                    Walk-forward pass rate: {formatPct(frozenPatchValidationSummary.walk_forward_pass_rate)}<br />
                    True unseen proof available: {String(frozenPatchPromotionGate.true_unseen_proof_available ?? false)}
                  </div>
                  <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 leading-7 text-orange-100">
                    Diagnostic-only validation. No live, paper, runtime, allocator, or config mutation is exposed here.
                  </div>
                </div>
              </Section>

              <Section eyebrow="Validation scoreboard" title="Year and window outcomes" className="p-0">
                {frozenPatchYearRows.length || frozenPatchValidationWindows.length ? (
                  <div className="overflow-x-auto px-5 py-5">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-white/45">
                        <tr>
                          <th className="pb-3 pr-4 font-medium">Window</th>
                          <th className="pb-3 pr-4 font-medium">Trades</th>
                          <th className="pb-3 pr-4 font-medium">End cap</th>
                          <th className="pb-3 pr-4 font-medium">PF</th>
                          <th className="pb-3 pr-4 font-medium">Max DD</th>
                          <th className="pb-3 pr-4 font-medium">Label</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[...frozenPatchValidationWindows, ...frozenPatchYearRows.slice(0, 6)].map((row, index) => (
                          <tr key={`${row.window_name ?? index}`} className="border-t border-white/6">
                            <td className="py-3 pr-4 font-medium text-white">{row.window_name ?? "n/a"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{formatMoney(row.ending_capital_from_20000)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.profit_factor ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4 text-white/68">{formatPct(row.max_drawdown_pct)}</td>
                            <td className="py-3 pr-4 text-white/68">{row.validation_label ?? "n/a"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <TableEmpty message="No frozen patch multi-year validation audit has been generated yet." />
                )}
              </Section>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No frozen patch multi-year validation audit found yet"
            body="Once `frozen_patch_validation_audit_001` exists, this section will show frozen-patch window proofs, walk-forward pass rate, moonshot dependency in validation, and the promotion-gate classification."
          />
        )}
      </Section>

      <Section eyebrow="Frozen Patch Forensic Integrity Audit" title="Proof Quality / Sample Reuse / Next Replay">
        {Object.keys(frozenPatchForensicSummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Current proof status"
                value={String(frozenPatchForensicSummary.current_proof_status_label ?? "n/a")}
                subtext="read-only integrity classification"
                tone="orange"
              />
              <MetricCard
                label="Available data years"
                value={String((frozenPatchForensicSummary.available_source_years ?? []).join(", ") || "n/a")}
                subtext={`trade years ${(frozenPatchForensicSummary.available_trade_years ?? []).join(", ") || "n/a"}`}
                tone="cyan"
              />
              <MetricCard
                label="Trade artifact date range"
                value={String(frozenPatchForensicSummary.trade_artifact_date_range?.start ?? "n/a")}
                subtext={String(frozenPatchForensicSummary.trade_artifact_date_range?.end ?? "n/a")}
                tone="green"
              />
              <MetricCard
                label="True unseen proof"
                value={String(frozenPatchForensicSummary.true_unseen_proof_available ?? false)}
                subtext="current truthful answer"
                tone="orange"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Sample reuse risk"
                value={String(frozenPatchForensicSummary.sample_reuse_risk ?? "n/a")}
                subtext={String(frozenPatchForensicSampleReuse.current_validation_is_retrospective_only ? "retrospective only" : "independent sample")}
                tone="orange"
              />
              <MetricCard
                label="Leakage / overfit risk"
                value={String(frozenPatchForensicSummary.leakage_overfit_risk ?? frozenPatchForensicLeakage.risk_level ?? "n/a")}
                subtext={String(frozenPatchForensicLeakage.validation_windows_effectively_independent ? "independent windows" : "same-sample windows")}
                tone="orange"
              />
              <MetricCard
                label="Next required validation"
                value={String(frozenPatchForensicSummary.next_required_validation ?? "n/a")}
                subtext="exact replay still missing"
                tone="cyan"
              />
              <MetricCard
                label="Promotion blocker count"
                value={String(frozenPatchForensicSummary.promotion_blocker_count ?? frozenPatchForensicNoGoRisks.promotion_blocker_count ?? 0)}
                subtext="research-only blockers"
                tone="orange"
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Integrity truth" title="Lineage / Coverage / Gap" className="p-0">
                <div className="space-y-3 px-5 py-5 text-sm text-white/68">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 leading-7">
                    Same-sample validation detected: {String(frozenPatchForensicLineage.same_trade_artifact_used_for_discovery_and_validation ?? "n/a")}<br />
                    Raw source history sufficient to regenerate: {String(frozenPatchForensicCoverage.raw_source_history_sufficient_to_regenerate ?? "n/a")}<br />
                    Coverage sufficient for multi-year validation now: {String(frozenPatchForensicCoverage.coverage_is_sufficient_for_multi_year_validation ?? "n/a")}
                  </div>
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-white/45">What is proven</div>
                    <div className="mt-2 space-y-2">
                      {(frozenPatchForensicSummary.what_is_proven ?? []).slice(0, 3).map((item: string, index: number) => (
                        <div key={`${item}-${index}`} className="text-sm leading-6 text-white/66">
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 leading-7 text-orange-100">
                    {String(frozenPatchForensicGap.why_1m_target_is_not_yet_proven ?? "This audit remains research-only and does not mutate paper/live/runtime behavior.")}
                  </div>
                </div>
              </Section>

              <Section eyebrow="Blockers and next replay" title="No-Go Risks" className="p-0">
                {(frozenPatchForensicNoGoRisks.blockers ?? []).length ? (
                  <div className="space-y-3 px-5 py-5">
                    {(frozenPatchForensicNoGoRisks.blockers ?? []).map((item: string, index: number) => (
                      <div
                        key={`${item}-${index}`}
                        className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 text-sm text-orange-100"
                      >
                        {item}
                      </div>
                    ))}
                    <div className="rounded-2xl border border-cyan-400/18 bg-cyan-400/10 px-4 py-3 text-sm leading-7 text-cyan-100">
                      {String(
                        frozenPatchForensicGap.minimum_next_validation_needed
                        ?? frozenPatchForensicSummary.next_required_validation
                        ?? frozenPatchForensicNextReplay.stage_1_generate_broad_historical_structural_outputs?.purpose
                        ?? "No next replay plan written yet.",
                      )}
                    </div>
                  </div>
                ) : (
                  <TableEmpty message="No frozen patch forensic integrity audit has been generated yet." />
                )}
              </Section>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No frozen patch forensic integrity audit found yet"
            body="Once `frozen_patch_forensic_integrity_audit_001` exists, this section will show the true proof boundary: sample reuse, available data years, lineage truth, and the exact replay still required before promotion."
          />
        )}
      </Section>

      <Section eyebrow="Broad Historical Structural Replay" title="Raw BTC To Regenerated Multi-Year Ledger">
        {Object.keys(broadHistoricalReplaySummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <MetricCard
                label="Source data range"
                value={String(broadHistoricalReplayCoverage.source_data_start ?? "n/a")}
                subtext={String(broadHistoricalReplayCoverage.source_data_end ?? "n/a")}
                tone="cyan"
              />
              <MetricCard
                label="Generated ledger range"
                value={String(broadHistoricalReplaySummary.generated_ledger_start ?? "n/a")}
                subtext={String(broadHistoricalReplaySummary.generated_ledger_end ?? "n/a")}
                tone="green"
              />
              <MetricCard
                label="Years generated"
                value={String((broadHistoricalReplaySummary.years_generated ?? []).join(", ") || "n/a")}
                subtext={`${String((broadHistoricalReplayHealth.generated_trade_years ?? []).length)} trade years`}
                tone="cyan"
              />
              <MetricCard
                label="Trades generated"
                value={String(broadHistoricalReplaySummary.trade_count ?? 0)}
                subtext={`L ${String(broadHistoricalReplaySummary.long_trade_count ?? 0)} / S ${String(broadHistoricalReplaySummary.short_trade_count ?? 0)}`}
                tone="green"
              />
              <MetricCard
                label="Next required step"
                value={String(broadHistoricalReplaySummary.next_required_step ?? "n/a")}
                subtext="read-only replay gate"
                tone="orange"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Replay health"
                value={broadHistoricalReplayHealth.successful_replay ? "healthy" : "attention"}
                subtext={`${String((broadHistoricalReplayHealth.zero_trade_windows ?? []).length)} zero-trade windows`}
                tone={broadHistoricalReplayHealth.successful_replay ? "green" : "orange"}
              />
              <MetricCard
                label="Safe for frozen patch validation"
                value={String(broadHistoricalReplayHealth.safe_for_frozen_patch_validation ?? broadHistoricalReplaySummary.coverage_sufficient_for_frozen_patch_validation ?? false)}
                subtext={`${String(broadHistoricalReplayLeakage.counts?.failed ?? 0)} leakage failures`}
                tone={(broadHistoricalReplayHealth.safe_for_frozen_patch_validation ?? broadHistoricalReplaySummary.coverage_sufficient_for_frozen_patch_validation) ? "green" : "orange"}
              />
              <MetricCard
                label="Missing minute count"
                value={String(broadHistoricalReplayCoverage.missing_timestamp_count ?? 0)}
                subtext={`${String(broadHistoricalReplayCoverage.duplicate_timestamp_count ?? 0)} duplicates removed`}
                tone="cyan"
              />
              <MetricCard
                label="Short-window untouched"
                value={String(broadHistoricalReplayManifest.current_short_window_artifacts_untouched ?? "n/a")}
                subtext={String(broadHistoricalReplayManifest.broad_replay_isolated ? "isolated output root" : "review isolation")}
                tone={broadHistoricalReplayManifest.current_short_window_artifacts_untouched ? "green" : "orange"}
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Manifest" title="Window and leakage truth" className="p-0">
                <div className="space-y-3 px-5 py-5 text-sm text-white/68">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 leading-7">
                    Source file: {String(broadHistoricalReplayCoverage.source_path ?? "n/a")}<br />
                    Cleaned rows: {String(broadHistoricalReplayCoverage.cleaned_rows ?? 0)}<br />
                    Zero-trade windows: {String((broadHistoricalReplayHealth.zero_trade_windows ?? []).join(", ") || "none")}<br />
                    Leakage unknown/manual-review checks: {String(broadHistoricalReplayLeakage.counts?.unknown ?? 0)}
                  </div>
                  <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 leading-7 text-orange-100">
                    Read-only research telemetry only. No strategy, paper, live, allocator, or config behavior is exposed for mutation here.
                  </div>
                </div>
              </Section>

              <Section eyebrow="Window counts" title="Year-by-year trade generation" className="p-0">
                {(broadHistoricalReplay?.yearly_trade_counts ?? []).length ? (
                  <div className="overflow-x-auto px-5 py-5">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-white/45">
                        <tr>
                          <th className="pb-3 pr-4 font-medium">Year</th>
                          <th className="pb-3 pr-4 font-medium">Trades</th>
                          <th className="pb-3 pr-4 font-medium">Long</th>
                          <th className="pb-3 pr-4 font-medium">Short</th>
                          <th className="pb-3 pr-4 font-medium">Setups</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(broadHistoricalReplay?.yearly_trade_counts ?? []).map((row, index) => (
                          <tr key={`${row.period ?? index}`} className="border-t border-white/6">
                            <td className="py-3 pr-4 font-medium text-white">{row.period ?? "n/a"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.long_trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.short_trade_count ?? "0"}</td>
                            <td className="py-3 pr-4 text-white/68">{row.setup_count ?? "0"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <TableEmpty message="No broad historical replay artifacts have been generated yet." />
                )}
              </Section>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No broad historical replay generated yet"
            body="Once `broad_historical_structural_replay_001` exists, this section will show the raw BTC source range, the regenerated ledger range, yearly trade counts, leakage-audit status, and whether the isolated multi-year ledger is ready for unchanged frozen-patch validation."
          />
        )}
      </Section>

      <Section eyebrow="Broad Frozen Patch Validation" title="Unchanged Patch Applied To The Broad Ledger">
        {Object.keys(broadFrozenPatchSummary).length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <MetricCard
                label="Raw broad ending equity"
                value={formatMoney(broadFrozenPatchSummary.raw_broad_ending_equity)}
                subtext="completed structural replay ledger"
                tone="cyan"
              />
              <MetricCard
                label="Patched ending equity"
                value={formatMoney(broadFrozenPatchSummary.patched_broad_ending_equity)}
                subtext="frozen filtered-trade replay proxy"
                tone="green"
              />
              <MetricCard
                label="PF raw vs patch"
                value={`${Number(broadFrozenPatchSummary.raw_broad_profit_factor ?? 0).toFixed(2)} -> ${Number(broadFrozenPatchSummary.patched_broad_profit_factor ?? 0).toFixed(2)}`}
                subtext={`DD ${formatPct(broadFrozenPatchSummary.raw_broad_max_drawdown_pct)} -> ${formatPct(broadFrozenPatchSummary.patched_broad_max_drawdown_pct)}`}
                tone="orange"
              />
              <MetricCard
                label="Trades raw vs patch"
                value={`${String(broadFrozenPatchSummary.raw_broad_trade_count ?? 0)} -> ${String(broadFrozenPatchSummary.patched_broad_trade_count ?? 0)}`}
                subtext={`removed ${String(broadFrozenPatchSummary.removed_trade_count ?? 0)}`}
                tone="green"
              />
              <MetricCard
                label="Final classification"
                value={String(broadFrozenPatchSummary.final_patch_classification ?? "n/a")}
                subtext={String(broadFrozenPatchSummary.next_recommended_step ?? "research-only")}
                tone="orange"
              />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Long R removed"
                value={String(Number(broadFrozenPatchSummary.long_R_removed ?? 0).toFixed(2))}
                subtext="damage stripped by frozen rule"
                tone="orange"
              />
              <MetricCard
                label="Short R preserved"
                value={String(Number(broadFrozenPatchSummary.short_R_preserved ?? 0).toFixed(2))}
                subtext="broad short edge kept"
                tone="green"
              />
              <MetricCard
                label="Moonshot verdict"
                value={String(broadFrozenPatchSummary.moonshot_dependency_verdict ?? broadFrozenPatchMoonshot?.patched?.classification ?? "n/a")}
                subtext="dependency truth"
                tone="cyan"
              />
              <MetricCard
                label="Execution-cost verdict"
                value={String(broadFrozenPatchSummary.execution_cost_verdict ?? "n/a")}
                subtext={`${String((broadFrozenPatchExecution.scenarios?.low_cost?.patch_improves_cost_survival ?? false) ? "low-cost improved" : "low-cost still weak")}`}
                tone="orange"
              />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.05fr_0.95fr]">
              <Section eyebrow="Year-by-year truth" title="Did the patch help or hurt?" className="p-0">
                {broadFrozenPatchYearly.length ? (
                  <div className="overflow-x-auto px-5 py-5">
                    <table className="min-w-full text-left text-sm">
                      <thead className="text-white/45">
                        <tr>
                          <th className="pb-3 pr-4 font-medium">Year</th>
                          <th className="pb-3 pr-4 font-medium">Raw PnL</th>
                          <th className="pb-3 pr-4 font-medium">Patch PnL</th>
                          <th className="pb-3 pr-4 font-medium">Raw PF</th>
                          <th className="pb-3 pr-4 font-medium">Patch PF</th>
                          <th className="pb-3 pr-4 font-medium">Verdict</th>
                        </tr>
                      </thead>
                      <tbody>
                        {broadFrozenPatchYearly.slice(0, 9).map((row, index) => (
                          <tr key={`${row.year ?? index}`} className="border-t border-white/6">
                            <td className="py-3 pr-4 font-medium text-white">{row.year ?? "n/a"}</td>
                            <td className="py-3 pr-4 text-white/68">{formatMoney(row.raw_pnl)}</td>
                            <td className="py-3 pr-4 text-white/68">{formatMoney(row.patched_pnl)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.raw_profit_factor ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4 text-white/68">{Number(row.patched_profit_factor ?? 0).toFixed(2)}</td>
                            <td className="py-3 pr-4 text-white/68">{row.patch_helped_or_hurt ?? "n/a"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <TableEmpty message="No broad frozen patch validation has been generated yet." />
                )}
              </Section>

              <Section eyebrow="Forensic verdict" title="Risks / cost survival / next step" className="p-0">
                <div className="space-y-3 px-5 py-5 text-sm text-white/68">
                  <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 leading-7">
                    Years helped: {String(broadFrozenPatchSummary.yearly_verdict?.years_helped ?? broadFrozenPatchValidation?.patch_survival_by_year?.years_helped ?? 0)}<br />
                    Years hurt: {String(broadFrozenPatchSummary.yearly_verdict?.years_hurt ?? broadFrozenPatchValidation?.patch_survival_by_year?.years_hurt ?? 0)}<br />
                    Consistency: {String(broadFrozenPatchSummary.yearly_verdict?.yearly_consistency_label ?? broadFrozenPatchValidation?.patch_survival_by_year?.yearly_consistency_label ?? "n/a")}
                  </div>
                  <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 leading-7 text-orange-100">
                    {String(
                      broadFrozenPatchValidation?.next_research_recommendation?.next_step
                      ?? broadFrozenPatchSummary.next_recommended_step
                      ?? "No next step written yet.",
                    )}
                  </div>
                  {(broadFrozenPatchNoGo.blockers ?? []).length ? (
                    <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 text-orange-100">
                      Blockers: {(broadFrozenPatchNoGo.blockers ?? []).join(", ")}
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-emerald-400/18 bg-emerald-400/10 px-4 py-3 text-emerald-100">
                      No explicit no-go blockers were written into the artifact.
                    </div>
                  )}
                  <div className="rounded-2xl border border-cyan-400/18 bg-cyan-400/10 px-4 py-3 text-cyan-100">
                    Read-only research telemetry only. This section does not mutate runtime, config, live, or paper state.
                  </div>
                </div>
              </Section>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No broad frozen patch validation generated yet"
            body="Once `broad_frozen_patch_validation_001` exists, this section will show the unchanged patch applied to the completed broad ledger, the raw-vs-patch yearly verdict, moonshot dependency, cost survival, and the final research-only classification."
          />
        )}
      </Section>

      <Section eyebrow="Daily Opportunity Engine" title="BTC Structural Opportunity Truth">
        {dailyOpportunityRows.length ? (
          <div className="grid gap-5">
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <MetricCard label="Days analyzed" value={String(dailyOpportunitySummary.days_analyzed ?? 0)} subtext={dailyOpportunityMetadata.classification ?? "research-only"} />
              <MetricCard label="Valid days" value={String(dailyOpportunitySummary.valid_opportunity_days ?? 0)} subtext="daily structural opportunities" tone="green" />
              <MetricCard label="Strong hills" value={String(dailyOpportunitySummary.strong_structural_hill_days ?? 0)} subtext="high-conviction market structure" tone="green" />
              <MetricCard
                label="Actual trades"
                value={String(dailyOpportunitySummary.actual_trade_frequency?.actual_trade_count ?? 0)}
                subtext={`${String(dailyOpportunitySummary.actual_trade_frequency?.actual_trade_days ?? 0)} active trade days`}
                tone="green"
              />
              <MetricCard label="Noise avoided" value={String(dailyOpportunitySummary.noise_chasing_avoided_count ?? 0)} subtext="tiny wiggles correctly ignored" />
            </div>

            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
              <MetricCard label="No-opportunity days" value={String(dailyOpportunitySummary.no_opportunity_days ?? 0)} subtext="flat or unrewarding structure" />
              <MetricCard label="True missed high-R" value={String(dailyOpportunitySummary.missed_high_R_opportunity_count ?? 0)} subtext="qualified high-R days with no actual trade" tone="orange" />
              <MetricCard label="High-R probe days" value={String(dailyOpportunitySummary.high_R_probe_day_count ?? 0)} subtext="strong days intentionally kept probe-only" />
              <MetricCard label="Full-size" value={String(dailyOpportunitySummary.full_size_count ?? 0)} subtext="strongest participation days" tone="green" />
              <MetricCard label="Too-tight days" value={String(dailyOpportunitySummary.too_tight_day_count ?? 0)} subtext="good structure, weak participation" tone="orange" />
              <MetricCard label="Reject-invalid" value={String(dailyOpportunitySummary.reject_invalid_count ?? 0)} subtext="broken or impossible geometry" tone="orange" />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
              <Section eyebrow="Top opportunity by day" title="Daily Structural Opportunity Tape" className="p-0">
                <div className="overflow-x-auto px-5 py-5">
                  <table className="min-w-full text-left text-sm">
                    <thead className="text-white/45">
                      <tr>
                        <th className="pb-3 pr-4 font-medium">Date</th>
                        <th className="pb-3 pr-4 font-medium">Side</th>
                        <th className="pb-3 pr-4 font-medium">Label</th>
                        <th className="pb-3 pr-4 font-medium">Score</th>
                        <th className="pb-3 pr-4 font-medium">Archetype</th>
                        <th className="pb-3 pr-4 font-medium">Personality</th>
                        <th className="pb-3 pr-4 font-medium">Participation</th>
                        <th className="pb-3 pr-4 font-medium">Actual Trades</th>
                        <th className="pb-3 pr-4 font-medium">Opened Setups</th>
                        <th className="pb-3 pr-4 font-medium">Expected R</th>
                        <th className="pb-3 pr-4 font-medium">High-R Audit</th>
                        <th className="pb-3 pr-4 font-medium">Room</th>
                        <th className="pb-3 pr-4 font-medium">Danger</th>
                        <th className="pb-3 pr-4 font-medium">Explanation</th>
                      </tr>
                    </thead>
                    <tbody>
                      {dailyOpportunityRows.slice(0, 40).map((row, index) => (
                        <tr key={`${row.date ?? row.timestamp ?? index}`} className="border-t border-white/6 align-top">
                          <td className="py-3 pr-4 text-white/68">{row.date ?? "n/a"}</td>
                          <td className="py-3 pr-4 text-white/68">{row.side ?? "flat"}</td>
                          <td className="py-3 pr-4 font-medium text-white">{row.opportunity_label ?? "n/a"}</td>
                          <td className="py-3 pr-4 text-white/68">{Number(row.opportunity_score ?? 0).toFixed(1)}</td>
                          <td className="py-3 pr-4 text-white/68">{row.best_archetype ?? "n/a"}</td>
                          <td className="py-3 pr-4 text-white/68">{row.best_personality ?? "n/a"}</td>
                          <td className="py-3 pr-4 text-white/68">{row.participation_mode ?? "n/a"}</td>
                          <td className="py-3 pr-4 text-white/68">{row.actual_trade_count ?? "0"}</td>
                          <td className="py-3 pr-4 text-white/68">{row.opened_setup_count ?? "0"}</td>
                          <td className="py-3 pr-4 text-white/68">{Number(row.expected_R_potential ?? 0).toFixed(2)}</td>
                          <td className="py-3 pr-4 text-white/68">{row.missed_high_r_audit_category ?? "n/a"}</td>
                          <td className="py-3 pr-4 text-white/68">{Number(row.room_to_target_score ?? 0).toFixed(2)}</td>
                          <td className="py-3 pr-4 text-white/68">{Number(row.danger_score ?? 0).toFixed(2)}</td>
                          <td className="py-3 pr-4 text-white/55">{row.explanation ?? "n/a"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>

              <div className="grid gap-5">
                <Section eyebrow="Support / resistance intelligence" title="Zone Quality / Breakout / Retest">
                  <div className="grid gap-3">
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      breakout-retest hold days: <span className="font-medium text-white">{String(dailyOpportunity?.sr_zone_report?.breakout_retest_hold_days ?? 0)}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      failed breakout days: <span className="font-medium text-white">{String(dailyOpportunity?.sr_zone_report?.failed_breakout_days ?? 0)}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      average zone quality: <span className="font-medium text-white">{Number(dailyOpportunity?.sr_zone_report?.average_zone_quality_score ?? 0).toFixed(2)}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      source updated: <span className="font-medium text-white">{formatTime(dailyOpportunityMetadata.last_updated)}</span>
                    </div>
                  </div>
                </Section>

                <Section eyebrow="Too tight vs wiggle chasing" title="Participation Guardrails">
                  <div className="grid gap-3">
                    <div className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3 text-sm text-orange-100">
                      too-tight days: {String(dailyOpportunitySummary.too_tight_day_count ?? 0)} | missed valid: {String(dailyOpportunitySummary.missed_valid_opportunity_count ?? 0)}
                    </div>
                    <div className="rounded-2xl border border-cyan-400/18 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100">
                      noise-chasing avoided: {String(dailyOpportunitySummary.noise_chasing_avoided_count ?? 0)} | tiny wiggles: {String(dailyOpportunity?.noise_chasing_report?.tiny_wiggle_flag_count ?? 0)}
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      next step: <span className="font-medium text-white">{dailyOpportunity?.next_research_recommendation?.next_step ?? "n/a"}</span>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/68">
                      read-only source files: <span className="font-medium text-white">{String((dailyOpportunityMetadata.source_files ?? []).length)}</span>
                    </div>
                  </div>
                </Section>
              </div>
            </div>
          </div>
        ) : (
          <EmptyState
            title="No daily structural opportunity artifact found yet"
            body="Once `daily_structural_opportunity_001` exists, this section will show day-level structural opportunity labels, participation routing, support/resistance intelligence, and the too-tight versus wiggle-chasing balance."
          />
        )}
      </Section>

      <Section eyebrow="Operator truth" title="Artifact Freshness And Empty-State Honesty">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {latestArtifacts.map(([key, status]) => (
            <div key={key} className={clsx("rounded-2xl border px-4 py-3", toneForArtifact(String(status.status ?? "")))}>
              <div className="text-[10px] uppercase tracking-[0.22em] text-white/55">{key}</div>
              <div className="mt-2 text-sm break-all">{String(status.path ?? "n/a")}</div>
              <div className="mt-3 text-xs text-white/60">
                {status.exists ? `updated ${formatTime(status.last_modified_timestamp)}` : "artifact missing"}
              </div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );

  const marketReplayContent = (
    <div className="grid gap-5">
      {data?.lab?.has_run ? null : (
        <Section eyebrow="Replay truth" title="Structural Replay Is Scaffolded, Not Fabricated">
          <EmptyState
            title="No structural backtest run found yet"
            body="The replay theatre is already wired for candles, EMA overlays, trade markers, condition cards, fullscreen charting, and future structure overlays. Once the external structural-lab project writes its output artifacts, this page will light up without touching the active paper or backtest cockpit."
          />
        </Section>
      )}

      <Section eyebrow="Replay controls" title="Symbol / Timeframe">
        <div className="flex flex-wrap gap-3">
          <label className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/72">
            Symbol
            <select
              className="ml-3 bg-transparent text-white outline-none"
              value={selectedSymbol}
              onChange={(event) => setSymbol(event.target.value)}
            >
              {availableSymbols.map((item) => (
                <option key={item} value={item} className="bg-slate-950 text-white">
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/72">
            Timeframe
            <select
              className="ml-3 bg-transparent text-white outline-none"
              value={selectedTimeframe}
              onChange={(event) => setTimeframe(event.target.value)}
            >
              {availableTimeframes.map((item) => (
                <option key={item} value={item} className="bg-slate-950 text-white">
                  {item}
                </option>
              ))}
            </select>
          </label>
          <div className="rounded-full border border-cyan-300/16 bg-cyan-400/10 px-4 py-2 text-sm text-cyan-100">
            Read-only research replay. No runtime mutation, no real money, no paper integration.
          </div>
        </div>
      </Section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Trades" value={String(tradeRows.length)} subtext="Entry, exit, and moonshot lifecycle markers" tone="green" />
        <MetricCard label="Setups" value={String(setupRows.length)} subtext="Condition-card candidates and score breakdowns" />
        <MetricCard label="Profit locks" value={String(overview?.profit_lock_count ?? 0)} subtext="Protected vault transitions" tone="orange" />
        <MetricCard label="Add-ons" value={String(overview?.add_on_event_count ?? 0)} subtext="Proof-based convex expansion" />
      </div>

      <CandlePanel
        apiUrl={API_URL}
        endpointPath="/api/structural-lab/candles"
        panelLabel="Structural Replay Chart"
        symbol={selectedSymbol}
        timeframe={selectedTimeframe}
        mode="structural_lab"
      />

      <div className="grid gap-5 xl:grid-cols-3">
        <Section eyebrow="Condition card" title="Replay Context">
          <div className="space-y-3 text-sm text-white/68">
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              Support, resistance, liquidity sweeps, add-ons, profit-lock events, and cooldown markers are drawn from structural artifacts instead of mocked UI placeholders.
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              Latest structural trade: {latestTrade ? `${latestTrade.symbol ?? selectedSymbol} / ${latestTrade.side ?? "n/a"} / ${latestTrade.exit_reason ?? "open"}` : "No trades available"}
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              Latest setup review: {latestSetup ? `${latestSetup.symbol ?? selectedSymbol} / ${latestSetup.classification ?? latestSetup.setup_class ?? "n/a"} / score ${Number(latestSetup.total_score ?? latestSetup.score ?? 0).toFixed(2)}` : "No setups available"}
            </div>
          </div>
        </Section>
        <Section eyebrow="Vault state" title="Convexity / Lock / Cooldown">
          <div className="space-y-3 text-sm text-white/68">
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              Cycle {overview?.current_compounding_cycle ?? "cycle-0"} | locked {formatMoney(overview?.locked_profit)} | active {formatMoney(overview?.active_trading_capital)}
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              Latest cooldown event: {latestCooldownEvent ? `${formatTime(latestCooldownEvent.timestamp)} | ${latestCooldownEvent.reason ?? latestCooldownEvent.event_type ?? "cooldown"}` : "No cooldown events yet"}
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
              Latest convex event: {latestPyramidingEvent ? `${formatTime(latestPyramidingEvent.timestamp)} | ${latestPyramidingEvent.add_type ?? latestPyramidingEvent.event_type ?? "pyramid"}` : "No add-on or profit-lock event yet"}
            </div>
          </div>
        </Section>
        <Section eyebrow="Replay counters" title="Market-Theatre Coverage">
          <div className="grid gap-3">
            <MetricCard label="Cooldown rows" value={String(cooldownRows.length)} subtext={`Releases ${String(overview?.cooldown_release_count ?? 0)}`} tone="orange" />
            <MetricCard label="Liquidity events" value={String(liquidityRows.length)} subtext="Sweeps, failed breaks, and reclaims" />
            <MetricCard label="Levels" value={String(levelRows.length)} subtext="Range, previous-period, and pivot structure" tone="green" />
          </div>
        </Section>
      </div>
    </div>
  );

  const structureMapContent = (
    <div className="grid gap-5 xl:grid-cols-2">
      <Section eyebrow="Level inventory" title="Support / Resistance / Range Structure">
        {levelRows.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-white/45">
                <tr>
                  <th className="pb-3 pr-4 font-medium">Time</th>
                  <th className="pb-3 pr-4 font-medium">Type</th>
                  <th className="pb-3 pr-4 font-medium">Price</th>
                  <th className="pb-3 pr-4 font-medium">Timeframe</th>
                  <th className="pb-3 pr-4 font-medium">Touches</th>
                </tr>
              </thead>
              <tbody>
                {levelRows.slice(-40).reverse().map((row, index) => (
                  <tr key={`${row.timestamp ?? row.first_seen ?? index}`} className="border-t border-white/6">
                    <td className="py-3 pr-4 text-white/68">{formatTime(row.timestamp ?? row.first_seen)}</td>
                    <td className="py-3 pr-4 font-medium text-white">{row.type ?? row.level_type ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.price ?? row.level_price ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.timeframe_source ?? row.timeframe ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.touch_count ?? row.touches ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <TableEmpty message="No levels detected yet." />
        )}
      </Section>

      <Section eyebrow="Liquidity inventory" title="Sweeps / Reclaims / Failed Breaks">
        {liquidityRows.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-white/45">
                <tr>
                  <th className="pb-3 pr-4 font-medium">Time</th>
                  <th className="pb-3 pr-4 font-medium">Type</th>
                  <th className="pb-3 pr-4 font-medium">Price</th>
                  <th className="pb-3 pr-4 font-medium">Side</th>
                  <th className="pb-3 pr-4 font-medium">Source TF</th>
                </tr>
              </thead>
              <tbody>
                {liquidityRows.slice(-40).reverse().map((row, index) => (
                  <tr key={`${row.timestamp ?? row.event_time ?? index}`} className="border-t border-white/6">
                    <td className="py-3 pr-4 text-white/68">{formatTime(row.timestamp ?? row.event_time)}</td>
                    <td className="py-3 pr-4 font-medium text-white">{row.type ?? row.event_type ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.price ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.side_implication ?? row.side ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.source_timeframe ?? row.timeframe ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <TableEmpty message="No liquidity events available yet." />
        )}
      </Section>
    </div>
  );

  const profitVaultContent = (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
      <Section eyebrow="Vault accounting" title="Base / Active / Locked">
        <div className="grid gap-4 md:grid-cols-2">
          <MetricCard label="Base capital" value={formatMoney(overview?.base_capital)} subtext="Static research base" />
          <MetricCard label="Locked profit" value={formatMoney(overview?.locked_profit)} subtext="Protected after danger" tone="orange" />
          <MetricCard label="Active trading capital" value={formatMoney(overview?.active_trading_capital)} subtext="Capital currently in cycle" tone="green" />
          <MetricCard label="Current equity" value={formatMoney(overview?.current_equity)} subtext={`Cooldown ${overview?.cooldown_state ?? "inactive"}`} />
        </div>
        <div className="mt-4 rounded-2xl border border-white/10 bg-white/5 px-4 py-4 text-sm leading-7 text-white/65">
          This vault stays read-only. The scaffold is designed to later show cycle-by-cycle profit locking, capital resets to base, cooldown activation, and eventual guarded re-entry once structure becomes favorable again.
        </div>
      </Section>

      <Section eyebrow="Vault event tape" title="Locks / Cooldowns / Resets">
        {cooldownRows.length || pyramidingRows.length || data?.profit_vault ? (
          <div className="space-y-3">
            {cooldownRows.slice(-12).reverse().map((row, index) => (
              <div key={`${row.timestamp ?? row.cooldown_start ?? index}`} className="rounded-2xl border border-orange-400/18 bg-orange-400/10 px-4 py-3">
                <div className="text-[10px] uppercase tracking-[0.24em] text-orange-200/70">Cooldown</div>
                <div className="mt-2 text-sm text-orange-100">
                  {formatTime(row.timestamp ?? row.cooldown_start)} | {row.reason ?? "danger sniffer"}
                </div>
              </div>
            ))}
            {pyramidingRows.slice(-12).reverse().map((row, index) => (
              <div key={`${row.timestamp ?? row.event_time ?? index}`} className="rounded-2xl border border-cyan-400/18 bg-cyan-400/10 px-4 py-3">
                <div className="text-[10px] uppercase tracking-[0.24em] text-cyan-200/70">Pyramiding / Vault Event</div>
                <div className="mt-2 text-sm text-cyan-100">
                  {formatTime(row.timestamp ?? row.event_time)} | {row.add_type ?? row.event_type ?? "research event"}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <TableEmpty message="No profit vault state yet." />
        )}
      </Section>
    </div>
  );

  const tradeReviewContent = (
    <div className="grid gap-5">
      <Section eyebrow="Trading activity KPIs" title="Trade Frequency & PnL">
        <TradeFrequencyPnlPanel
          payload={data?.trade_frequency_pnl}
          title="Trading Activity KPIs"
          subtitle="Structural realized trade aggregation by day, week, month, and year"
        />
      </Section>

      <div className="grid gap-5 xl:grid-cols-[1.15fr_0.85fr]">
        <Section eyebrow="Trade ledger" title="All Structural Trades">
        {tradeRows.length ? (
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="text-white/45">
                <tr>
                  <th className="pb-3 pr-4 font-medium">Symbol</th>
                  <th className="pb-3 pr-4 font-medium">Side</th>
                  <th className="pb-3 pr-4 font-medium">R</th>
                  <th className="pb-3 pr-4 font-medium">PnL</th>
                  <th className="pb-3 pr-4 font-medium">Entry reason</th>
                  <th className="pb-3 pr-4 font-medium">Exit reason</th>
                </tr>
              </thead>
              <tbody>
                {tradeRows.slice(-80).reverse().map((row, index) => (
                  <tr key={`${row.trade_id ?? row.entry_time ?? index}`} className="border-t border-white/6">
                    <td className="py-3 pr-4 font-medium text-white">{row.symbol ?? "BTCUSDT"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.side ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.r_multiple ?? row.pnl_r ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.pnl ?? row.pnl_value ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.entry_reason ?? "n/a"}</td>
                    <td className="py-3 pr-4 text-white/68">{row.exit_reason ?? "n/a"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <TableEmpty message="No trades available." />
        )}
        </Section>

        <Section eyebrow="Setup tape" title="Decision Forensics">
        {setupRows.length ? (
          <div className="space-y-3">
            {setupRows.slice(-18).reverse().map((row, index) => (
              <div key={`${row.timestamp ?? row.setup_time ?? index}`} className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="text-sm font-medium text-white">{row.symbol ?? selectedSymbol}</div>
                  <div className="rounded-full border border-cyan-300/16 bg-cyan-400/10 px-2 py-1 text-[10px] uppercase tracking-[0.18em] text-cyan-100">
                    {row.classification ?? row.setup_class ?? "setup"}
                  </div>
                </div>
                <div className="mt-2 text-xs uppercase tracking-[0.2em] text-white/45">{formatTime(row.timestamp ?? row.setup_time)}</div>
                <div className="mt-3 text-sm leading-6 text-white/64">
                  {row.explanation ?? row.entry_reason ?? "No setup explanation written yet."}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <TableEmpty message="No setup reviews available yet." />
        )}
        </Section>
      </div>
    </div>
  );

  const settingsContent = (
    <div className="grid gap-5 xl:grid-cols-2">
      <Section eyebrow="Read-only research config" title="Structural Settings">
        <JsonBlock value={data?.settings ?? {}} />
      </Section>
      <Section eyebrow="Universe and artifact roots" title="Symbols / Output / Report">
        <div className="space-y-4">
          <JsonBlock value={data?.symbols_config ?? {}} />
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/65">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/48">Output root</div>
            <div className="mt-2 break-all">{data?.lab?.output_path ?? "n/a"}</div>
          </div>
          <div className="rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm text-white/65">
            <div className="text-[10px] uppercase tracking-[0.22em] text-white/48">Report excerpt</div>
            <div className="mt-2 whitespace-pre-wrap leading-6">
              {data?.report_markdown ? data.report_markdown.split("\n").slice(0, 10).join("\n") : "No report.md found yet."}
            </div>
          </div>
        </div>
      </Section>
    </div>
  );

  const content = {
    overview: overviewContent,
    "market-replay": marketReplayContent,
    "structure-map": structureMapContent,
    "profit-vault": profitVaultContent,
    "trade-review": tradeReviewContent,
    settings: settingsContent,
  }[view];

  return (
    <main className="min-h-screen bg-transparent px-5 py-6 text-white md:px-8 xl:px-10">
      <div className="mx-auto flex max-w-[1900px] flex-col gap-6">
        <header
          className={clsx(
            "relative overflow-hidden rounded-[38px] border border-white/10 bg-[linear-gradient(180deg,rgba(8,17,34,0.92),rgba(6,11,24,0.88))] shadow-[0_30px_120px_rgba(4,8,22,0.45)]",
            compactHero ? "p-4" : "p-6",
          )}
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_18%,rgba(83,242,255,0.18),transparent_22%),radial-gradient(circle_at_76%_14%,rgba(255,153,56,0.12),transparent_18%),radial-gradient(circle_at_72%_84%,rgba(52,211,153,0.12),transparent_22%)]" />
          <div className={clsx("relative grid xl:items-center", compactHero ? "gap-4 xl:grid-cols-[112px_minmax(0,1fr)]" : "gap-6 xl:grid-cols-[280px_minmax(0,1fr)]")}>
            <div className={clsx("relative hidden overflow-hidden rounded-[30px] border border-cyan-300/16 bg-[#050c1d] xl:block", compactHero ? "h-[96px]" : "h-[180px]")}>
              <Image
                src="/logo-hero.png"
                alt="Structural Compounding Lab"
                fill
                className={clsx("object-contain drop-shadow-[0_0_28px_rgba(83,242,255,0.16)]", compactHero ? "scale-[1.01]" : "scale-[1.03]")}
                priority
              />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap gap-2">
                <span className="rounded-full border border-cyan-300/28 bg-cyan-400/14 px-3 py-1 text-[10px] uppercase tracking-[0.34em] text-cyan-100">
                  Structural Compounding Lab
                </span>
                <span className="rounded-full border border-orange-300/24 bg-orange-400/12 px-3 py-1 text-[10px] uppercase tracking-[0.28em] text-orange-100">
                  Separate Research UI
                </span>
                <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] uppercase tracking-[0.28em] text-white/65">
                  Read-only / isolated from paper-live runtime
                </span>
              </div>
              <h1 className={clsx("font-semibold tracking-[0.01em]", compactHero ? "mt-2 text-3xl md:text-[2.35rem]" : "mt-4 text-4xl md:text-[3rem]")}>Structural Command Lab</h1>
              <p className={clsx("max-w-4xl text-sm leading-7 text-white/70", compactHero ? "mt-2" : "mt-3")}>
                {compactHero
                  ? "Chart-first replay theatre for structural compounding research: support and resistance, liquidity sweeps, convex adds, profit locks, and fast-clearing cooldown control."
                  : "This cockpit is a future-ready research shell for a support/resistance, liquidity, EMA, pyramiding, danger-sniffer, cooldown, and profit-vault strategy lab. It borrows the current dashboard language, but stays fully isolated from `/paper`, `/backtest`, `/live`, and the active Phase 2 capital-lane replay."}
              </p>
              <div className={clsx("flex flex-wrap gap-3", compactHero ? "mt-3" : "mt-5")}>
                <Link
                  href="/"
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/72 transition hover:border-cyan-300/20 hover:text-white"
                >
                  <ArrowRight className="h-4 w-4 rotate-180" />
                  Return to command center
                </Link>
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-white/68">
                  <Database className="h-4 w-4 text-cyan-200" />
                  {data?.lab?.has_run ? "reading external structural output" : "awaiting structural artifacts"}
                </div>
              </div>
            </div>
          </div>
        </header>

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <MetricCard label="Base capital" value={formatMoney(overview?.base_capital)} subtext="research base" />
          <MetricCard label="Active capital" value={formatMoney(overview?.active_trading_capital)} subtext={overview?.current_compounding_cycle ?? "cycle-0"} tone="green" />
          <MetricCard label="Locked profit" value={formatMoney(overview?.locked_profit)} subtext={overview?.cooldown_state ?? "inactive"} tone="orange" />
          <MetricCard label="Trades" value={String(tradeRows.length)} subtext="trade review rows" />
          <MetricCard label="Warnings" value={String(warningList.length)} subtext={warningList[0] ?? "no warnings"} tone={warningList.length ? "orange" : "green"} />
        </div>

        <nav className="flex flex-wrap gap-3">
          {VIEWS.map((item) => {
            const active = item.key === activeView.key;
            return (
              <Link
                key={item.key}
                href={item.href}
                className={clsx(
                  "inline-flex items-center gap-2 rounded-2xl border px-4 py-2 text-sm transition",
                  active
                    ? "border-cyan-300/30 bg-cyan-400/12 text-cyan-50 shadow-[0_0_20px_rgba(83,242,255,0.12)]"
                    : "border-white/10 bg-white/5 text-white/68 hover:border-cyan-300/18 hover:text-white",
                )}
              >
                {item.icon}
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        {warningList.length ? (
          <Section eyebrow="Research warnings" title="Current Empty-State / Artifact Truth">
            <div className="grid gap-3">
              {warningList.map((warning) => (
                <div key={warning} className="rounded-2xl border border-orange-400/20 bg-orange-400/10 px-4 py-3 text-sm text-orange-100">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="h-4 w-4" />
                    <span>{warning}</span>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        ) : null}

        {isLoading && !data ? (
          <Section eyebrow="Loading" title="Structural Lab Snapshot">
            <TableEmpty message="Loading structural lab telemetry..." />
          </Section>
        ) : null}
        {error ? (
          <Section eyebrow="Telemetry error" title="Structural Lab Snapshot">
            <TableEmpty message="Snapshot request failed. The lab remains read-only; refresh after the structural API comes up." />
          </Section>
        ) : null}
        {!error ? content : null}
      </div>
    </main>
  );
}
