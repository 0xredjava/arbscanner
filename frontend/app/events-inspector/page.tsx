"use client";

import { ExternalLink, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type Outcome = {
  name: string;
  decimal_odds: number;
  implied_prob: number;
  fee_adjusted_prob: number;
  liquidity_usd?: number | null;
  url?: string | null;
};

type CollectedEvent = {
  platform: string;
  sport: string;
  event_key: string;
  event_id: string;
  home_team: string;
  away_team: string;
  league: string;
  start_time?: string | null;
  market_type: string;
  url?: string | null;
  outcomes: Outcome[];
};

type Payload = {
  scan?: { id?: string; finished_at?: string; duration_ms?: number } | null;
  events: CollectedEvent[];
  event_count: number;
  counts_by_platform: Record<string, number>;
  running: boolean;
  scan_interval_seconds: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function EventsInspector() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [platform, setPlatform] = useState("");
  const [sport, setSport] = useState("");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      setError(null);
      const response = await fetch(`${API_BASE}/api/events/latest?limit=5000`, {
        cache: "no-store"
      });
      if (!response.ok) throw new Error(`API returned ${response.status}`);
      setPayload(await response.json());
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Unable to load collected events");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  const platforms = useMemo(
    () => Object.keys(payload?.counts_by_platform || {}).sort(),
    [payload]
  );
  const sports = useMemo(
    () => Array.from(new Set((payload?.events || []).map((event) => event.sport))).sort(),
    [payload]
  );
  const grouped = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const groups: Record<string, CollectedEvent[]> = {};
    for (const event of payload?.events || []) {
      if (platform && event.platform !== platform) continue;
      if (sport && event.sport !== sport) continue;
      if (needle) {
        const text = `${event.home_team} ${event.away_team} ${event.league} ${event.event_id}`.toLowerCase();
        if (!text.includes(needle)) continue;
      }
      (groups[event.platform] ||= []).push(event);
    }
    return groups;
  }, [payload, platform, sport, query]);
  const visibleCount = Object.values(grouped).reduce((total, events) => total + events.length, 0);

  return (
    <main className={styles.shell}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Unlinked diagnostic route</p>
          <h1>Collected Events Inspector</h1>
          <p className={styles.subtitle}>Latest persisted pre-match events and normalized outcome odds.</p>
        </div>
        <button className={styles.refresh} onClick={() => void load()} disabled={loading}>
          <RefreshCw size={17} className={loading ? styles.spin : ""} />
          Refresh
        </button>
      </header>

      <section className={styles.metrics}>
        <Metric label="Latest scan" value={payload?.scan?.finished_at ? new Date(payload.scan.finished_at).toLocaleString() : "No scan"} />
        <Metric label="Collected events" value={payload?.event_count || 0} />
        <Metric label="Visible events" value={visibleCount} />
        <Metric label="Automatic cadence" value={`Every ${payload?.scan_interval_seconds || 60}s`} />
      </section>

      <section className={styles.platformSummary} aria-label="Platform event counts">
        <button className={!platform ? styles.activePill : styles.pill} onClick={() => setPlatform("")}>All</button>
        {platforms.map((name) => (
          <button
            key={name}
            className={platform === name ? styles.activePill : styles.pill}
            onClick={() => setPlatform(platform === name ? "" : name)}
          >
            {name} <strong>{payload?.counts_by_platform[name] || 0}</strong>
          </button>
        ))}
      </section>

      <section className={styles.filters}>
        <label className={styles.search}>
          <Search size={17} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search team, league, or event ID" />
        </label>
        <select value={sport} onChange={(event) => setSport(event.target.value)}>
          <option value="">All sports</option>
          {sports.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </section>

      {error ? <div className={styles.error}>{error}</div> : null}
      {loading && !payload ? <div className={styles.loading}>Loading latest persisted scan...</div> : null}

      <section className={styles.groups}>
        {!loading && visibleCount === 0 ? (
          <div className={styles.loading}>No collected events match these filters.</div>
        ) : null}
        {Object.entries(grouped).sort(([a], [b]) => a.localeCompare(b)).map(([name, events]) => (
          <details className={styles.group} key={name} open={Boolean(platform)}>
            <summary>
              <span>{name}</span>
              <strong>{events.length} events</strong>
            </summary>
            <div className={styles.eventList}>
              {events.map((event) => (
                <article className={styles.event} key={`${event.platform}-${event.event_id}-${event.event_key}`}>
                  <div className={styles.eventInfo}>
                    <div>
                      <strong>{event.home_team} vs {event.away_team}</strong>
                      <span>{event.sport} - {event.league || "Unknown league"} - {event.market_type}</span>
                    </div>
                    <div className={styles.eventMeta}>
                      <span>{event.start_time ? new Date(event.start_time).toLocaleString() : "No start time"}</span>
                      <code>{event.event_id}</code>
                    </div>
                  </div>
                  <div className={styles.outcomes}>
                    {event.outcomes.map((outcome) => (
                      <div className={styles.outcome} key={`${event.event_id}-${outcome.name}`}>
                        <span>{outcome.name}</span>
                        <strong>{Number(outcome.decimal_odds).toFixed(3)}</strong>
                        <small>{(Number(outcome.implied_prob) * 100).toFixed(2)}%</small>
                      </div>
                    ))}
                    {event.url ? (
                      <a className={styles.open} href={event.url} target="_blank" rel="noreferrer" title="Open source event">
                        <ExternalLink size={17} />
                      </a>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          </details>
        ))}
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className={styles.metric}><span>{label}</span><strong>{value}</strong></div>;
}
