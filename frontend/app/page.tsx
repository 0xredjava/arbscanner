"use client";

import {
  Activity, AlertTriangle, CheckCircle2, Clock3, ExternalLink, Filter,
  Globe2, History, RefreshCw, ShieldCheck
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Leg = {
  platform: string; outcome: string; outcome_key?: string; odds: number; stake: number;
  return: number; gross_payout?: number; net_payout?: number; url?: string | null;
  fee_pct?: number; fee_amount?: number; bet_type?: string; price?: number | null;
  average_price?: number | null; maximum_price?: number | null; shares?: number | null;
  quote_fetched_at?: string | null; source_timestamp?: string | null;
  best_price_size?: number | null; depth_used?: { price: number; shares: number }[];
  available_depth?: { price: number; shares: number }[];
  minimum_decimal_odds?: number | null;
  warnings?: string[];
};

type Opportunity = {
  id?: string | number; match_id?: string; fingerprint?: string; sport: string;
  event_name: string; league: string; country?: string; competition?: string;
  market_type: string; start_time?: string | null; profit_pct: number;
  total_stake: number; requested_bankroll?: number; guaranteed_return: number;
  guaranteed_profit: number; legs: Leg[]; warnings?: string[]; detected_at?: string;
  first_found_at?: string; last_seen_at?: string; last_verified_at?: string;
  quote_expires_at?: string; freshness_status?: string; execution_safe?: boolean;
};

type PlatformStatus = {
  platform: string; enabled: boolean; status: string; fetch_method: string;
  source_type?: string; event_count: number; response_count?: number;
  last_error?: string | null; last_success_at?: string | null;
  data_timestamp?: string | null; updated_at?: string;
};

type Scan = { id?: string; started_at?: string; finished_at?: string; status?: string; event_count?: number; opportunity_count?: number };
type ComparisonLeg = { key: string; platform: string; outcome: string; odds: number; effective_odds: number; execution_cost_pct: number };
type Comparison = { match_id: string; sport: string; event_name: string; margin_pct: number; break_even_gap_pct: number; legs: ComparisonLeg[] };
type Coverage = { scope_label: string; sports: string[]; countries: string[]; competitions: string[]; platforms: string[]; event_count: number };
type Lifecycle = { fingerprint: string; event_name: string; sport: string; country?: string; competition?: string; first_found_at: string; last_seen_at: string; ended_at?: string | null; end_reason?: string | null; observation_count: number; latest_profit_pct: number; latest_state: string };
type Observation = { observed_at: string; legs: Leg[] };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const FALLBACK_PLATFORMS = ["polymarket", "stake", "bcgame", "shuffle", "cloudbet", "tgcasino", "thunderpick"];
const money = (value: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value || 0);
const localTime = (value?: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";

function currentState(item: Opportunity) {
  if (item.quote_expires_at && Date.now() >= new Date(item.quote_expires_at).getTime()) return "expired";
  return item.freshness_status || "unknown";
}

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [platforms, setPlatforms] = useState<PlatformStatus[]>([]);
  const [scan, setScan] = useState<Scan | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [coverage, setCoverage] = useState<Coverage>({ scope_label: "Worldwide where enabled sources provide markets", sports: [], countries: [], competitions: [], platforms: [], event_count: 0 });
  const [history, setHistory] = useState<Lifecycle[]>([]);
  const [scanInterval, setScanInterval] = useState(60);
  const [running, setRunning] = useState(false);
  const [sport, setSport] = useState(""); const [platform, setPlatform] = useState("");
  const [country, setCountry] = useState(""); const [competition, setCompetition] = useState("");
  const [minProfit, setMinProfit] = useState("0");
  const [expanded, setExpanded] = useState<string | number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (sport) params.set("sport", sport); if (platform) params.set("platform", platform);
      if (country) params.set("country", country); if (competition) params.set("competition", competition);
      if (minProfit) params.set("minProfit", minProfit);
      const responses = await Promise.all([
        fetch(`${API_BASE}/api/opportunities/latest?${params}`), fetch(`${API_BASE}/api/opportunities/closest?limit=10`),
        fetch(`${API_BASE}/api/platforms`), fetch(`${API_BASE}/api/scans/latest`), fetch(`${API_BASE}/api/health`),
        fetch(`${API_BASE}/api/coverage`), fetch(`${API_BASE}/api/opportunities/history?limit=20`)
      ]);
      if (responses.some((response) => !response.ok)) throw new Error("One or more scanner API requests failed");
      const [oppsData, closestData, platformData, scanData, healthData, coverageData, historyData] = await Promise.all(responses.map((response) => response.json()));
      setOpportunities(oppsData.opportunities || []); setComparisons(closestData.comparisons || []);
      setPlatforms(platformData.platforms || []); setScan(scanData.scan || null);
      setRunning(Boolean(oppsData.running || scanData.running)); setScanInterval(Number(healthData.scan_interval_seconds || 60));
      setCoverage(coverageData); setHistory(historyData.opportunities || []);
    } catch (exc) { setError(exc instanceof Error ? exc.message : "Unable to load scanner data"); }
  }

  async function runScan() {
    const token = window.prompt("Admin token"); if (!token) return;
    setRunning(true);
    try {
      const response = await fetch(`${API_BASE}/api/scans/run`, { method: "POST", headers: { "X-Admin-Token": token } });
      if (!response.ok) throw new Error("Manual scan failed"); await loadData();
    } catch (exc) { setError(exc instanceof Error ? exc.message : "Manual scan failed"); }
    finally { setRunning(false); }
  }

  useEffect(() => { void loadData(); const timer = window.setInterval(() => void loadData(), 15_000); return () => window.clearInterval(timer); }, [sport, platform, country, competition, minProfit]);
  const okCount = useMemo(() => platforms.filter((item) => item.status === "ok").length, [platforms]);
  const visibleComparisons = comparisons.filter((item) => (!sport || item.sport === sport) && (!platform || item.legs.some((leg) => leg.platform === platform))).slice(0, 5);

  return <main className="shell">
    <header className="topbar">
      <div><p className="eyebrow">Execution-aware pre-match scanner</p><h1>Arbitrage Scanner</h1><p className="subtitle">Find it, verify it, and understand every leg before risking money.</p></div>
      <button className="primary" onClick={runScan} disabled={running}><RefreshCw size={18} className={running ? "spin" : ""} />{running ? "Scanning" : "Run fresh scan"}</button>
    </header>

    <section className="coverageBanner"><Globe2 size={22} /><div><strong>{coverage.scope_label}</strong><span>Not Brazil-only · {coverage.sports.length || 6} sports · {coverage.countries.length} regions · {coverage.competitions.length} competitions in the latest scan</span></div></section>
    <section className="metrics" aria-label="Scanner summary">
      <Metric label="Latest scan" value={localTime(scan?.finished_at)} /><Metric label="Events checked" value={scan?.event_count ?? 0} />
      <Metric label="Actionable now" value={opportunities.filter((item) => currentState(item) !== "expired" && item.execution_safe).length} />
      <Metric label="Platforms healthy" value={`${okCount}/${platforms.length || FALLBACK_PLATFORMS.length}`} /><Metric label="Automatic scan" value={`Every ${scanInterval}s`} />
    </section>
    {error && <div className="notice"><AlertTriangle size={18} />{error}</div>}

    <section className="toolbar" aria-label="Opportunity filters"><Filter size={18} />
      <FilterSelect label="All sports" value={sport} values={coverage.sports} onChange={setSport} />
      <FilterSelect label="All regions" value={country} values={coverage.countries} onChange={setCountry} />
      <FilterSelect label="All competitions" value={competition} values={coverage.competitions} onChange={setCompetition} />
      <FilterSelect label="All platforms" value={platform} values={coverage.platforms.length ? coverage.platforms : FALLBACK_PLATFORMS} onChange={setPlatform} />
      <label>Min profit <input value={minProfit} onChange={(event) => setMinProfit(event.target.value)} inputMode="decimal" /></label>
    </section>

    <section className="layout"><div className="opportunities"><div className="sectionTitle"><Activity size={18} />Actionable opportunities</div>
      {!opportunities.length ? <div className="panel empty">No execution-safe arbitrage clears the threshold right now.<ClosestMarkets items={visibleComparisons} /></div> : opportunities.map((item, index) => {
        const key = item.fingerprint || item.id || item.match_id || index; const state = currentState(item);
        return <article className={`opportunityCard ${state}`} key={key}>
          <button className="opportunitySummary" onClick={() => setExpanded(expanded === key ? null : key)}>
            <div><span className={`statusPill ${state}`}><Clock3 size={13} />{state}</span><h2>{item.event_name}</h2><p>{item.country || "Unknown region"} · {item.competition || item.league} · {item.sport}</p></div>
            <div className="profitBlock"><small>After modeled costs</small><strong>{Number(item.profit_pct).toFixed(2)}%</strong><span>{money(item.guaranteed_profit)}</span></div>
          </button>
          <div className="timingStrip"><span>First found <strong>{localTime(item.first_found_at || item.detected_at)}</strong></span><span>Last verified <strong>{localTime(item.last_verified_at)}</strong></span><span>Kickoff <strong>{localTime(item.start_time)}</strong></span></div>
          {expanded === key && <OpportunityDetails item={item} />}
        </article>;
      })}
      <HistoryPanel items={history} />
    </div><aside className="health"><div className="sectionTitle"><ShieldCheck size={18} />Platform health</div>{platforms.map((item) => <div className="platform" key={item.platform}><div><strong>{item.platform}</strong><small>{item.source_type || item.fetch_method} · {item.event_count || 0} events</small><small>{item.last_success_at ? `Last success ${localTime(item.last_success_at)}` : "No successful collection yet"}</small>{item.data_timestamp && <small>Source odds {localTime(item.data_timestamp)}</small>}{item.last_error && <p>{item.last_error}</p>}</div><span className={`badge ${item.status}`}>{item.status}</span></div>)}</aside></section>
  </main>;
}

