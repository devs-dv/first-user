-- First User job queue. Run once in the Supabase SQL editor; safe to re-run.
-- Only the worker (service role) reads or writes these tables: RLS is on with no
-- policies, and anon/authenticated get no grants.

-- Runs: one queued visit of a founder's app.
create table if not exists public.runs (
  id            uuid primary key default gen_random_uuid(),
  url           text not null,
  goal          text not null,
  status        text not null default 'queued'
                check (status in ('queued', 'running', 'done', 'failed')),
  source        text not null default 'live',
  agent_version text,
  brain_model   text,
  outcome       text,
  reason        text,
  result        jsonb,
  error         text,
  cost_usd      numeric(10, 5),
  created_at    timestamptz not null default now(),
  started_at    timestamptz,
  finished_at   timestamptz
);

-- claim_run() takes the oldest queued run; the stale-run sweep looks for old running runs.
create index if not exists runs_queued_created_at_idx on public.runs (created_at) where status = 'queued';
create index if not exists runs_running_started_at_idx on public.runs (started_at) where status = 'running';

-- Steps: one tool call by the agent, written as it happens.
create table if not exists public.steps (
  id              bigint generated always as identity primary key,
  run_id          uuid not null references public.runs (id) on delete cascade,
  idx             integer not null,
  tool            text not null,
  thought         text,
  input           jsonb,
  result          jsonb,
  url             text,
  screenshot_path text,
  created_at      timestamptz not null default now(),
  unique (run_id, idx)
);

-- Frictions: a point where the visitor got stuck (site), or where the browser tool failed (agent_issue).
create table if not exists public.frictions (
  id         bigint generated always as identity primary key,
  run_id     uuid not null references public.runs (id) on delete cascade,
  step_idx   integer,
  kind       text not null check (kind in ('site', 'agent_issue')),
  severity   text check (severity in ('low', 'medium', 'high')),
  expected   text,
  happened   text,
  created_at timestamptz not null default now()
);

create index if not exists frictions_run_id_idx on public.frictions (run_id);

-- Service role only.
alter table public.runs enable row level security;
alter table public.steps enable row level security;
alter table public.frictions enable row level security;

revoke all on table public.runs, public.steps, public.frictions from anon, authenticated;
grant select, insert, update, delete on table public.runs, public.steps, public.frictions to service_role;

-- Atomically claim the oldest queued run. SKIP LOCKED lets several workers claim
-- different runs without waiting on each other. Returns no row when the queue is empty.
create or replace function public.claim_run()
returns setof public.runs
language sql
security invoker
set search_path = ''
as $$
  update public.runs
  set status = 'running', started_at = now()
  where id = (
    select id
    from public.runs
    where status = 'queued'
    order by created_at
    limit 1
    for update skip locked
  )
  returning *;
$$;

-- New functions are executable by PUBLIC by default; keep this one to the worker.
revoke execute on function public.claim_run() from public, anon, authenticated;
grant execute on function public.claim_run() to service_role;

-- Public bucket: anyone with a screenshot's URL can view it. Uploads use the service role.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('screenshots', 'screenshots', true, 5242880, array['image/png'])
on conflict (id) do nothing;
