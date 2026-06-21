# Arbitrage Scanner - Implementation Plan and Integration Record

## Status

**Implemented and deployed to Supabase, Railway, and Vercel on 2026-06-21.**

The source-integration scope below was completed and deployed on 2026-06-21,
but the product is not considered complete as an actionable arbitrage tool. A
reported Cuiaba EC vs Londrina EC opportunity exposed gaps between a displayed
Polymarket quote and the price/cost a user could actually execute, and the
dashboard does not yet teach a new user how to place and verify every leg. The
work in the next section is now the highest-priority implementation scope.

## Reopened scope - actionable, auditable opportunities

### Confirmed product findings

- [x] The scanner is **not limited to Brazilian games**. The default configured
  scope is worldwide soccer plus NBA, tennis, NFL, NHL, and MLB. A Brazilian
  Serie B event appeared because it was an overlapping event returned by the
  enabled sources, not because Brazil is a country filter.
- [x] The current dashboard shows sport and source league, but not country or a
  clear coverage explanation. This makes worldwide coverage look accidental.
- [x] `detected_at` is already generated and persisted on each opportunity, and
  scan start/finish timestamps are persisted, but opportunity cards do not show
  the detection time and the API only returns opportunities from the latest
  scan. This is insufficient to prove when an opportunity first appeared, how
  long it lasted, or whether a user could have acted on it.
- [x] The current Polymarket adapter records one top-of-book BUY quote per
  outcome and the calculator sizes the full bankroll as if every share can fill
  at that one price. It does not retain the order-book levels, quote timestamp,
  average fill price, or a post-sizing revalidation result.
- [x] The reported Londrina card displayed decimal odds `6.67`, equivalent to a
  15-cent contract, while the user observed an 18-cent executable price. At 18
  cents, a $162.14 order buys about 900.78 shares and has a $900.78 gross winning
  payout before fees, not the card's displayed guaranteed return. Whether the
  quote moved after detection or the original quote was wrong cannot be proven
  from the data currently saved; the missing quote history is itself a defect.

### Phase 7 - execution-safe pricing and stake math (P0)

- [x] Replace single-price Polymarket enrichment with an order-book quote that
  retains all ask levels needed to fill the proposed size, the CLOB/source
  timestamp, fetch timestamp, token ID, market ID, best ask, available size at
  best ask, and raw response needed for later audit.
- [x] Calculate Polymarket legs in native prediction-market units: limit price,
  dollars spent, shares/contracts bought, volume-weighted average fill price,
  gross payout if the outcome wins, fee, net payout, and unfilled remainder.
  Keep sportsbook legs in decimal-odds units and explicitly label their stake
  and payout semantics.
- [x] Size the arb against executable depth at every required price level. Scale
  the entire opportunity down to the largest common bankroll that all legs can
  fill; reject it if depth, minimum order size, precision, or configured safety
  buffer makes the guaranteed profit fall below the threshold.
- [x] Use conservative currency rounding for each platform and recompute the
  worst-case net payout after rounding. Never derive the displayed guaranteed
  return from unrounded internal allocations.
- [x] Perform a fresh quote-and-depth revalidation after stake sizing and just
  before returning an opportunity. Reject or mark the card expired if any leg's
  executable price, available size, market status, or settlement mapping has
  changed beyond tolerance.
- [x] Define a short quote TTL and show `fresh`, `aging`, or `expired` based on
  the oldest leg quote. Do not label stale or partially fillable cards as
  guaranteed arbitrage.
- [x] Store the calculation inputs and outputs as an immutable audit snapshot,
  including raw odds/price, effective odds, depth used, fees, slippage buffer,
  rounded stake, expected payout per leg, and worst-case profit.
- [ ] Investigate the historical Cuiaba EC vs Londrina EC market using saved
  production identifiers if available. Record whether the 15-cent value came
  from Gamma, the CLOB ask, a moving quote, or a response-parsing error. Do not
  treat this historical diagnosis as a blocker for fixing the unsafe model.

### Phase 8 - beginner-friendly opportunity experience (P0)

- [x] Redesign each opportunity as a guided bet slip instead of a compact odds
  table. Lead with event, competition/country, kickoff, first found, last
  verified, quote age, executable bankroll, and a prominent freshness state.
- [x] Add a plain-language `How to use this opportunity` sequence with one
  numbered step per leg. Each step must show platform, exact outcome to select,
  bet type (`moneyline/1X2` or `YES contract`), amount to spend, displayed price
  or minimum acceptable decimal odds, expected shares where applicable, payout,
  and a direct market link.
- [x] Add an editable bankroll control. Recalculate allocations from the user's
  amount, cap it to executable liquidity, and explain when the safe maximum is
  lower than the requested bankroll.
- [x] Show an outcome matrix proving coverage: Cuiaba win, draw, and Londrina
  win each point to exactly one leg and each row shows the same conservative net
  payout. Block display if the outcome set is incomplete or duplicated.
- [x] Separate `price when found`, `price now`, and `minimum safe price`; visually
  flag a changed leg and disable the action checklist when the arb no longer
  clears the threshold.
- [x] Replace ambiguous labels such as `Stake $1000` and `Return $1054.08` with
  `Total amount across all bets`, `Lowest payout across outcomes`, and
  `Guaranteed profit after modeled costs`, each with a short tooltip.
