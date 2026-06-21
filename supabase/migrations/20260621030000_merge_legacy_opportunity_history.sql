begin;

-- The first lifecycle migration intentionally preserved every legacy row, but
-- used its database ID as the fingerprint. That made the same event appear once
-- per scan. Rebuild legacy history around a stable event/market identity.
delete from opportunity_observations where fingerprint like 'legacy-%';
delete from opportunity_lifecycles where fingerprint like 'legacy-%';

update opportunities
set fingerprint = 'legacy-' || md5(
  lower(trim(event_name)) || '|' || sport || '|' || market_type
)
where fingerprint like 'legacy-%';

insert into opportunity_lifecycles (
  fingerprint, event_name, sport, country, competition, market_type, start_time,
  first_found_at, last_seen_at, last_verified_at, ended_at, end_reason,
  observation_count, latest_profit_pct, latest_total_stake, latest_payout,
  latest_state, latest_legs, updated_at
)
select
  fingerprint,
  (array_agg(event_name order by detected_at desc))[1],
  (array_agg(sport order by detected_at desc))[1],
  (array_agg(country order by detected_at desc))[1],
  (array_agg(competition order by detected_at desc))[1],
  (array_agg(market_type order by detected_at desc))[1],
  max(start_time),
  min(detected_at),
  max(detected_at),
  max(last_verified_at),
  max(detected_at),
  'legacy_import',
  count(*)::integer,
  (array_agg(profit_pct order by detected_at desc))[1],
  (array_agg(total_stake order by detected_at desc))[1],
  (array_agg(guaranteed_return order by detected_at desc))[1],
  'legacy',
  (array_agg(legs order by detected_at desc))[1],
  now()
from opportunities
where fingerprint like 'legacy-%'
group by fingerprint;

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

commit;
