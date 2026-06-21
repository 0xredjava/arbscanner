# Sportsbook Data Integration Implementation Plan

## Goal

Collect reliable, public, pre-match moneyline odds from every supported platform, normalize them into the existing scanner, and produce honest platform-health reporting.

Source priority is mandatory:

1. Official on-chain data
2. Official documented API
3. Stable first-party public API, GraphQL, or WebSocket endpoint
4. Reputable supported odds aggregator
5. Public, no-login Playwright interception as the absolute last option

Playwright must not be selected until the API/on-chain investigation for that platform is completed and documented.

## Scope and constraints

- [ ] Read public, unauthenticated pre-match odds only.
- [ ] Support two-way moneyline and three-way soccer 1X2 markets first.
- [ ] Do not use account sessions, private cookies, private keys, CAPTCHA bypasses, or proxy bypassing.
- [ ] Respect applicable rate limits, access controls, and terms.
- [ ] Treat inaccessible or blocked platforms as unavailable instead of reporting a false healthy state.
- [ ] Preserve raw source samples as sanitized test fixtures; never store credentials or personal data.

## Phase 1: Source discovery — required before implementation

**Completed 2026-06-21.** See [`SOURCE_DECISIONS.md`](SOURCE_DECISIONS.md) for the
dated evidence, source/auth/rate-limit matrix, aggregator evaluation, and the
Playwright decision gate.

Create a source report for every platform. Record the date checked, evidence, candidate URLs or contracts, authentication requirements, rate limits, response format, market coverage, and final source decision.

### Polymarket — known public/on-chain baseline

- [ ] Revalidate Gamma API event discovery.
- [ ] Revalidate CLOB prices/order books and token identifiers.
- [ ] Check whether Polygon contracts or an official indexer provide anything more reliable than the current APIs.
- [ ] Confirm sports tags, active/closed filtering, start times, liquidity, and outcome prices.
- [ ] Document the selected combination of Gamma, CLOB, and on-chain data.

### Cloudbet — previously documented API, currently returning zero

- [ ] Search current official Cloudbet API documentation.
- [ ] Verify whether the existing `/pub/v2/odds` endpoints still exist or moved.
- [ ] Check official REST, GraphQL, and WebSocket options.
- [ ] Inspect public first-party network calls and static application configuration if documentation is incomplete.
- [ ] Determine whether an API key is required and whether a read-only/public key is available.
- [ ] Capture sanitized real responses for supported sports and moneyline markets.
- [ ] Document whether Cloudbet will use an official API, public first-party endpoint, aggregator, or Playwright fallback.

### Stake

- [ ] Search official Stake developer/API documentation for sportsbook data.
- [ ] Check for public REST, GraphQL, WebSocket, or feed endpoints used by the public sportsbook.
- [ ] Check whether sportsbook markets are available through an official provider or documented integration.
- [ ] Investigate relevant on-chain data only if it contains actual sportsbook markets and executable odds.
- [ ] Inspect public static configuration and public network calls without logging in.
- [ ] Check supported aggregators for Stake-specific odds.
- [ ] Document evidence for the selected source or why Playwright is unavoidable.

### BC.Game

- [ ] Search official BC.Game developer/API documentation for sportsbook data.
- [ ] Check for public REST, GraphQL, WebSocket, or feed endpoints used by the public sportsbook.
- [ ] Identify any first-party or sportsbook-provider API exposed to anonymous visitors.
- [ ] Investigate relevant on-chain data only if it contains actual sportsbook odds.
- [ ] Inspect public static configuration and public network calls without logging in.
- [ ] Check supported aggregators for BC.Game-specific odds.
- [ ] Document evidence for the selected source or why Playwright is unavoidable.

### Shuffle

- [ ] Search official Shuffle developer/API documentation for sportsbook data.
- [ ] Check for public REST, GraphQL, WebSocket, or feed endpoints used by the public sportsbook.
- [ ] Identify any first-party or sportsbook-provider API exposed to anonymous visitors.
- [ ] Investigate relevant on-chain data only if it contains actual sportsbook odds.
- [ ] Inspect public static configuration and public network calls without logging in.
- [ ] Check supported aggregators for Shuffle-specific odds.
- [ ] Document evidence for the selected source or why Playwright is unavoidable.

### TG.Casino

- [ ] Search official TG.Casino developer/API documentation for sportsbook data.
- [ ] Check for public REST, GraphQL, WebSocket, or feed endpoints used by the public sportsbook.
- [ ] Identify any first-party or sportsbook-provider API exposed to anonymous visitors.
- [ ] Investigate relevant on-chain data only if it contains actual sportsbook odds.
- [ ] Inspect public static configuration and public network calls without logging in.
- [ ] Check supported aggregators for TG.Casino-specific odds.
- [ ] Document evidence for the selected source or why Playwright is unavoidable.

