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

create index if not exists idx_opportunities_fingerprint
  on opportunities(fingerprint, detected_at desc);

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

-- Legacy rows did not retain enough quote data to merge into a true lifecycle.
-- Preserve each one as an explicitly legacy, single-observation lifecycle and
-- use detected_at only as the documented approximate first-found time.
update opportunities
set fingerprint = 'legacy-' || id::text,
    freshness_status = 'legacy',
    execution_safe = false
where fingerprint is null;

insert into opportunity_lifecycles (
  fingerprint, event_name, sport, country, competition, market_type, start_time,
  first_found_at, last_seen_at, last_verified_at, ended_at, end_reason,
  observation_count, latest_profit_pct, latest_total_stake, latest_payout,
  latest_state, latest_legs
)
select
  fingerprint, event_name, sport, country, competition, market_type, start_time,
  detected_at, detected_at, last_verified_at, detected_at, 'legacy_import',
  1, profit_pct, total_stake, guaranteed_return, 'legacy', legs
from opportunities
where fingerprint like 'legacy-%'
on conflict (fingerprint) do nothing;

insert into opportunity_observations (
  scan_id, fingerprint, observed_at, last_verified_at, quote_expires_at, state,
  profit_pct, total_stake, lowest_payout, legs, calculation
)
select
  scan_id, fingerprint, detected_at, last_verified_at, quote_expires_at, 'legacy',
  profit_pct, total_stake, guaranteed_return, legs,
  jsonb_build_object(
    'legacy', true,
    'event_name', event_name,
    'detected_at_is_approximate_first_found', true,
    'warnings', warnings
  )
from opportunities
where fingerprint like 'legacy-%'
on conflict (scan_id, fingerprint) do nothing;

alter table opportunities alter column fingerprint set not null;

create index if not exists idx_opportunity_lifecycles_last_seen
  on opportunity_lifecycles(last_seen_at desc);
create index if not exists idx_opportunity_observations_fingerprint_time
  on opportunity_observations(fingerprint, observed_at asc);

comment on table opportunity_observations is
  'Append-only opportunity audit history. Retained indefinitely unless an explicit operational retention policy is adopted.';
