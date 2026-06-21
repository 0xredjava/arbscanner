# Sportsbook Source Decisions

Verified: **2026-06-21** from Brazil (`America/Sao_Paulo`).

This report is the Phase 1 decision gate from `IMPLEMENTATION_PLAN.md`. Only public,
unauthenticated pre-match data is eligible. A source returning HTTP 200 in the
observations below was tested without an account session, private cookies, a private
key, CAPTCHA handling, or a proxy bypass.

## Decision table

| Platform | Primary source | Optional fallback | Auth | Response and coverage | Rate limits | Decision |
|---|---|---|---|---|---|---|
| Polymarket | Official Gamma API `/events/keyset` for discovery plus public CLOB `/prices` or `/books` for executable prices | Polygon contracts for market/settlement verification; CLOB market WebSocket for later freshness work | None for Gamma and CLOB read endpoints | JSON; sports metadata, events, token IDs, books, bids/asks, timestamps, liquidity | Published: Gamma `/events` 500 requests/10s; CLOB `/prices` 500 requests/10s | **Enable API/on-chain adapter.** Migrate discovery from deprecated `/events` to keyset pagination and read the nested CLOB price response correctly. |
| Cloudbet | Official Cloudbet Feed API at `https://sports-api.cloudbet.com/pub/v2` | None that preserves Cloudbet bookmaker identity | `X-API-Key`; long-lived trading or affiliate key | JSON or protobuf; sports, competitions, fixtures, events, markets, and latest lines. Affiliate data may be cached by up to one minute. | Not published in the OpenAPI document | **Implement keyed API adapter, disabled/unavailable until a key is configured.** The old unkeyed request now returns 401. |
| Stake | None acceptable | None | Official API requires a logged-in Stake session token and approved-affiliate access | The documented API covers affiliate utilities and casino history, not sportsbook odds. The public sportsbook returned a Cloudflare challenge (403) in both HTTP and no-login browser checks. | Not applicable | **Unavailable. Do not approve Playwright.** A browser still reaches the access challenge, and using the documented session token violates project constraints. |
| BC.Game | Anonymous sportsbook-provider REST snapshot exposed by the public BC.Game sportsbook (`sptpub.com`, brand `2103509236163162112`) | Provider WebSocket `.../api/v1/ws_new` | None observed | JSON; pre-match/live deltas, sports, competitions, events, and markets. Anonymous `/api/v4/prematch/...` returned 200. | Not published; use conservative polling and bounded retries | **Enable first-party-exposed provider API adapter.** No Playwright is needed. |
| Shuffle | Same-origin public sports GraphQL at `/main-api/graphql/sports/graphql-sports` | Public sports GraphQL subscription at `/main-api/bp-subscription/sports-subscription/graphql` | None observed for public queries | GraphQL JSON; public navigation, fixture, tournament, event, market, and price data. Endpoint and sports page data returned 200 without login. | Not published; use conservative polling and bounded retries | **Enable first-party GraphQL adapter.** No Playwright is needed. |
| TG.Casino | Anonymous sportsbook-provider REST snapshot exposed by the public TG.Casino sportsbook (`sptpub.com`, brand `2352178356470026240`) | Provider WebSocket `.../api/v1/ws_new` | None observed | JSON; pre-match/live deltas, sports, competitions, events, and markets. Anonymous `/api/v4/prematch/...` returned 200. | Not published; use conservative polling and bounded retries | **Enable first-party-exposed provider API adapter.** No Playwright is needed. |
| Thunderpick | Same-origin public REST (`/api/v2/competitions`, `/api/matches`) | Same-origin WebSockets (`/socket.io`, `/ws/websockets`) | None observed for public market reads | JSON; competitions, pre-match matches, event groups, selections, decimal odds, and timestamps. All selected REST routes returned 200. | Not published; use conservative polling and bounded retries | **Enable first-party REST adapter.** No Playwright is needed. |

## Evidence by platform

### Polymarket

