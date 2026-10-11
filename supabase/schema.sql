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

-- ---------------------------------------------------------------------------
-- Web app (added for web/). Safe to re-run.
-- ---------------------------------------------------------------------------

-- Who queued a run, as a keyed hash of their IP address (never the IP itself),
-- for the per-visitor rate limit. Null for runs queued from the command line.
alter table public.runs add column if not exists ip_hash text;

create index if not exists runs_ip_hash_created_at_idx
  on public.runs (ip_hash, created_at) where ip_hash is not null;

-- Ways in (2026-10-11): runs can start at a "start link" past the login, and can carry a
-- throwaway test login. The login lives in run_secrets, not on the run, and only until the
-- worker claims the run: take_run_secrets() reads and deletes it in one statement.
alter table public.runs add column if not exists start_url text;
alter table public.runs add column if not exists has_test_login boolean not null default false;
alter table public.runs add column if not exists first_impression jsonb;
alter table public.runs add column if not exists entry jsonb;

create table if not exists public.run_secrets (
  run_id        uuid primary key references public.runs (id) on delete cascade,
  test_email    text not null,
  test_password text not null,
  created_at    timestamptz not null default now()
);

-- Service role only, like the other tables.
alter table public.run_secrets enable row level security;
revoke all on table public.run_secrets from anon, authenticated;
grant select, insert, delete on table public.run_secrets to service_role;

-- Read a run's test login and delete it, atomically. Returns no row when there is none.
create or replace function public.take_run_secrets(p_run_id uuid)
returns table (test_email text, test_password text)
language sql
security invoker
set search_path = ''
as $$
  delete from public.run_secrets
  where run_id = p_run_id
  returning run_secrets.test_email, run_secrets.test_password;
$$;

revoke execute on function public.take_run_secrets(uuid) from public, anon, authenticated;
grant execute on function public.take_run_secrets(uuid) to service_role;

-- Queue a run from the web app, enforcing both limits in one transaction.
-- The advisory lock serialises web enqueues, so two requests cannot both pass
-- a limit and then both insert. Returns {"id": ...} or {"error": ...}.
-- The old five-argument version is dropped so only one overload exists.
drop function if exists public.enqueue_web_run(text, text, text, integer, integer);

create or replace function public.enqueue_web_run(
  p_url text,
  p_goal text,
  p_ip_hash text,
  p_max_queued integer,
  p_max_per_hour integer,
  p_start_url text default null,
  p_test_email text default null,
  p_test_password text default null
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  queued_count integer;
  recent_count integer;
  oldest_recent timestamptz;
  new_id uuid;
  with_login boolean := p_test_email is not null and p_test_password is not null;
begin
  perform pg_advisory_xact_lock(hashtext('public.enqueue_web_run'));

  select count(*) into queued_count from public.runs where status = 'queued';
  if queued_count >= p_max_queued then
    return jsonb_build_object('error', 'queue_full');
  end if;

  select count(*), min(created_at) into recent_count, oldest_recent
  from public.runs
  where ip_hash = p_ip_hash and created_at > now() - interval '1 hour';
  if recent_count >= p_max_per_hour then
    return jsonb_build_object(
      'error', 'rate_limited',
      'retry_after_seconds', ceil(extract(epoch from (oldest_recent + interval '1 hour' - now())))::integer
    );
  end if;

  insert into public.runs (url, goal, source, ip_hash, start_url, has_test_login)
  values (p_url, p_goal, 'web', p_ip_hash, p_start_url, with_login)
  returning id into new_id;

  if with_login then
    insert into public.run_secrets (run_id, test_email, test_password)
    values (new_id, p_test_email, p_test_password);
  end if;
  return jsonb_build_object('id', new_id);
end;
$$;

revoke execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text)
  from public, anon, authenticated;
grant execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text)
  to service_role;

-- Evals: evals/run.py queues runs with source 'eval' and labels them with the eval version.
alter table public.runs add column if not exists eval_version text;
create index if not exists runs_eval_version_idx on public.runs (eval_version) where eval_version is not null;

-- neatlogs trace id of each run (the worker's first_visit span), for linking a run to its trace.
alter table public.runs add column if not exists trace_id text;
