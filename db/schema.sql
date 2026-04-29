-- Esyy Tesla Connector - Supabase schema (Wave 5A)
-- Idempotent script: safe to run multiple times.

create extension if not exists pgcrypto;

create table if not exists public.inverter_samples (
    id uuid primary key default gen_random_uuid(),
    sample_timestamp timestamptz not null,
    pv_power_w double precision,
    grid_power_raw_w double precision,
    grid_import_w double precision,
    grid_export_w double precision,
    grid_sign_mode text,
    grid_sign_assumed_mode text,
    grid_sign_unknown boolean,
    cycle integer,
    source text default 'controller_loop_dry_run',
    created_at timestamptz not null default now()
);

create index if not exists idx_inverter_samples_sample_timestamp
    on public.inverter_samples (sample_timestamp);

create table if not exists public.tesla_samples (
    id uuid primary key default gen_random_uuid(),
    sample_timestamp timestamptz not null,
    vehicle_id text,
    vehicle_state text,
    battery_level double precision,
    charging_state text,
    charge_amps double precision,
    charge_current_request double precision,
    charge_current_request_max double precision,
    charge_limit_soc double precision,
    odometer_km double precision,
    energy_added_kwh double precision,
    asleep_or_offline boolean,
    skipped_vehicle_data boolean,
    source text default 'tesla_readonly_status',
    created_at timestamptz not null default now()
);

alter table if exists public.tesla_samples
    add column if not exists vehicle_id text;
alter table if exists public.tesla_samples
    add column if not exists charge_current_request double precision;
alter table if exists public.tesla_samples
    add column if not exists charge_current_request_max double precision;
alter table if exists public.tesla_samples
    add column if not exists energy_added_kwh double precision;

create index if not exists idx_tesla_samples_sample_timestamp
    on public.tesla_samples (sample_timestamp);

create table if not exists public.controller_decisions (
    id uuid primary key default gen_random_uuid(),
    sample_timestamp timestamptz not null,
    cycle integer,
    export_w double precision,
    current_amps_before integer,
    target_amps integer,
    action text not null,
    current_amps_after integer,
    note text,
    created_at timestamptz not null default now()
);

create index if not exists idx_controller_decisions_sample_timestamp
    on public.controller_decisions (sample_timestamp);

create table if not exists public.controller_settings (
    id uuid primary key default gen_random_uuid(),
    sample_timestamp timestamptz not null,
    auto_mode boolean,
    dry_run boolean,
    min_amps integer,
    max_amps integer,
    start_threshold_w double precision,
    stop_threshold_w double precision,
    poll_interval_seconds integer,
    grid_sign_mode text,
    created_at timestamptz not null default now()
);

create index if not exists idx_controller_settings_sample_timestamp
    on public.controller_settings (sample_timestamp);

create table if not exists public.afore_candidate_samples (
    id uuid primary key default gen_random_uuid(),
    sample_timestamp timestamptz not null,
    register_name text not null,
    register_address text not null,
    register_order text not null,
    raw_high bigint,
    raw_low bigint,
    decoded_int32 bigint,
    scale double precision not null default 1,
    value_w double precision,
    unit text not null default 'W',
    source text not null default 'ha_candidate_sync',
    notes text,
    created_at timestamptz not null default now()
);

create index if not exists idx_afore_candidate_samples_sample_timestamp
    on public.afore_candidate_samples (sample_timestamp);

create index if not exists idx_afore_candidate_samples_register_name
    on public.afore_candidate_samples (register_name);
