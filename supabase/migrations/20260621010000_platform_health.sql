alter table platform_status
  add column if not exists source_type text not null default 'unknown',
  add column if not exists response_count integer not null default 0,
  add column if not exists data_timestamp timestamptz;
