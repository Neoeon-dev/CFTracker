create extension if not exists pgcrypto;

create table if not exists public.users (
  id uuid primary key default gen_random_uuid(),
  cf_handle text unique not null,
  timezone text not null default 'Asia/Kolkata',
  created_at timestamptz not null default now()
);

create table if not exists public.problems (
  id bigserial primary key,
  contest_id integer not null,
  problem_index text not null,
  name text not null,
  rating integer,
  tags text[] not null default '{}',
  unique (contest_id, problem_index)
);

create table if not exists public.submissions (
  id bigint primary key,
  user_id uuid not null references public.users(id) on delete cascade,
  problem_id bigint references public.problems(id) on delete set null,
  contest_id integer,
  problem_index text,
  verdict text not null,
  programming_language text,
  submitted_at timestamptz not null,
  handle text not null,
  created_at timestamptz not null default now()
);

create index if not exists submissions_user_time_idx
  on public.submissions(user_id, submitted_at desc);
create index if not exists submissions_user_verdict_idx
  on public.submissions(user_id, verdict);
create index if not exists submissions_problem_idx
  on public.submissions(problem_id);

alter table public.users enable row level security;
alter table public.problems enable row level security;
alter table public.submissions enable row level security;

-- Backend-only application: keep the tables inaccessible through anon/authenticated
-- Data API unless you intentionally add policies later.

create or replace view public.solved_problems as
select distinct on (s.user_id, s.contest_id, s.problem_index)
  s.user_id,
  s.contest_id,
  s.problem_index,
  p.id as problem_id,
  p.name,
  p.rating,
  p.tags,
  s.submitted_at as solved_at
from public.submissions s
join public.problems p on p.id = s.problem_id
where s.verdict = 'OK'
order by s.user_id, s.contest_id, s.problem_index, s.submitted_at asc;