- [Official API overview](https://docs.polymarket.com/api-reference/introduction) separates Gamma discovery, CLOB order books/prices, and on-chain settlement.
- [Authentication](https://docs.polymarket.com/api-reference/authentication) says Gamma, Data API, and CLOB read endpoints do not require authentication.
- [Sports metadata](https://docs.polymarket.com/api-reference/sports/get-sports-metadata-information) and live `GET https://gamma-api.polymarket.com/sports` returned structured sport/series/tag metadata.
- A live request to the legacy [events route](https://gamma-api.polymarket.com/events?active=true&closed=false&limit=1) returned 200 with `Deprecation: true`, a 2026-05-01 sunset, and `Warning: 299 - "use /events/keyset"`.
- [Keyset event pagination](https://docs.polymarket.com/api-reference/events/list-events-keyset-pagination) supports up to 500 events and an opaque `next_cursor`.
- [Batch market prices](https://docs.polymarket.com/api-reference/market-data/get-market-prices-request-body) and [batch books](https://docs.polymarket.com/api-reference/market-data/get-order-books-request-body) are public CLOB reads.
- [Contract addresses](https://docs.polymarket.com/resources/contracts) identify the Polygon chain, CTF exchanges, Conditional Tokens contract, and resolution contracts. Contracts are authoritative for creation/trading/settlement, but do not replace Gamma's participant metadata or the CLOB's current executable book.
- [Published rate limits](https://docs.polymarket.com/api-reference/rate-limits) are far above the scanner's intended polling volume.

Selected composition: Gamma keyset discovery + CLOB best executable price, with
on-chain identifiers retained for verification. The public market WebSocket is a
future freshness optimization, not required for the initial reliable adapter.

### Cloudbet

- [Official Cloudbet API portal](https://www.cloudbet.com/api/) served a current OpenAPI UI, last modified 2026-06-16.
- [Official Feed OpenAPI](https://www.cloudbet.com/api/swagger.yaml) declares server `https://sports-api.cloudbet.com/pub`, global `X-API-Key` authentication, and `/v2/odds/sports`, `/events`, `/fixtures`, `/competitions/{key}`, and `/lines` operations.
- The schema says affiliate keys are intended for consuming odds, may be up to one minute behind, and expire; trading keys provide real-time updates. Both require an account flow. No public shared/read-only key is documented.
- The configured anonymous `GET /pub/v2/odds/soccer` returned **401**, confirming that the code's current zero-event behavior is authentication failure rather than an empty slate.
- The official [Cloudbet documentation repository](https://github.com/Cloudbet/docs) provides response examples and market/event status definitions suitable for deterministic fixtures.

The adapter must require a new `CLOUDBET_API_KEY` setting, use the documented
event/competition response shape, and return `unavailable` when the key is absent or
rejected. No generic aggregator currently preserves Cloudbet-specific odds.

### Stake

- [Official public API documentation](https://docs.stake.com/) is current, but its OpenAPI describes an authenticated affiliate API. Authentication explicitly uses a logged-in user's `session` cookie as `x-access-token`.
- Its documented operations cover bet preview, affiliate challenges, gifts/tips, and casino crash/slide history. It contains no sportsbook fixture, market, or odds read operation.
- The no-login [sportsbook](https://stake.com/sports/home) returned a managed Cloudflare challenge and HTTP 403 from both a direct request and a headless public-page check.
- No official on-chain contract containing Stake sportsbook markets or executable odds was identified. Crypto deposits/settlement are not an on-chain sportsbook order book.
- The aggregator checks below found no named Stake bookmaker feed.

Because sessions, private cookies, CAPTCHA/challenge bypasses, and proxy bypasses are
out of scope, the honest source state is `unavailable`. Empty data must never be
reported as healthy.

### BC.Game

- The public [BC.Game sportsbook](https://bc.game/sports) returned 200 without login and loaded its sportsbook provider anonymously.
- It requested `GET https://bc.game/api/platform-sports/v14/home/sport/provider/support/` and provider configuration without a user session.
- It then received 200 JSON from `https://api-k-c7818b61-623.sptpub.com/api/v4/prematch/brand/2103509236163162112/pt-BR/0`, followed by cursor/delta requests on the same route.
- It opened `wss://api-k-c7818b61-623.sptpub.com/api/v1/ws_new?brand_id=2103509236163162112&lang=pt-BR` for updates.
- Provider responses also expose descriptions, top events, side navigation, and brand settings. The first implementation should consume only the minimum pre-match snapshot and ignore live deltas.
- No official BC.Game developer documentation for sportsbook odds and no on-chain odds market were identified. The browser-discovered provider feed is preferable to DOM scraping because it is the structured source the public first-party page uses.

### Shuffle

- The public [Shuffle sportsbook](https://shuffle.com/sports) and public Next.js sports data returned 200 without login.
- The page called same-origin `POST https://shuffle.com/main-api/graphql/sports/graphql-sports` and opened `wss://shuffle.com/main-api/bp-subscription/sports-subscription/graphql`.
- It also called `GET https://shuffle.com/api/v1/sports/get-nav-items?locale=en` and exposed public fixture/tournament pages with stable source identifiers.
- No separate documented sports developer API or on-chain executable odds source was identified. The named, same-origin GraphQL operation used by the public page is the selected source.

### TG.Casino

- The public [TG.Casino sportsbook](https://www.tg.casino/sports) returned 200 without login after the canonical redirect.
- It received 200 JSON from `https://api-a-c7818b61-600.sptpub.com/api/v4/prematch/brand/2352178356470026240/en/0`, followed by cursor/delta requests.
- It opened `wss://api-a-c7818b61-600.sptpub.com/api/v1/ws_new?brand_id=2352178356470026240&lang=en`.
- This is the same structured sportsbook-provider protocol used by BC.Game with a different host, brand ID, theme, and locale. Adapters may share a transport/parser helper but must retain platform-specific configuration and fixtures.
- No official TG.Casino developer API or on-chain executable sportsbook market was identified.

### Thunderpick

- The public [Thunderpick sportsbook](https://thunderpick.io/sports) returned 200 without login.
- Same-origin `GET https://thunderpick.io/api/v2/competitions` and `GET https://thunderpick.io/api/matches` returned 200 JSON without authentication.
- The page also used targeted `/api/matches?matchesIds=...` reads and public live-count endpoints.
- It opened both `wss://thunderpick.io/socket.io/` and `wss://thunderpick.io/ws/websockets` for updates.
- No documented public developer feed or on-chain executable sportsbook market was identified. The stable same-origin REST route is preferred over browser interception and fixes the generic-parser string crash at its source.

## Aggregator evaluation

- [The Odds API bookmaker list](https://the-odds-api.com/sports-odds-data/bookmaker-apis.html) currently lists Polymarket (`us_ex`, key `polymarket`) but none of Cloudbet, Stake, BC.Game, Shuffle, TG.Casino, or Thunderpick. Its Polymarket coverage is a possible outage fallback, but direct official data has better identity and no third-party quota cost.
- [The Odds API v4 guide](https://the-odds-api.com/liveapi/guides/v4/) requires an API key and documents quota response headers. It must not be emitted as a synthetic `the_odds_api` platform when the goal is named-bookmaker arbitrage.
- [SportsGameOdds documentation](https://sportsgameodds.com/docs) contained no exact supported-bookmaker match for any target platform during this verification.
- Consensus feeds and white-label odds that cannot prove the named platform's actual offered price are rejected.

## Playwright decision gate

No platform is approved for a production Playwright collector:

- Polymarket, BC.Game, Shuffle, TG.Casino, and Thunderpick have structured public non-browser sources.
- Cloudbet has an official documented keyed API.
- Stake remains access-controlled in the deployment region; Playwright reaches the same challenge and using a session or bypass is forbidden.

Browser use in this investigation was limited to observing public, no-login network
requests. It is not a selected production transport.

## Revalidation notes

- Revalidate all undocumented first-party/provider endpoints before each production rollout and whenever a fixture parser fails.
- Treat 401/403/challenge pages as `blocked` or `unavailable`, never `empty` or `ok`.
- Poll undocumented feeds no faster than the scanner interval, honor 429/`Retry-After`, use bounded exponential backoff, and add a per-platform feature flag.
- Do not store response headers containing cookies, authorization values, device identifiers, or analytics payloads in fixtures or logs.