- [x] Add a pre-bet checklist: verify event/teams and kickoff, confirm all three
  settlement rules match (including overtime/void rules), confirm current
  prices and available size, place time-sensitive legs first, and stop if any
  displayed value changes. Make clear that the scanner does not place bets.
- [x] Display source and calculation warnings beside the affected leg rather
  than as one generic sentence below the card.
- [x] Add responsive/mobile layouts and accessible states for fresh, changed,
  expired, incomplete, and liquidity-limited opportunities.

### Phase 9 - geography and coverage clarity (P1)

- [x] Add normalized country/region and competition fields to events instead of
  relying only on free-text league names. Preserve the source values for audit.
- [x] Show a dashboard coverage summary generated from the latest successful
  scan: enabled sports, countries/regions seen, competitions seen, platforms,
  and explicit source limitations. Label it `worldwide where sources provide
  markets`, not `all games worldwide`.
- [x] Add sport, country/region, competition, and platform filters. Derive
  filter options from collected events rather than a hard-coded Brazil or league
  list.
- [x] Add coverage tests proving that no implicit Brazil-only filter exists and
  that international soccer events can pass collection, matching, and display.

### Phase 10 - opportunity lifecycle and timing evidence (P0)

- [x] Introduce a stable opportunity fingerprint based on canonical event,
  market, outcomes, and selected platforms. Do not use a per-scan database row
  ID as the lifecycle identity.
- [x] Add an `opportunity_observations` time-series table with scan ID,
  fingerprint, observed/detected time, quote times, prices, depth, allocations,
  profit, and state. Observations are append-only and retained after later scans
  find no opportunity.
- [x] Add lifecycle fields/records for `first_found_at`, `last_seen_at`,
  `last_verified_at`, `ended_at`, observation count, and end reason (`price
  moved`, `liquidity`, `market closed`, `source unavailable`, or `not matched`).
- [x] Distinguish timestamps clearly: scan started, source data time, quote
  fetched, opportunity first found, last verified, and event kickoff. Store UTC;
  render in the user's local timezone with the UTC value available on hover or
  detail view.
- [x] Keep the existing latest endpoint for the dashboard, and add opportunity
  history/detail endpoints that can return lifecycle records and observations by
  fingerprint. Include scan IDs so every card can be traced to platform health
  and source collection results.
- [x] Add a history view with active/expired status, duration, first-found and
  last-seen times, profit/price changes, and a compact timeline. This is the
  primary evidence for whether the scanner found a real, actionable window.
- [x] Add retention/indexing policy and migration/backfill behavior. Existing
  rows may use `detected_at` as an explicitly labeled approximate first-found
  value; never invent missing quote timestamps.

### Phase 11 - verification and rollout

- [x] Add deterministic calculator tests for the reported three-leg example at
  both 15 cents and 18 cents, multi-level partial fills, fees, conservative
  rounding, bankroll scaling, quote expiry, price movement, and insufficient
  depth.
- [x] Add parser contract tests using realistic Polymarket order-book responses,
  including absent books, crossed/empty books, malformed levels, and source
  timestamps. Do not use a mock shape invented only to fit the implementation.
- [ ] Add API/storage tests for append-only observations, stable fingerprints,
  first/last timestamps, disappearance/end reasons, history retention, and
  concurrent/repeated scans.
- [ ] Add frontend tests for the guided instructions, outcome coverage matrix,
  local-time rendering, changing/expired states, requested-bankroll cap, and
  exact per-leg payout math.
- [ ] Run shadow mode before enabling the new cards: persist observations and
  compare the indicated fills with later CLOB/order-book states without calling
  an opportunity actionable.
- [ ] Add production telemetry for quote age, revalidation failures, insufficient
  depth, price movement, observation duration, and opportunities rejected by
  execution checks.
- [x] Roll out behind an `execution_safe_opportunities` feature flag. Remove the
  old guaranteed-return presentation only after migrations, history endpoints,
  tests, shadow validation, and mobile/browser review pass.

### Reopened acceptance criteria

- [x] A user can tell from the dashboard that scanning is multi-sport and not
  Brazil-only, and can inspect/filter the actual countries and competitions
  covered by the latest data.
- [x] Every displayed opportunity shows when it was first found, when each quote
  was fetched, when it was last revalidated, its current age/state, and the scan
  that produced the observation.
- [x] For every leg, displayed spend, odds/price, shares where relevant, fees,
  and net payout reconcile to the cent. The lowest leg payout equals the summary
  payout after conservative rounding.
- [x] An 18-cent Polymarket contract cannot be presented or allocated as a
  15-cent/6.67-odds fill, and the full suggested order must be supported by the
  retained executable order-book depth.
- [x] A beginner can follow a numbered set of platform-specific steps and verify
  that all possible match outcomes are covered before placing anything.
- [x] Opportunity history remains queryable after the window disappears and is
  sufficient to distinguish a real short-lived arb from stale or incorrect
  data.
- [x] No card uses `guaranteed` when a quote is expired, depth is insufficient,
  settlement mapping is unverified, or the final revalidation failed.

### Implementation order

1. Freeze the old card's `guaranteed` claim and add visible detection/quote-age
   warnings.
2. Implement executable depth snapshots, native Polymarket units, conservative
   sizing, and final revalidation.
3. Add lifecycle migrations, append-only observations, and history APIs.
4. Build the guided bet-slip UI, timing/history views, and coverage filters.
5. Run deterministic tests and production shadow validation, then enable the
   feature flag.

The original source-integration scope described below is finished. Six platforms return current,
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
