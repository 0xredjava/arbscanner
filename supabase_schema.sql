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
  event_count integer not null default 0,
  duration_ms integer not null default 0,
  last_success_at timestamptz,
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
