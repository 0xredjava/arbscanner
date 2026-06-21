# Sportsbook Data Integration — Final Implementation Record

## Status

**Completed and deployed on 2026-06-21.**

The implementable project scope is finished. Six platforms return current,
validated pre-match odds in production. Stake is the only non-collecting
platform and is intentionally reported as `unavailable`: no compliant public,
no-login sportsbook source was found, and the project does not use sessions,
private cookies, CAPTCHA bypasses, or access-control workarounds.

Production endpoints:

- Dashboard: <https://arbscanner-alpha.vercel.app>
- API: <https://api-production-c9c2.up.railway.app>
- Health: <https://api-production-c9c2.up.railway.app/api/health>
- Platform status: <https://api-production-c9c2.up.railway.app/api/platforms>
- Latest scan: <https://api-production-c9c2.up.railway.app/api/scans/latest>
- Latest opportunities: <https://api-production-c9c2.up.railway.app/api/opportunities/latest>

Latest implementation commit at completion: `c9a7130` (`Fix Cloudbet Feed API
integration`).

## Goal and constraints

- [x] Collect reliable pre-match two-way moneyline and soccer 1X2 odds.
- [x] Prefer official/on-chain/documented APIs, then stable public first-party
  feeds; use Playwright only as a formally justified last resort.
- [x] Use public/no-login market data. A documented API key is permitted where
  the official provider requires one; credentials remain environment secrets.
- [x] Do not use account sessions, private cookies, private keys, CAPTCHA
  bypasses, or proxy/access-control bypassing.
- [x] Reject live, closed, suspended, malformed, stale, already-started, and
  out-of-horizon events.
- [x] Preserve only sanitized source fixtures; never commit credentials or
  personal data.
- [x] Report inaccessible sources honestly rather than displaying false green
  health.

## Phase 1 — Source discovery

**Complete.** The dated evidence, authentication requirements, rate limits,
response formats, aggregator evaluation, source choices, and Playwright decision
gate are recorded in [`SOURCE_DECISIONS.md`](SOURCE_DECISIONS.md).

- [x] Revalidated Polymarket Gamma discovery, keyset pagination, CLOB token IDs,
  public executable pricing, sports tags, timestamps, and Polygon contract role.
- [x] Revalidated Cloudbet's official Feed API, `X-API-Key` authentication,
  `/pub/v2/odds/events` time-range contract, competition envelopes, and canonical
  market identifiers.
- [x] Investigated Stake documentation, public network/static configuration,
  providers, aggregators, and the public challenge behavior.
- [x] Identified BC.Game's anonymous sportsbook-provider REST snapshots.
- [x] Identified Shuffle's public first-party sports GraphQL endpoint.
- [x] Identified TG.Casino's anonymous sportsbook-provider REST snapshots.
- [x] Identified Thunderpick's public same-origin REST endpoints.
- [x] Revalidated The Odds API and rejected generic/consensus feeds that could
  not prove the named bookmaker's offered price.
- [x] Evaluated on-chain, API, GraphQL, WebSocket, provider, aggregator, and
  public-browser options before implementation.
- [x] Determined that no production Playwright collector is justified.

## Selected sources and production state

| Platform | Selected source | Authentication | Parser/tests | Production result |
|---|---|---|---|---|
| Polymarket | Official Gamma `/events/keyset` + public CLOB `/prices` | None | Native parser, fixture, keyset and CLOB regressions | Healthy; complete bounded pagination |
| Cloudbet | Official Feed API `/pub/v2/odds/events` | Railway `CLOUDBET_API_KEY` | Native competition/market parser, fixture, authenticated smoke test | Healthy; 85 events in final verification |
| Stake | No acceptable source | Not used | Explicit unavailable adapter and health-state coverage | `unavailable` by policy |
| BC.Game | Anonymous public provider REST snapshot | None | Shared native provider parser and fixture | Healthy; 385 events in final verification |
| Shuffle | Public first-party sports GraphQL | None | Native GraphQL parser and fixture | Healthy; 65 events in final verification |
| TG.Casino | Anonymous public provider REST snapshot | None | Shared native provider parser and fixture | Healthy; 476 events in final verification |
| Thunderpick | Public same-origin REST | None | Native parser, fixture, string/dictionary regression | Healthy; 227 events in final verification |