### Thunderpick

- [ ] Search official Thunderpick developer/API documentation for sports and esports data.
- [ ] Check for public REST, GraphQL, WebSocket, or feed endpoints used by the public site.
- [ ] Identify any first-party or sportsbook-provider API exposed to anonymous visitors.
- [ ] Investigate relevant on-chain data only if it contains actual sportsbook odds.
- [ ] Inspect public static configuration and public network calls without logging in.
- [ ] Check supported aggregators for Thunderpick-specific odds.
- [ ] Document evidence for the selected source or why Playwright is unavoidable.

### Aggregator evaluation

- [ ] Revalidate The Odds API integration and its supported bookmaker list.
- [ ] Check other reputable, documented odds providers only when they legally expose the target bookmaker's prices.
- [ ] Compare cost, rate limits, update latency, bookmaker identity, market coverage, and redistribution restrictions.
- [ ] Reject aggregators that provide generic consensus odds rather than the named platform's actual prices.

### Phase 1 deliverable and decision gate

- [ ] Add a source-decision table containing one row per platform.
- [ ] Include evidence links and the date each source was verified.
- [ ] Record one selected primary source and one optional fallback per platform.
- [ ] Confirm that every non-Playwright option was evaluated before approving Playwright.
- [ ] Do not begin a Playwright implementation for a platform until its research checklist is complete.

## Phase 2: Source adapter design

- [ ] Define a small source-adapter contract shared by REST, GraphQL, WebSocket, on-chain, aggregator, and Playwright implementations.
- [ ] Keep transport-specific response parsing inside the platform scraper.
- [ ] Require each adapter to produce `ScrapedEvent` objects with:
  - stable event and selection identifiers;
  - platform and sport;
  - home and away participants;
  - league or competition;
  - UTC start time;
  - pre-match/live state;
  - market type;
  - named outcomes and decimal odds;
  - direct platform URL where available.
- [ ] Add explicit validation for dictionaries, lists, nested envelopes, nulls, strings, suspended markets, and malformed prices.
- [ ] Remove the assumption that all websites share one generic JSON shape.
- [ ] Retain a generic parser only as a safe helper; never allow it to throw on an unknown response.

## Phase 3: Implement API and on-chain sources first

For each platform whose selected source is an API, feed, aggregator, or on-chain endpoint:

- [ ] Save sanitized response fixtures.
- [ ] Write the parser against fixtures before making live requests.
- [ ] Implement pagination, subscriptions, or cursor handling where required.
- [ ] Add timeouts, bounded retries, rate-limit handling, and useful error messages.
- [ ] Filter live, closed, suspended, and non-moneyline markets.
- [ ] Map source-specific sports and market names into scanner enums.
- [ ] Preserve source timestamps so stale odds can be rejected.
- [ ] Add a live smoke test that is disabled by default in the unit-test suite.
- [ ] Verify at least two real events manually against the public website.

Recommended implementation order:

- [ ] Cloudbet, after its official API is revalidated.
- [ ] Any platform with a confirmed public first-party endpoint.
- [ ] Any platform supported by a trustworthy bookmaker-specific aggregator.
- [ ] Remaining platforms with no viable non-browser source.

## Phase 4: Playwright fallback — last resort only

For each platform formally approved for Playwright:

- [ ] Document why official API, public first-party API, on-chain data, and aggregators were rejected.
- [ ] Use public/no-login pages only.
- [ ] Prefer response interception over DOM scraping.
- [ ] Capture only relevant JSON, GraphQL, or WebSocket payloads.
- [ ] Write a dedicated parser for the platform's actual captured response shape.
- [ ] Reuse one Chromium process and run platforms sequentially or under a strict semaphore.
- [ ] Block images, video, fonts, advertising, analytics, and other unnecessary resources.
- [ ] Use `domcontentloaded` plus a bounded capture window instead of waiting indefinitely for `networkidle`.
- [ ] Close pages and contexts deterministically after every platform.
- [ ] Enforce per-platform memory and execution time limits.
- [ ] Detect geo-block, consent, challenge, and maintenance pages and report them honestly.
- [ ] Never treat an empty capture as successful platform health.

## Phase 5: Platform health and observability

- [ ] Replace the current binary `ok`/`failed` model with:
  - `ok`: valid current events were returned;
  - `empty`: source responded correctly but no eligible events exist;
  - `blocked`: geo, challenge, or access control prevented collection;
  - `unavailable`: selected source is down or no supported public source exists;
  - `degraded`: partial data, stale data, or some sports failed;
  - `failed`: parser or application error.
