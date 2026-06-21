"use client";

import { Activity, AlertTriangle, ExternalLink, Filter, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

type Leg = {
  platform: string;
  outcome: string;
  odds: number;
  stake: number;
  return: number;
  url?: string | null;
  fee_pct?: number;
};

type Opportunity = {
  id?: string | number;
  match_id?: string;
  sport: string;
  event_name: string;
  league: string;
  market_type: string;
  profit_pct: number;
  total_stake: number;
  guaranteed_return: number;
  guaranteed_profit: number;
  legs: Leg[];
  warnings?: string[];
  detected_at?: string;
};

type PlatformStatus = {
  platform: string;
  enabled: boolean;
  status: string;
  fetch_method: string;
  source_type?: string;
  event_count: number;
  response_count?: number;
  last_error?: string | null;
  last_success_at?: string | null;
  data_timestamp?: string | null;
  updated_at?: string;
};

type Scan = {
  id?: string;
  started_at?: string;
  finished_at?: string;
  status?: string;
  event_count?: number;
  opportunity_count?: number;
};

type ComparisonLeg = {
  key: string;
  platform: string;
  outcome: string;
  odds: number;
  effective_odds: number;
  execution_cost_pct: number;
  url?: string | null;
};

type Comparison = {
  match_id: string;
  sport: string;
  event_name: string;
  league: string;
  market_type: string;
  margin_pct: number;
  break_even_gap_pct: number;
  platform_count: number;
  legs: ComparisonLeg[];
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const SPORTS = ["", "soccer", "nba", "nfl", "mlb", "nhl", "tennis"];
const PLATFORMS = ["", "polymarket", "stake", "bcgame", "shuffle", "cloudbet", "tgcasino", "thunderpick"];

export default function Dashboard() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [platforms, setPlatforms] = useState<PlatformStatus[]>([]);
  const [scan, setScan] = useState<Scan | null>(null);
  const [comparisons, setComparisons] = useState<Comparison[]>([]);
  const [scanInterval, setScanInterval] = useState(60);
  const [running, setRunning] = useState(false);
  const [sport, setSport] = useState("");
  const [platform, setPlatform] = useState("");
  const [minProfit, setMinProfit] = useState("0");
  const [expanded, setExpanded] = useState<string | number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadData() {
    setError(null);
    try {
      const params = new URLSearchParams();
      if (sport) params.set("sport", sport);
      if (platform) params.set("platform", platform);
      if (minProfit) params.set("minProfit", minProfit);

      const [oppsRes, closestRes, platformRes, scanRes, healthRes] = await Promise.all([
        fetch(`${API_BASE}/api/opportunities/latest?${params.toString()}`),
        fetch(`${API_BASE}/api/opportunities/closest?limit=10`),
        fetch(`${API_BASE}/api/platforms`),
        fetch(`${API_BASE}/api/scans/latest`),
        fetch(`${API_BASE}/api/health`)
      ]);

      if (!oppsRes.ok || !closestRes.ok || !platformRes.ok || !scanRes.ok || !healthRes.ok) {
        throw new Error("API request failed");
      }

      const oppsData = await oppsRes.json();
      const closestData = await closestRes.json();
      const platformData = await platformRes.json();
      const scanData = await scanRes.json();
      const healthData = await healthRes.json();
      setOpportunities(oppsData.opportunities || []);
      setComparisons(closestData.comparisons || []);
      setRunning(Boolean(oppsData.running || scanData.running));
      setPlatforms(platformData.platforms || []);
      setScan(scanData.scan || null);
      setScanInterval(Number(healthData.scan_interval_seconds || 60));
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load scanner data");
    }
  }

  async function runScan() {
    const token = window.prompt("Admin token");
    if (!token) return;
    setRunning(true);
    setError(null);
    try {
      const response = await fetch(`${API_BASE}/api/scans/run`, {
        method: "POST",
        headers: { "X-Admin-Token": token }
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || "Manual scan failed");
      }
      await loadData();
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Manual scan failed");
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => {
    void loadData();
    const timer = window.setInterval(() => void loadData(), 15_000);
    return () => window.clearInterval(timer);
  }, [sport, platform, minProfit]);

  const totals = useMemo(() => {
    const ok = platforms.filter((item) => item.status === "ok").length;
    return { ok };
  }, [platforms]);

  const visibleComparisons = useMemo(() => comparisons.filter((item) => {
    if (sport && item.sport !== sport) return false;
    if (platform && !item.legs.some((leg) => leg.platform === platform)) return false;
    return true;
  }).slice(0, 5), [comparisons, platform, sport]);

  return (
    <main className="shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Pre-match moneyline scanner</p>
          <h1>Arbitrage Scanner</h1>
        </div>
        <button className="primary" onClick={runScan} disabled={running}>
          <RefreshCw size={18} className={running ? "spin" : ""} />
          {running ? "Scanning" : "Refresh"}
        </button>
      </header>

      <section className="metrics" aria-label="Scanner summary">
        <Metric label="Latest scan" value={scan?.finished_at ? new Date(scan.finished_at).toLocaleString() : "No scan"} />
        <Metric label="Events" value={scan?.event_count ?? 0} />
        <Metric label="Opportunities" value={scan?.opportunity_count ?? opportunities.length} />
        <Metric label="Platforms ok" value={`${totals.ok}/${platforms.length || PLATFORMS.length - 1}`} />
        <Metric label="Auto scan" value={`Every ${scanInterval}s`} />
      </section>

      {error ? (
        <div className="notice">
          <AlertTriangle size={18} />
          {error}
        </div>
      ) : null}

      <section className="toolbar" aria-label="Opportunity filters">
        <Filter size={18} />
        <select value={sport} onChange={(event) => setSport(event.target.value)} aria-label="Sport">
          {SPORTS.map((item) => (
            <option key={item || "all"} value={item}>{item || "All sports"}</option>
          ))}
        </select>
        <select value={platform} onChange={(event) => setPlatform(event.target.value)} aria-label="Platform">
          {PLATFORMS.map((item) => (
            <option key={item || "all"} value={item}>{item || "All platforms"}</option>
          ))}
        </select>
        <label>
          Min profit
          <input value={minProfit} onChange={(event) => setMinProfit(event.target.value)} inputMode="decimal" />
        </label>
      </section>

      <section className="layout">
        <div className="opportunities">
          <div className="sectionTitle">
            <Activity size={18} />
            Opportunities
          </div>
          <div className="table">
            <div className="row head">
              <span>Event</span>
              <span>Sport</span>
              <span>Profit</span>
              <span>Legs</span>
            </div>
            {opportunities.length === 0 ? (
              <div>
                <div className="empty">
                  No guaranteed arbitrage above the configured threshold in this scan.
                  The closest executable comparisons are shown below and are not betting recommendations.
                </div>
                <ClosestMarkets items={visibleComparisons} />
              </div>
            ) : opportunities.map((item, index) => {
              const key = item.id || item.match_id || index;
              return (
                <div key={key}>
                  <button className="row data" onClick={() => setExpanded(expanded === key ? null : key)}>
                    <span>
                      <strong>{item.event_name}</strong>
                      <small>{item.league || "Unknown league"}</small>
                    </span>
                    <span>{item.sport}</span>
                    <span className="profit">{Number(item.profit_pct).toFixed(2)}%</span>
                    <span>{item.legs.map((leg) => leg.platform).join(" / ")}</span>
                  </button>
                  {expanded === key ? <OpportunityDetails item={item} /> : null}
                </div>
              );
            })}
          </div>
        </div>

        <aside className="health">
          <div className="sectionTitle">
            <ShieldCheck size={18} />
            Platform Health
          </div>
          {platforms.map((item) => (
            <div className="platform" key={item.platform}>
              <div>
                <strong>{item.platform}</strong>
                <small>{item.source_type || item.fetch_method} - {item.event_count || 0} events</small>
                <small>{item.last_success_at ? `Last success ${new Date(item.last_success_at).toLocaleString()}` : "No successful collection yet"}</small>
                {item.data_timestamp ? <small>Odds timestamp {new Date(item.data_timestamp).toLocaleString()}</small> : null}
              </div>
              <span className={`badge ${item.status}`}>{item.status}</span>
              {item.last_error ? <p>{item.last_error}</p> : null}
            </div>
          ))}
        </aside>
      </section>
    </main>
  );
}

function ClosestMarkets({ items }: { items: Comparison[] }) {
  if (!items.length) return null;
  return (
    <div className="closest">
      <div className="closestTitle">Closest markets - not arbitrage</div>
      {items.map((item) => (
        <div className="closestItem" key={item.match_id}>
          <div>
            <strong>{item.event_name}</strong>
            <small>{item.sport} - {item.legs.map((leg) => leg.platform).join(" / ")}</small>
          </div>
          <div className={item.margin_pct >= 0 ? "nearPositive" : "nearNegative"}>
            {item.margin_pct >= 0
              ? `${item.margin_pct.toFixed(2)}% below configured threshold`
              : `${item.break_even_gap_pct.toFixed(2)}% from break-even`}
          </div>
        </div>
      ))}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function OpportunityDetails({ item }: { item: Opportunity }) {
  return (
    <div className="details">
      <div className="legs">
        {item.legs.map((leg) => (
          <div className="leg" key={`${leg.platform}-${leg.outcome}`}>
            <strong>{leg.platform}</strong>
            <span>{leg.outcome}</span>
            <span>@ {Number(leg.odds).toFixed(2)}</span>
            <span>${Number(leg.stake).toFixed(2)}</span>
            {leg.url ? (
              <a href={leg.url} target="_blank" rel="noreferrer" aria-label={`Open ${leg.platform}`}>
                <ExternalLink size={16} />
              </a>
            ) : null}
          </div>
        ))}
      </div>
      <div className="returns">
        <span>Stake ${Number(item.total_stake).toFixed(2)}</span>
        <span>Return ${Number(item.guaranteed_return).toFixed(2)}</span>
        <strong>Profit ${Number(item.guaranteed_profit).toFixed(2)}</strong>
      </div>
      {item.warnings?.length ? <p className="warning">{item.warnings.join("; ")}</p> : null}
    </div>
  );
}
