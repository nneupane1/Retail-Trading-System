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
