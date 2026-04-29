-- Wave 7B/8C - Read-only policies for dashboard anon role
-- Apply in Supabase SQL Editor.

alter table if exists public.inverter_samples enable row level security;
alter table if exists public.controller_decisions enable row level security;
alter table if exists public.tesla_samples enable row level security;
alter table if exists public.afore_candidate_samples enable row level security;

grant select on table public.inverter_samples to anon, authenticated;
grant select on table public.controller_decisions to anon, authenticated;
grant select on table public.tesla_samples to anon, authenticated;
grant select on table public.afore_candidate_samples to anon, authenticated;

drop policy if exists "anon_read_inverter_samples" on public.inverter_samples;
drop policy if exists "anon_read_controller_decisions" on public.controller_decisions;
drop policy if exists "anon_read_tesla_samples" on public.tesla_samples;
drop policy if exists "anon_read_afore_candidate_samples" on public.afore_candidate_samples;

create policy "anon_read_inverter_samples"
on public.inverter_samples
for select
to anon
using (true);

create policy "anon_read_controller_decisions"
on public.controller_decisions
for select
to anon
using (true);

create policy "anon_read_tesla_samples"
on public.tesla_samples
for select
to anon
using (true);

create policy "anon_read_afore_candidate_samples"
on public.afore_candidate_samples
for select
to anon
using (true);

-- Optional: allow authenticated reads too.
drop policy if exists "auth_read_inverter_samples" on public.inverter_samples;
drop policy if exists "auth_read_controller_decisions" on public.controller_decisions;
drop policy if exists "auth_read_tesla_samples" on public.tesla_samples;
drop policy if exists "auth_read_afore_candidate_samples" on public.afore_candidate_samples;

create policy "auth_read_inverter_samples"
on public.inverter_samples
for select
to authenticated
using (true);

create policy "auth_read_controller_decisions"
on public.controller_decisions
for select
to authenticated
using (true);

create policy "auth_read_tesla_samples"
on public.tesla_samples
for select
to authenticated
using (true);

create policy "auth_read_afore_candidate_samples"
on public.afore_candidate_samples
for select
to authenticated
using (true);