- [ ] Include source type (`onchain`, `api`, `graphql`, `websocket`, `aggregator`, or `playwright`).
- [ ] Include event count, response/capture count, duration, last success, last error, and data timestamp.
- [ ] Make zero-event platforms visible as `empty`, `blocked`, `unavailable`, or `degraded`, not green `ok` by default.
- [ ] Add concise structured logs without storing complete sensitive payloads.

## Phase 6: Tests and data-quality gates

- [ ] Add fixture-based parser tests for every selected platform source.
- [ ] Add regression coverage for the Thunderpick string/dictionary crash.
- [ ] Test empty, malformed, suspended, live, two-way, and three-way markets.
- [ ] Test decimal, American, fractional, and implied-probability conversions where encountered.
- [ ] Validate that every emitted event has unique outcome names and odds greater than 1.0.
- [ ] Validate start times and reject stale or already-started pre-match events.
- [ ] Test status transitions for success, empty, blocked, unavailable, degraded, and failed.
- [ ] Add recorded cross-platform fixtures for the same fixture to test matching and arbitrage calculation.
- [ ] Keep all unit tests deterministic and independent of live websites.

## Phase 7: Local staged rollout

- [ ] Run one platform at a time locally and record event counts and failure modes.
- [ ] Compare sampled odds against the public website.
- [ ] Run two sources together and verify event matching.
- [ ] Enable all API/on-chain sources together and measure a complete scan.
- [ ] Add Playwright fallbacks one at a time while measuring peak memory.
- [ ] Confirm a failed platform cannot abort persistence for successful platforms.
- [ ] Confirm Supabase stores scan runs, platform health, events, and opportunities correctly.

## Phase 8: Railway production rollout

- [ ] Deploy API/on-chain integrations first.
- [ ] Confirm Docker includes Chromium only if at least one approved Playwright fallback remains.
- [ ] Configure source-specific public API keys as Railway secrets when required.
- [ ] Keep browser concurrency at one unless production metrics prove higher concurrency is safe.
- [ ] Measure memory, CPU, scan duration, and restart behavior.
- [ ] Verify `/api/health`, `/api/platforms`, `/api/scans/latest`, and `/api/opportunities/latest` after every deployment.
- [ ] Confirm the background scan interval does not overlap long-running scans.
- [ ] Roll back an individual platform with its feature flag if it destabilizes production.

## Phase 9: Vercel dashboard updates

- [ ] Display the expanded platform-health states and source type.
- [ ] Show last successful collection time and useful zero-event explanations.
- [ ] Distinguish "no eligible events" from "collector could not access the source."
- [ ] Show stale-data warnings.
- [ ] Keep scanner-wide health separate from individual platform health.

## Phase 10: Acceptance criteria

- [ ] Every supported platform has a completed and dated source investigation.
- [ ] Every Playwright fallback has written evidence that no acceptable API/on-chain/aggregator option exists.
- [ ] Every enabled platform has fixture-based parser tests.
- [ ] The production dashboard never displays `ok` for a platform that failed to return or validate data.
- [ ] At least two independent platforms return overlapping, current pre-match events before arbitrage results are considered meaningful.
- [ ] Supabase, Railway, and Vercel pass end-to-end production checks.
- [ ] Repository documentation explains source choices, limitations, and how to revalidate them.

## Platform progress table

| Platform | Research | Selected source | Parser | Tests | Local validation | Production validation |
|---|---|---|---|---|---|---|
| Polymarket | Complete | Gamma keyset + CLOB | Native | Fixture + live smoke | 82 events; degraded pagination | Pending rollout |
| Cloudbet | Complete | Official keyed Feed API | Native | Official fixture | Key required | Pending key |
| Stake | Complete | No acceptable source | Unavailable state | Health-state coverage | Unavailable by policy | Pending rollout |
| BC.Game | Complete | Public provider REST feed | Native | Fixture + live smoke | 392 events | Pending rollout |
| Shuffle | Complete | Public first-party GraphQL | Native | Fixture + live smoke | 70 events | Pending rollout |
| TG.Casino | Complete | Public provider REST feed | Native | Shared fixture + live smoke | 484 events | Pending rollout |
| Thunderpick | Complete | Public same-origin REST | Native | Fixture + regression | 227 events | Pending rollout |

## Session handoff — 2026-06-21

### Repository state

- Workspace: `C:\Users\Pimentel\Desktop\crypto\arbscanner`
- Branch: `main`, tracking `origin/main`.
- Writable origin: `https://github.com/0xredjava/arbscanner.git`.
- Read-only upstream: `https://github.com/CryptoDungeonMaster/arbscanner.git`.
- Latest pushed commit at handoff: `f9cdbb8` (`Ignore local Vercel metadata`).
- This implementation-plan file is currently untracked and intentionally not committed yet.
- Preserve any user changes already present in the worktree.

### Live environments

#### Supabase

