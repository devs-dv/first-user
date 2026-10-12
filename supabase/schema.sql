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

-- ---------------------------------------------------------------------------
-- How the visitor gets in, and report findings (2026-10-11). Safe to re-run.
-- ---------------------------------------------------------------------------

-- The form's "How should the visitor get in?" choice: public (look at what is public, the default),
-- link (a demo or guest link in start_url), account (a test login in run_secrets) or signup (the
-- visitor makes up its own account). Null on runs from before this change and from the command line.
alter table public.runs add column if not exists access_mode text
  check (access_mode in ('public', 'link', 'account', 'signup'));

-- Up to five ranked findings written after the visit (worker/report_writer.py), each with evidence,
-- steps to reproduce and a fix prompt. Null until the report writer has run.
alter table public.runs add column if not exists findings jsonb;

-- enqueue_web_run now takes the access mode. Drop the 8-argument version so one overload exists.
drop function if exists public.enqueue_web_run(text, text, text, integer, integer, text, text, text);

create or replace function public.enqueue_web_run(
  p_url text,
  p_goal text,
  p_ip_hash text,
  p_max_queued integer,
  p_max_per_hour integer,
  p_start_url text default null,
  p_test_email text default null,
  p_test_password text default null,
  p_access_mode text default null
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

  insert into public.runs (url, goal, source, ip_hash, start_url, has_test_login, access_mode)
  values (p_url, p_goal, 'web', p_ip_hash, p_start_url, with_login, p_access_mode)
  returning id into new_id;

  if with_login then
    insert into public.run_secrets (run_id, test_email, test_password)
    values (new_id, p_test_email, p_test_password);
  end if;
  return jsonb_build_object('id', new_id);
end;
$$;

revoke execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text)
  from public, anon, authenticated;
grant execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- Which worker took each run (2026-10-12). Safe to re-run.
-- ---------------------------------------------------------------------------

-- Host name and agent version of the worker that claimed the run, e.g. "ip-10-0-1-5@907b4b3".
-- Set by claim_run itself, so a result always says where it was produced.
alter table public.runs add column if not exists worker_id text;

-- claim_run now takes the worker id. A worker still calling it with no argument keeps working
-- (the argument has a default). The zero-argument version is dropped so only one function exists.
drop function if exists public.claim_run();

create or replace function public.claim_run(p_worker_id text default null)
returns setof public.runs
language sql
security invoker
set search_path = ''
as $$
  update public.runs
  set status = 'running', started_at = now(), worker_id = p_worker_id
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

revoke execute on function public.claim_run(text) from public, anon, authenticated;
grant execute on function public.claim_run(text) to service_role;

-- ===========================================================================
-- REPORT V2 (2026-10-12): success condition, verdict, run facts. Safe to re-run.
-- Own block, last in the file, so it merges cleanly with other changes to this file.
-- ===========================================================================

-- What the founder said success looks like (the form's optional "What does success look like?").
alter table public.runs add column if not exists success_condition text;

-- One verdict per run: {kind, headline, where_step, where_url, evidence_quote, basis, ...}.
alter table public.runs add column if not exists verdict jsonb;

-- How the report was made: steps, recoveries, own issues, reloads, page errors, verifier, cost, time,
-- agent version, worker id, trace id.
alter table public.runs add column if not exists run_facts jsonb;

-- enqueue_web_run takes the success condition as its last argument (default null). If another change
-- also adds an argument to this function, keep both: this is the only function that queues web runs.
drop function if exists public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text);

create or replace function public.enqueue_web_run(
  p_url text,
  p_goal text,
  p_ip_hash text,
  p_max_queued integer,
  p_max_per_hour integer,
  p_start_url text default null,
  p_test_email text default null,
  p_test_password text default null,
  p_access_mode text default null,
  p_success_condition text default null
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
  from public.runs where ip_hash = p_ip_hash and created_at > now() - interval '1 hour';
  if recent_count >= p_max_per_hour then
    return jsonb_build_object('error', 'rate_limited',
      'retry_after_seconds', ceil(extract(epoch from (oldest_recent + interval '1 hour' - now())))::integer);
  end if;

  insert into public.runs (url, goal, source, ip_hash, start_url, has_test_login, access_mode, success_condition)
  values (p_url, p_goal, 'web', p_ip_hash, p_start_url, with_login, p_access_mode, p_success_condition)
  returning id into new_id;

  if with_login then
    insert into public.run_secrets (run_id, test_email, test_password)
    values (new_id, p_test_email, p_test_password);
  end if;
  return jsonb_build_object('id', new_id);
end;
$$;

revoke execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text, text)
  from public, anon, authenticated;