function OpportunityDetails({ item }: { item: Opportunity }) {
  const [bankroll, setBankroll] = useState(String(Math.floor(item.total_stake)));
  const [firstObservation, setFirstObservation] = useState<Observation | null>(null);
  useEffect(() => {
    if (!item.fingerprint) return;
    void fetch(`${API_BASE}/api/opportunities/${item.fingerprint}/observations?limit=1`)
      .then((response) => response.ok ? response.json() : null)
      .then((payload) => setFirstObservation(payload?.observations?.[0] || null))
      .catch(() => undefined);
  }, [item.fingerprint]);
  const requested = Math.max(0, Number(bankroll) || 0); const safeMaximum = item.total_stake;
  const usable = Math.min(requested, safeMaximum); const scale = safeMaximum ? usable / safeMaximum : 0;
  const state = currentState(item); const actionable = state !== "expired" && Boolean(item.execution_safe);
  return <div className="details">
    {!actionable && <div className="expiredNotice"><AlertTriangle size={18} /><strong>Do not place these bets.</strong> Quotes expired or final execution checks are no longer valid. Run a new scan.</div>}
    <div className="bankrollControl"><div><strong>Your total amount across all bets</strong><small>Maximum supported by retained order-book depth: {money(safeMaximum)}</small></div><label>$<input type="number" min="0" max={safeMaximum} step="1" value={bankroll} onChange={(event) => setBankroll(event.target.value)} /></label></div>
    {requested > safeMaximum && <p className="inlineWarning">Requested amount capped to {money(safeMaximum)} because larger orders were not verified against available depth.</p>}
    <div className="guideTitle"><span>How to use this opportunity</span><small>The scanner never places bets for you. Stop if any platform price differs.</small></div>
    <ol className="betSteps">{item.legs.map((leg, index) => {
      const cost = leg.stake * scale; const payout = (leg.net_payout || leg.return) * scale; const shares = (leg.shares || 0) * scale;
      const isPoly = leg.bet_type === "prediction_yes" || leg.platform === "polymarket";
      const firstLeg = firstObservation?.legs?.find((candidate) => candidate.platform === leg.platform && candidate.outcome === leg.outcome);
      return <li key={`${leg.platform}-${leg.outcome}`}><div className="stepNumber">{index + 1}</div><div className="stepBody"><div className="stepHeading"><strong>{leg.platform}</strong><span>{isPoly ? "Buy YES contracts" : `${item.market_type} bet`}</span>{leg.url && <a href={leg.url} target="_blank" rel="noreferrer">Open market <ExternalLink size={14} /></a>}</div>
        <p>Select <strong>{leg.outcome}</strong> and spend <strong>{money(cost)}</strong>.</p>
        {isPoly ? <div className="legFacts"><span>Price when first found <b>{firstLeg?.price ? `${(firstLeg.price * 100).toFixed(1)}¢` : "Awaiting history"}</b></span><span>Best ask now/verified <b>{((leg.price || 0) * 100).toFixed(1)}¢</b></span><span>Average fill <b>{((leg.average_price || 0) * 100).toFixed(2)}¢</b></span><span>Do not pay above <b>{((leg.maximum_price || 0) * 100).toFixed(2)}¢ average</b></span><span>Contracts <b>{shares.toFixed(2)}</b></span><span>Winning payout <b>{money(payout)}</b></span></div>
          : <div className="legFacts"><span>Odds when first found <b>{firstLeg?.odds ? Number(firstLeg.odds).toFixed(2) : "Awaiting history"}</b></span><span>Current verified odds <b>{Number(leg.odds).toFixed(2)}</b></span><span>Minimum safe odds <b>{Number(leg.minimum_decimal_odds || leg.odds).toFixed(2)}</b></span><span>Winning payout <b>{money(payout)}</b></span></div>}
        <small>Quote fetched {localTime(leg.quote_fetched_at)}{leg.source_timestamp ? ` · source ${localTime(leg.source_timestamp)}` : ""}</small>
        {leg.warnings?.map((warning) => <p className="legWarning" key={warning}><AlertTriangle size={14} />{warning}</p>)}
      </div></li>;
    })}</ol>
    <div className="outcomeMatrix"><h3>Every possible result is covered</h3>{item.legs.map((leg) => <div key={`matrix-${leg.platform}-${leg.outcome}`}><span>{leg.outcome}</span><span>{leg.platform}</span><strong>{money((leg.net_payout || leg.return) * scale)}</strong></div>)}</div>
    <div className="returns"><span>Total across bets <strong>{money(usable)}</strong></span><span>Lowest payout <strong>{money(item.guaranteed_return * scale)}</strong></span><span className="profit">Profit after modeled costs <strong>{money(item.guaranteed_profit * scale)}</strong></span></div>
    <div className="checklist"><h3>Before placing anything</h3>{["Teams, kickoff, and market type match on every platform", "All settlement, overtime, cancellation, and void rules match", "Every current price and available size is at least as good as shown", "Place time-sensitive legs first; stop immediately if one changes"].map((text) => <p key={text}><CheckCircle2 size={16} />{text}</p>)}</div>
    {item.warnings?.map((warning) => <p className="inlineWarning" key={warning}>{warning}</p>)}
  </div>;
}