- Existing project name: `0xredjava's Project`.
- Project reference: `kbnhhncgupyehjihjqnt`.
- Region: East US (Ohio).
- Dashboard: `https://supabase.com/dashboard/project/kbnhhncgupyehjihjqnt`.
- Migration `20260621000000_initial_schema.sql` is applied.
- Tables created: `scan_runs`, `platform_status`, `events`, and `opportunities`.
- REST access to `scan_runs` was verified successfully with the server credential.
- Supabase CLI was authenticated and the repository was linked during the previous session. Reauthenticate if the saved session expires.

#### Railway

- Project ID: `813d0cba-5880-4f64-9ffe-c1fd9f835b1a`.
- Service ID/name: `0be75172-bb72-4c63-9ae3-1620f8047126` / `api`.
- Public API: `https://api-production-c9c2.up.railway.app`.
- Health endpoint: `https://api-production-c9c2.up.railway.app/api/health`.
- Railway builds the root `Dockerfile`; `RAILWAY_DOCKERFILE_PATH=/Dockerfile` is configured.
- GitHub source is connected to `0xredjava/arbscanner`, branch `main`, and auto-deploy was verified.
- The latest verified deployment was healthy, used the Dockerfile builder, and returned HTTP 200 from `/api/health`.
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, and a generated `ADMIN_TOKEN` are stored only as Railway variables. Do not print or commit them.
- CORS is restricted to the current Vercel production aliases.

#### Vercel

- Team: `0xredjavas-projects` (`team_SBfahD0L137Q90hz7nKBmxXC`).
- Project: `arbscanner`.
- Production URL: `https://arbscanner-alpha.vercel.app`.
- The production page returned HTTP 200 and rendered the dashboard.
- The frontend points to the Railway API through `frontend/.env.production`; the value is public and contains no secret.
- Next.js was upgraded from vulnerable `14.2.0` to patched `14.2.35`.
- Vercel CLI deployment works and the local `frontend/` directory is linked to the project.
- Vercel Git auto-deploy is not connected: the Vercel GitHub App did not have permission to attach `0xredjava/arbscanner`. Production is currently deployable through the authenticated Vercel CLI.

### Verified scanner state

- Backend test suite: 5 tests passed at the end of deployment work.
- Frontend production build: passed with Next.js 14.2.35.
- End-to-end checks passed for Vercel page, Railway API, Supabase database health, and CORS.
- Polymarket is the only source currently returning usable events; observed production scans returned approximately 575–610 events.
- Cloudbet returned zero events and its configured public endpoint is probably stale or changed.
- Stake, BC.Game, Shuffle, and TG.Casino returned zero events from placeholder Playwright integrations.
- Thunderpick captured data but its generic parser crashed on a string with `'str' object has no attribute 'get'`.
- Several Playwright pages crashed when browser-backed scrapers ran concurrently on Railway's trial resources.
- Current green `ok` status can mean "returned without raising" even when event count is zero. This health behavior must be corrected.

### Important implementation findings

- The non-Polymarket implementations are placeholders built around one generic JSON parser; they are not complete platform integrations.
- The old repository README described the intended architecture: API sources for Polymarket/Cloudbet and Playwright interception for the other bookmakers. That document was an architectural overview, not a completed implementation plan.
- Do not assume Playwright is necessary just because the placeholder chose it.
- The user explicitly requires a fresh API/on-chain/source investigation for every platform before any Playwright implementation work.
- API, on-chain, first-party feed, and bookmaker-specific aggregator sources are preferred in that order. Playwright is the absolute final fallback.

### Exact starting point for the next session

1. Read this entire implementation plan before editing scraper code.
2. Begin with Phase 1 only.
3. Research all seven platforms, including revalidation of Polymarket and Cloudbet and full discovery for Stake, BC.Game, Shuffle, TG.Casino, and Thunderpick.
4. Create a dated source-decision report with evidence links, authentication requirements, rate limits, market coverage, response type, and the selected primary/fallback source for every platform.
5. Check official on-chain sources, documented APIs, first-party REST/GraphQL/WebSocket feeds, sportsbook providers, and reputable bookmaker-specific aggregators.
6. Do not implement or expand any Playwright scraper until every platform's Phase 1 research is complete and the decision gate is satisfied.
7. After the source report is complete, implement API/on-chain adapters first, one platform at a time, with sanitized fixtures and tests.
8. Before deployment, fix health-state semantics and ensure browser fallbacks run sequentially with strict resource limits.

### Suggested opening prompt for the next session

> Continue from `IMPLEMENTATION_PLAN.md`. Start with Phase 1 source discovery for every platform. Do not change scraper implementations yet. Produce the dated source-decision report and exhaust official API, on-chain, first-party feed, and bookmaker-specific aggregator options before approving Playwright for any platform.
