create table if not exists public.challenges (
  id uuid primary key default gen_random_uuid(),
  slug text unique not null,
  title text not null,
  description text not null,
  icon text not null default '🏆',
  reward_xp integer not null default 100 check (reward_xp >= 0 and reward_xp <= 5000),
  starts_on date,
  ends_on date,
  definition jsonb not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  check (ends_on is null or starts_on is null or ends_on >= starts_on)
);

create index if not exists challenges_active_dates_idx
  on public.challenges(active, starts_on, ends_on);

alter table public.challenges enable row level security;

-- Backend-only application: keep challenges inaccessible from anon/authenticated
-- clients. The FastAPI service uses the Postgres connection string.