function HistoryPanel({ items }: { items: Lifecycle[] }) { return <section className="historyPanel"><div className="sectionTitle"><History size={18} />Opportunity history</div>{!items.length ? <p>No retained observations yet.</p> : items.map((item) => <div className="historyRow" key={item.fingerprint}><div><strong>{item.event_name}</strong><small>{item.country || "Unknown region"} · {item.competition || item.sport}</small></div><div><span className={`statusPill ${item.ended_at ? "ended" : item.latest_state}`}>{item.ended_at ? "ended" : item.latest_state}</span><small>{item.observation_count} observation{item.observation_count === 1 ? "" : "s"}</small></div><div><small>First {localTime(item.first_found_at)}</small><small>Last {localTime(item.last_seen_at)}</small></div><strong>{Number(item.latest_profit_pct).toFixed(2)}%</strong></div>)}</section>; }
function ClosestMarkets({ items }: { items: Comparison[] }) { if (!items.length) return null; return <div className="closest"><strong>Closest comparisons — not arbitrage</strong>{items.map((item) => <div className="closestItem" key={item.match_id}><span>{item.event_name}</span><b>{item.margin_pct >= 0 ? `${item.margin_pct.toFixed(2)}% below threshold` : `${item.break_even_gap_pct.toFixed(2)}% from break-even`}</b></div>)}</div>; }
function FilterSelect({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (value: string) => void }) { return <select value={value} onChange={(event) => onChange(event.target.value)} aria-label={label}><option value="">{label}</option>{values.map((item) => <option value={item} key={item}>{item}</option>)}</select>; }
function Metric({ label, value }: { label: string; value: string | number }) { return <div className="metric"><span>{label}</span><strong>{value}</strong></div>; }
