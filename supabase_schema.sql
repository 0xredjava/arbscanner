create extension if not exists pgcrypto;

create table if not exists scan_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null,
  finished_at timestamptz,
  duration_ms integer not null default 0,
  status text not null check (status in ('success', 'failed')),
  trigger text not null check (trigger in ('background', 'manual')),
  error text,
  platform_count integer not null default 0,
  event_count integer not null default 0,
  normalized_event_count integer not null default 0,
  opportunity_count integer not null default 0
);

create table if not exists platform_status (
  platform text primary key,
  scan_id uuid references scan_runs(id) on delete set null,
  enabled boolean not null default true,
  status text not null,
  fetch_method text not null,
  source_type text not null default 'unknown',
  event_count integer not null default 0,
  response_count integer not null default 0,
  duration_ms integer not null default 0,
  last_success_at timestamptz,
  data_timestamp timestamptz,
  last_error text,
  updated_at timestamptz not null default now()
);

create table if not exists events (
  id bigint generated always as identity primary key,
  scan_id uuid not null references scan_runs(id) on delete cascade,
  platform text not null,
  sport text not null,
  event_key text not null,
  event_id text not null,
  home_team text not null,
  away_team text not null,
  league text not null,
  start_time timestamptz,
  market_type text not null,
  outcome_name text not null,
  decimal_odds numeric not null,
  implied_prob numeric not null,
  fee_adjusted_prob numeric not null,
  liquidity_usd numeric,
  url text,
  created_at timestamptz not null default now()
);

create table if not exists opportunities (
  id bigint generated always as identity primary key,
  scan_id uuid not null references scan_runs(id) on delete cascade,
  match_id text not null,
  sport text not null,
  event_name text not null,
  league text not null,
  market_type text not null,
  profit_pct numeric not null,
  total_stake numeric not null,
  guaranteed_return numeric not null,
  guaranteed_profit numeric not null,
  total_implied_prob numeric not null,
  legs jsonb not null,
  warnings jsonb not null default '[]'::jsonb,
  detected_at timestamptz not null,
  created_at timestamptz not null default now()
);

create index if not exists idx_scan_runs_started_at on scan_runs(started_at desc);
create index if not exists idx_events_scan_id on events(scan_id);
create index if not exists idx_events_event_key on events(event_key);
create index if not exists idx_opportunities_scan_profit on opportunities(scan_id, profit_pct desc);

-- Apply supabase/migrations/20260621020000_execution_safe_opportunities.sql
-- to existing installations. The definitions below keep fresh installs aligned.
alter table events
  add column if not exists country text not null default 'International / unknown',
  add column if not exists competition text not null default '',
  add column if not exists quote_fetched_at timestamptz,
  add column if not exists source_timestamp timestamptz;

alter table opportunities
  add column if not exists fingerprint text,
  add column if not exists country text not null default 'International / unknown',
  add column if not exists competition text not null default '',
  add column if not exists start_time timestamptz,
  add column if not exists last_verified_at timestamptz,
  add column if not exists quote_expires_at timestamptz,
  add column if not exists freshness_status text not null default 'unknown',
  add column if not exists execution_safe boolean not null default false,
  add column if not exists requested_bankroll numeric;

create table if not exists opportunity_lifecycles (
  fingerprint text primary key,
  event_name text not null,
  sport text not null,
  country text not null default 'International / unknown',
  competition text not null default '',
  market_type text not null,
  start_time timestamptz,
  first_found_at timestamptz not null,
  last_seen_at timestamptz not null,
  last_verified_at timestamptz,
  ended_at timestamptz,
  end_reason text,
  observation_count integer not null default 1,
  latest_profit_pct numeric not null,
  latest_total_stake numeric not null,
  latest_payout numeric not null,
  latest_state text not null,
  latest_legs jsonb not null default '[]'::jsonb,
  updated_at timestamptz not null default now()
);

create table if not exists opportunity_observations (
  id bigint generated always as identity primary key,
  scan_id uuid not null references scan_runs(id) on delete cascade,
  fingerprint text not null references opportunity_lifecycles(fingerprint) on delete cascade,
  observed_at timestamptz not null,
  last_verified_at timestamptz,
  quote_expires_at timestamptz,
  state text not null,
  profit_pct numeric not null,
  total_stake numeric not null,
  lowest_payout numeric not null,
  legs jsonb not null,
  calculation jsonb not null,
  created_at timestamptz not null default now(),
  unique(scan_id, fingerprint)
);

create index if not exists idx_opportunities_fingerprint on opportunities(fingerprint, detected_at desc);
create index if not exists idx_opportunity_lifecycles_last_seen on opportunity_lifecycles(last_seen_at desc);
create index if not exists idx_opportunity_observations_fingerprint_time on opportunity_observations(fingerprint, observed_at asc);