Event counts are snapshots and naturally fluctuate as fixtures open, start, or
close.

## Phase 2 — Native source adapters

- [x] Standardized adapters on `BaseScraper` and `ScrapedEvent`.
- [x] Kept each transport and response shape inside its platform adapter.
- [x] Emitted stable event/selection IDs, platform, sport, participants, league,
  UTC start time, live state, market type, named outcomes, decimal odds, and
  direct URLs where available.
- [x] Added defensive validation for dictionaries, lists, nested envelopes,
  nulls, strings, statuses, prices, and malformed selections.
- [x] Removed the generic shared website JSON assumption.
- [x] Removed all production Playwright scrapers, Chromium installation, and the
  Playwright runtime dependency.
- [x] Implemented bounded retries, timeouts, rate-limit handling, and isolated
  per-platform failures.

Platform-specific implementation:

- [x] Polymarket combines binary YES markets into coherent two-way/1X2 events,
  paginates Gamma to its terminal cursor, and enriches tokens with CLOB SELL
  prices.
- [x] Cloudbet uses required `from`/`to` Unix timestamps, exact official market
  keys, nested competition parsing, NBA/NFL/NHL/MLB league filters, BACK-only
  selections, and virtual/simulated competition rejection.
- [x] BC.Game and TG.Casino share a dedicated provider-snapshot parser with
  platform-specific hosts and brand IDs.
- [x] Shuffle parses its fractional sports GraphQL prices and participant order.
- [x] Thunderpick parses native match/event-group/selection structures without
  assuming every list member is a dictionary.
- [x] Stake raises a deliberate `SourceStatusError("unavailable", ...)`.

## Phase 3 — Matching and arbitrage quality

- [x] Normalize decimal odds and source-specific participant/outcome names.
- [x] Require both competitors to match independently; league similarity cannot
  rescue an unrelated fixture.
- [x] Reject same-team rematches outside the configured start-time window.
- [x] Correctly align outcomes when two platforms reverse home/away order.
- [x] Require the exact outcome set (`home/away` or `home/draw/away`).
- [x] Require at least two platforms among selected cross-platform arb legs.
- [x] Reject stale, live, duplicate-outcome, invalid-price, past, and more-than-
  14-day events before matching.
- [x] Remove the production false positives caused by unrelated same-league
  fixtures and reversed outcomes.
- [x] Correct Polymarket execution pricing to use the CLOB `BUY` ask rather than
  the non-executable `SELL` bid.
- [x] Remove invented flat sportsbook fees (bookmaker margin is already present
  in fixed odds) and model Polymarket's official per-market taker fee curve.
- [x] Rank and expose closest executable market comparisons as clearly labeled
  near misses, without presenting them as guaranteed arbitrage.

## Phase 4 — Platform health and persistence

- [x] Implement `ok`, `empty`, `blocked`, `unavailable`, `degraded`, and `failed`.
- [x] Record source/fetch type, event count, response count, duration, last
  success, last error, and source data timestamp.
- [x] Never report zero validated events as `ok`.
- [x] Keep one failed source from aborting successful source persistence.
- [x] Persist scan runs, platform health, normalized events, and opportunities to
  Supabase.
- [x] Apply migration `20260621010000_platform_health.sql` for `source_type`,
  `response_count`, and `data_timestamp`.
- [x] Verify local and remote Supabase migration histories match.

## Phase 5 — Tests and validation

- [x] Add sanitized fixtures for Polymarket, Cloudbet, the shared provider feed,
  Shuffle, and Thunderpick.
- [x] Cover Cloudbet's current competition envelope, exact league filtering, and
  simulated competition exclusion.
- [x] Cover Polymarket six-page completion and bounded truncation.
- [x] Cover Thunderpick's former `'str' object has no attribute 'get'` crash.
- [x] Cover success, empty, blocked, unavailable, degraded, and failed health
  transitions.
- [x] Cover unrelated same-league fixtures, rematch time windows, single-platform
  false arbs, reversed home/away order, profitable arbs, and non-profitable
  markets.