grant execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text, text)
  to service_role;

-- ---------------------------------------------------------------------------
-- Understand mode (2026-10-12): "Understand this website" writes a sourced product brief. Safe to re-run.
-- ---------------------------------------------------------------------------

-- A run is a 'test' (the visit, as before) or an 'understand' run (read a few pages, write a brief).
-- The worker's claim_run() claims both; it reads kind to decide what to do.
alter table public.runs add column if not exists kind text not null default 'test'
  check (kind in ('test', 'understand'));

-- The brief, as JSON, on the understand run itself. A site that could not be read gets
-- {"status": "could_not_read", "message": "..."} here and status 'failed'.
alter table public.runs add column if not exists brief jsonb;

-- For a test run started from a brief: the understand run (the brief) it came from.
alter table public.runs add column if not exists brief_run_id uuid
  references public.runs (id) on delete set null;

create index if not exists runs_brief_run_id_idx on public.runs (brief_run_id) where brief_run_id is not null;

-- Queue an understand run from the web app, under the same two limits as test runs (the queue and the
-- per-visitor hour), in one transaction. Returns {"id": ...} or {"error": ...}.
create or replace function public.enqueue_understand_run(
  p_url text,
  p_ip_hash text,
  p_max_queued integer,
  p_max_per_hour integer
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

  insert into public.runs (url, goal, source, ip_hash, kind, access_mode)
  values (p_url, 'Understand this website', 'web', p_ip_hash, 'understand', 'public')
  returning id into new_id;

  return jsonb_build_object('id', new_id);
end;
$$;

revoke execute on function public.enqueue_understand_run(text, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.enqueue_understand_run(text, text, integer, integer) to service_role;

-- ---------------------------------------------------------------------------
-- Founder brief (2026-10-12): a second report from a stored product brief. Safe to re-run.
-- ---------------------------------------------------------------------------

-- A founder brief is its own run of kind 'founder_brief': brief_run_id points at the product brief it was
-- written from, and the finished report is saved in its `brief` column. The worker claims it like any run
-- and fetches nothing: it writes from the stored product brief.
alter table public.runs drop constraint if exists runs_kind_check;
alter table public.runs add constraint runs_kind_check
  check (kind in ('test', 'understand', 'founder_brief'));

-- Ask for a founder brief of a finished product brief. If one is already queued, running or done for it,
-- its id is returned (and no new run or limit is used). Otherwise the same queue and per-visitor limits
-- as other runs apply. Returns {"id": ...}, or {"error": "no_brief" | "queue_full" | "rate_limited"}.
create or replace function public.enqueue_founder_brief_run(
  p_brief_id uuid,
  p_ip_hash text,
  p_max_queued integer,
  p_max_per_hour integer
)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
  source_url text;
  existing_id uuid;
  queued_count integer;
  recent_count integer;
  oldest_recent timestamptz;
  new_id uuid;
begin
  perform pg_advisory_xact_lock(hashtext('public.enqueue_web_run'));

  select url into source_url from public.runs
  where id = p_brief_id and kind = 'understand' and status = 'done' and brief is not null;
  if source_url is null then
    return jsonb_build_object('error', 'no_brief');
  end if;

  select id into existing_id from public.runs
  where brief_run_id = p_brief_id and kind = 'founder_brief' and status in ('queued', 'running', 'done')
  order by created_at desc limit 1;
  if existing_id is not null then
    return jsonb_build_object('id', existing_id);
  end if;

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

  insert into public.runs (url, goal, source, ip_hash, kind, access_mode, brief_run_id)
  values (source_url, 'Founder brief', 'web', p_ip_hash, 'founder_brief', 'public', p_brief_id)
  returning id into new_id;

  return jsonb_build_object('id', new_id);
end;
$$;

revoke execute on function public.enqueue_founder_brief_run(uuid, text, integer, integer)
  from public, anon, authenticated;
grant execute on function public.enqueue_founder_brief_run(uuid, text, integer, integer) to service_role;

-- ===========================================================================
-- CHECK AGAIN (2026-10-12): re-run the same journey after a fix. Safe to re-run.
-- Own block, last in the file.
-- ===========================================================================

-- The run this one re-checks (always the original, never a retest of a retest), and the comparison the
-- worker made: a label for each old finding, the new ones, and the verdicts side by side.
alter table public.runs add column if not exists retest_of uuid references public.runs (id) on delete set null;
alter table public.runs add column if not exists retest jsonb;

create index if not exists runs_retest_of_idx on public.runs (retest_of) where retest_of is not null;

-- enqueue_web_run gains p_retest_of as its last argument (default null); every earlier argument is
-- unchanged. Retests go through this same function, so they get the same limits as any new run.
drop function if exists public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text, text);

create or replace function public.enqueue_web_run(
  p_url text,
  p_goal text,
  p_ip_hash text,
  p_max_queued integer,
  p_max_per_hour integer,
  p_start_url text default null,
  p_test_email text default null,
  p_test_password text default null,
  p_access_mode text default null,
  p_success_condition text default null,
  p_retest_of uuid default null
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

  if p_retest_of is not null and not exists (select 1 from public.runs where id = p_retest_of) then
    return jsonb_build_object('error', 'original_not_found');
  end if;

  select count(*) into queued_count from public.runs where status = 'queued';
  if queued_count >= p_max_queued then
    return jsonb_build_object('error', 'queue_full');
  end if;

  select count(*), min(created_at) into recent_count, oldest_recent
  from public.runs where ip_hash = p_ip_hash and created_at > now() - interval '1 hour';
  if recent_count >= p_max_per_hour then
    return jsonb_build_object('error', 'rate_limited',
      'retry_after_seconds', ceil(extract(epoch from (oldest_recent + interval '1 hour' - now())))::integer);
  end if;

  insert into public.runs (url, goal, source, ip_hash, start_url, has_test_login, access_mode, success_condition,
                           retest_of)
  values (p_url, p_goal, 'web', p_ip_hash, p_start_url, with_login, p_access_mode, p_success_condition,
          p_retest_of)
  returning id into new_id;

  if with_login then
    insert into public.run_secrets (run_id, test_email, test_password)
    values (new_id, p_test_email, p_test_password);
  end if;
  return jsonb_build_object('id', new_id);
end;
$$;

revoke execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text, text, uuid)
  from public, anon, authenticated;
grant execute on function public.enqueue_web_run(text, text, text, integer, integer, text, text, text, text, text, uuid)
  to service_role;

-- ===========================================================================
-- FEEDBACK (2026-10-12): did a finding help? One vote per finding per visitor. Safe to re-run.
-- Own block, last in the file, so it merges cleanly with other changes to this file.
-- ===========================================================================

-- The only data kept about a voter is the keyed IP hash the rate limit already uses (never the address).
create table if not exists public.finding_feedback (
  run_id     uuid not null references public.runs (id) on delete cascade,
  finding_id text not null check (char_length(finding_id) between 1 and 64),
  verdict    text not null check (verdict in ('useful', 'not_a_problem', 'fixed')),
  ip_hash    text not null,
  created_at timestamptz not null default now(),
  -- one vote per finding per visitor: a later vote replaces the earlier one
  primary key (run_id, finding_id, ip_hash)
);

create index if not exists finding_feedback_verdict_idx on public.finding_feedback (verdict);

-- Service role only, like the other tables.
alter table public.finding_feedback enable row level security;
revoke all on table public.finding_feedback from anon, authenticated;
grant select, insert, update, delete on table public.finding_feedback to service_role;

-- Record a vote, replacing this visitor's earlier vote on the same finding (and dating it now).
create or replace function public.record_finding_feedback(
  p_run_id uuid,
  p_finding_id text,
  p_verdict text,
  p_ip_hash text
)
returns void
language sql
security invoker
set search_path = ''
as $$
  insert into public.finding_feedback (run_id, finding_id, verdict, ip_hash)
  values (p_run_id, p_finding_id, p_verdict, p_ip_hash)
  on conflict (run_id, finding_id, ip_hash)
  do update set verdict = excluded.verdict, created_at = now();
$$;

revoke execute on function public.record_finding_feedback(uuid, text, text, text)
  from public, anon, authenticated;
grant execute on function public.record_finding_feedback(uuid, text, text, text) to service_role;