- [x] Keep unit tests deterministic and independent of live websites.
- [x] Run authenticated/public live smoke checks separately from unit tests.
- [x] Final suite: **22 tests passed**.
- [x] Final Next.js 14.2.35 production build passed.
- [x] Full live local scan and low-confidence match audit completed.

## Phase 6 — Production rollout

### Supabase

- [x] Initial and platform-health migrations applied to project
  `kbnhhncgupyehjihjqnt`.
- [x] `scan_runs`, `platform_status`, `events`, and `opportunities` verified.
- [x] Server credentials remain deployment variables and are not committed.

### Railway

- [x] API deployed to project `813d0cba-5880-4f64-9ffe-c1fd9f835b1a`, service
  `0be75172-bb72-4c63-9ae3-1620f8047126` (`api`).
- [x] Dockerfile build, `/api/health` health check, background scanning, and all
  public API endpoints verified.
- [x] Moved production to Railway's Singapore region after the provider feeds
  returned HTTP 503 from US-West egress.
- [x] Stored `CLOUDBET_API_KEY`, Supabase credentials, and `ADMIN_TOKEN` only as
  Railway environment variables.
- [x] Final Cloudbet-enabled deployment used `/railway.toml`, the Dockerfile
  builder, and `asia-southeast1-eqsg3a`.
- [x] Final production scan showed six healthy collectors and Stake explicitly
  unavailable.
- [x] Background scans start on API startup and now run on an exact fixed
  60-second start-to-start cadence without overlap.

Operational deployment note: Railway variable changes and some Git webhook
deploys produced a generic Railpack/US-West manifest. The verified deployment
path is `railway up --detach --service api --environment production`, which
applies the committed `railway.toml`, Dockerfile, health check, and Singapore
region. Always inspect the exact deployment manifest before handoff.

### Vercel

- [x] Dashboard deployed to `https://arbscanner-alpha.vercel.app`.
- [x] Expanded platform health, source type, event count, last success, source
  timestamp, and explicit unavailable/degraded explanations are displayed.
- [x] Dashboard API wiring, HTTP 200 response, and final browser rendering were
  verified.
- [x] Next.js upgraded from 14.2.0 to patched 14.2.35.
- [x] Local `frontend/` is linked to Vercel and production deployment through the
  authenticated Vercel CLI was verified.
- [x] Main dashboard polls production state every 15 seconds and displays the
  configured automatic scan cadence.
- [x] Added the unlinked `/events-inspector` diagnostic route and
  `/api/events/latest` endpoint for checking every persisted platform event and
  outcome; no navigation link exposes it in the regular UI.
- [x] Added a closest-markets explanation when no guaranteed opportunity clears
  the configured threshold.

## Acceptance criteria

- [x] Every platform has a completed, dated source investigation.
- [x] No Playwright fallback was added without exhausting safer sources; none was
  ultimately required or approved.
- [x] Every enabled collecting source has deterministic parser coverage.
- [x] Production never displays `ok` for a source that failed to return validated
  events.
- [x] Multiple independent platforms return overlapping current fixtures.
- [x] Matching and arbitrage calculation are guarded against the observed false-
  positive classes.
- [x] Supabase, Railway, API, and Vercel passed end-to-end production checks.
- [x] Source choices, limitations, revalidation evidence, secrets, and deployment
  procedure are documented.

## Completion answer

Yes: the implementable and policy-compliant scope is complete, tested, pushed,
and deployed.

The only target without collected odds is Stake. This is not an unfinished
adapter: it is an explicit product state caused by the absence of a supported
public source. Enabling it would require new external availability or a change to
the project's no-login/no-bypass constraint.

Optional future enhancements, not blockers for completion:

- Revalidate Stake if it publishes an official public sportsbook feed.
- Add public WebSocket freshness paths for sources that currently use snapshots.
- Add automated production alerts and longer-term CPU/memory dashboards.
- Repair the Railway Git-webhook manifest behavior so manual `railway up` is no
  longer the safest deployment path.
- Connect the Vercel GitHub App when repository permission is available; the
  verified CLI deployment path remains functional.
- Rotate the Cloudbet key if it is ever exposed outside the private deployment
  workflow.
