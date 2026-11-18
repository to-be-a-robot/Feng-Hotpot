-- Feng Hotpot — schema.
-- Follows Tyler's docs/FRONTEND_SPEC.md §6 (origin/frontend) and his answers on
-- return codes, voids and occasions (2026-11-18). Open items are marked
-- "PENDING:" and tracked in /PENDING.md.
--
-- Conventions:
--   * Money is integer cents. Timestamps are timestamptz (UTC). Campaign dates
--     are local dates in the location's time zone (locations.timezone).
--   * Allowed values use CHECK constraints, not enum types (cheap to change).
--   * Embedding columns use an untyped `vector` until the model is agreed
--     (see supabase/pending/).
--   * Every table simulation writes to has is_simulated.

create extension if not exists vector;

create or replace function set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- Optimistic locking: callers update `... where id = $1 and version = $2`;
-- the trigger bumps the version.
create or replace function bump_version() returns trigger
language plpgsql as $$
begin
  new.version = old.version + 1;
  return new;
end;
$$;

-- ===========================================================================
-- Reference tables
-- ===========================================================================

create table locations (
  slug        text primary key check (slug ~ '^[a-z0-9_]+$'),
  name        text not null,
  timezone    text not null,             -- IANA name, e.g. America/Los_Angeles
  address     text,                      -- PENDING: real addresses
  is_active   boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

-- Owned by Aolin; editable without a code change. Never delete an occasion a
-- campaign uses (FK is RESTRICT) — set is_active = false to hide it.
create table occasions (
  id                         uuid primary key default gen_random_uuid(),
  slug                       text not null unique check (slug ~ '^[a-z0-9_]+$'),
  name                       text not null,
  name_zh                    text,
  code_prefix                text not null unique check (code_prefix ~ '^[A-Z]{2,8}$'),  -- FENG-<prefix>-XXXXXX
  offer_title_en             text not null,
  offer_title_zh             text not null,
  offer_details_en           text,
  offer_details_zh           text,
  -- D4 (Aolin): what Feng Hotpot spends to get one creator's post (comped meal + any
  -- fee). NOT the value of offers diners redeem.
  default_cost_cents         integer not null default 0 check (default_cost_cents between 0 and 1000000),
  return_offer_title_en      text not null,
  return_offer_title_zh      text not null,
  return_offer_details_en    text,
  return_offer_details_zh    text,
  return_valid_days          integer not null default 30 check (return_valid_days between 1 and 365),
  is_active                  boolean not null default true,
  sort_order                 integer not null default 0,
  created_at                 timestamptz not null default now(),
  updated_at                 timestamptz not null default now()
);

create table app_settings (
  key    text primary key,
  value  text not null
);

-- PENDING (D1): sign-in method. user_id is the Supabase auth user id.
create table profiles (
  user_id       uuid primary key,
  role          text not null check (role in ('manager', 'staff', 'admin')),
  locations     text[] not null default '{}',
  display_name  text,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);
do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'auth') then
    alter table profiles add constraint profiles_user_fk
      foreign key (user_id) references auth.users (id) on delete cascade;
  end if;
end;
$$;

-- ===========================================================================
-- Creators and brand material
-- ===========================================================================

-- One row per platform account. PENDING: confirm vs one person, many accounts.
create table creators (
  id               uuid primary key default gen_random_uuid(),
  external_id      text unique,                   -- id in Aolin's sheets (e.g. c_001); joins hand labels
  handle           text not null,                 -- stored without '@'
  display_name     text,
  platform         text not null check (platform in ('tiktok', 'instagram', 'xiaohongshu')),
  profile_url      text check (profile_url ~ '^https://' and length(profile_url) <= 2048),
  city             text,
  bio              text,                          -- untrusted text from the profile
  followers        integer check (followers >= 0),
  score            numeric(5,2) check (score between 0 and 100),   -- null until scored
  score_breakdown  jsonb,                                          -- values 0–1 or null
  score_reason     text,
  scored_at        timestamptz,
  source           text not null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (platform, handle)
);
create index creators_city_idx  on creators (city);
create index creators_score_idx on creators (score desc nulls last);

create table creator_posts (
  id               uuid primary key default gen_random_uuid(),
  creator_id       uuid not null references creators (id) on delete cascade,
  url              text not null,
  caption          text,
  lang             text,
  posted_at        timestamptz,
  likes            integer check (likes >= 0),
  comments         integer check (comments >= 0),
  embedding        vector,
  embedding_model  text,
  source           text not null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now(),
  unique (creator_id, url)
);
create index creator_posts_creator_idx on creator_posts (creator_id, posted_at desc);

create table brand_corpus (
  id               uuid primary key default gen_random_uuid(),
  kind             text not null,                 -- 'post', 'menu', 'tone', 'location', ...
  text             text not null,
  lang             text,
  embedding        vector,
  embedding_model  text,
  source           text not null,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create unique index brand_corpus_kind_text_uq on brand_corpus (kind, md5(text));

-- ===========================================================================
-- Campaigns
-- ===========================================================================

-- Offer fields are copied from the occasion at creation, so editing an
-- occasion later never changes a live campaign. Status (active/ended) and
-- generation progress are derived, not stored (see campaign_summary()).
create table campaigns (
  id                  uuid primary key default gen_random_uuid(),
  name                text not null check (length(name) between 3 and 80),
  occasion_id         uuid not null references occasions (id) on delete restrict,
  location            text not null references locations (slug),
  start_date          date not null,
  end_date            date not null,
  languages           text[] not null check (languages <@ array['en', 'zh'] and cardinality(languages) > 0),
  offer               jsonb not null,             -- {title:{en,zh}, details:{en,zh}}
  offer_value_cents   integer check (offer_value_cents >= 0),   -- diner offer's value, if known (not creator cost)
  return_offer        jsonb not null,             -- same shape
  return_valid_days   integer not null check (return_valid_days between 1 and 365),
  skipped             jsonb not null default '[]'::jsonb,   -- replayed for idempotent creates
  created_by          uuid,
  idempotency_key     uuid unique,
  is_simulated        boolean not null default false,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  check (end_date >= start_date)
);
create index campaigns_location_idx on campaigns (location, end_date desc);

create table campaign_creators (
  id            uuid primary key default gen_random_uuid(),
  campaign_id   uuid not null references campaigns (id) on delete cascade,
  creator_id    uuid not null references creators (id) on delete restrict,
  cost_cents    integer check (cost_cents between 0 and 1000000),   -- D4: comped meal + fee for this creator's post
  post_url      text check (post_url ~ '^https://' and length(post_url) <= 2048),
  post_date     date,
  version       integer not null default 1,
  is_simulated  boolean not null default false,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  unique (campaign_id, creator_id)
);

-- ===========================================================================
-- Outreach — drafts and human decisions. Nothing here sends a message.
-- ===========================================================================

create table outreach (
  id                   uuid primary key default gen_random_uuid(),
  campaign_id          uuid not null references campaigns (id) on delete cascade,
  campaign_creator_id  uuid not null references campaign_creators (id) on delete cascade,
  creator_id           uuid not null references creators (id) on delete restrict,
  platform             text not null check (platform in ('tiktok', 'instagram', 'xiaohongshu')),
  lang                 text not null check (lang in ('en', 'zh')),
  draft_text           text check (length(draft_text) <= 2000),     -- null while generating
  edited_text          text check (length(edited_text) between 1 and 2000),
  referenced_post_ids  uuid[] not null default '{}',
  status               text not null default 'draft'
    check (status in ('draft', 'approved', 'rejected', 'sent', 'replied', 'declined')),
  has_offer_link       boolean not null default false,
  generation_status    text not null default 'pending' check (generation_status in ('pending', 'ready', 'failed')),
  generation_error     text,
  reject_reason        text check (length(reject_reason) <= 280),
  approver_id          uuid,
  approver             text,
  decided_at           timestamptz,
  sent_at              timestamptz,
  replied_at           timestamptz,
  version              integer not null default 1,
  is_simulated         boolean not null default false,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique (campaign_creator_id, platform, lang)
);
create index outreach_campaign_status_idx on outreach (campaign_id, status);
create index outreach_generation_idx on outreach (generation_status) where generation_status = 'pending';

-- ===========================================================================
-- Codes and redemptions
-- ===========================================================================

-- kind = 'creator': one per campaign creator, many uses, valid for the campaign dates.
-- kind = 'return' : one per first-visit redemption, single use, valid
--                   return_valid_days from the next local day, same location,
--                   independent of the campaign end date.
create table offer_codes (
  id                    uuid primary key default gen_random_uuid(),
  code                  text not null,
  code_normalized       text generated always as (upper(regexp_replace(code, '[^A-Za-z0-9]', '', 'g'))) stored unique,
  kind                  text not null check (kind in ('creator', 'return')),
  campaign_id           uuid not null references campaigns (id) on delete cascade,
  campaign_creator_id   uuid not null references campaign_creators (id) on delete cascade,
  creator_id            uuid not null references creators (id) on delete restrict,
  location              text not null references locations (slug),
  offer                 jsonb not null,            -- snapshot {title:{en,zh}, details:{en,zh}}
  parent_redemption_id  uuid unique,               -- return codes only (FK added below)
  starts_at             timestamptz not null,
  expires_at            timestamptz not null,      -- 23:59:59 local on the last valid day
  max_uses              integer check (max_uses > 0),   -- null = unlimited
  uses                  integer not null default 0 check (uses >= 0),
  status                text not null default 'active' check (status in ('active', 'voided')),
  voided_at             timestamptz,
  voided_reason         text,
  is_simulated          boolean not null default false,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  check ((kind = 'return') = (parent_redemption_id is not null)),
  check ((kind = 'return') = (max_uses is not null)),
  check (max_uses is null or uses <= max_uses),
  check ((status = 'voided') = (voided_at is not null))
);
create unique index offer_codes_creator_code_uq on offer_codes (campaign_creator_id) where kind = 'creator';

create table redemptions (
  id                   uuid primary key default gen_random_uuid(),
  offer_code_id        uuid not null references offer_codes (id) on delete cascade,
  campaign_id          uuid not null references campaigns (id) on delete cascade,
  campaign_creator_id  uuid not null references campaign_creators (id) on delete cascade,
  creator_id           uuid not null references creators (id) on delete restrict,   -- attribution
  type                 text not null check (type in ('first', 'return')),
  visit_number         integer generated always as (case when type = 'return' then 2 else 1 end) stored,
  location             text not null references locations (slug),
  party_size           integer not null check (party_size between 1 and 50),
  redeemed_at          timestamptz not null default now(),
  redeemed_by          uuid,
  idempotency_key      uuid unique,
  voided_at            timestamptz,
  voided_reason        text check (length(voided_reason) <= 280),
  voided_by            uuid,
  is_simulated         boolean not null default false,
  created_at           timestamptz not null default now()
);
create index redemptions_location_idx on redemptions (location, redeemed_at desc);
create index redemptions_attribution_idx on redemptions (campaign_creator_id, type) where voided_at is null;

alter table offer_codes add constraint offer_codes_parent_redemption_fk
  foreign key (parent_redemption_id) references redemptions (id) on delete cascade;

-- ===========================================================================
-- Reviews, briefs, audit
-- ===========================================================================

-- Not attributed to campaigns (location + date matching doesn't prove cause).
create table reviews (
  id             uuid primary key default gen_random_uuid(),
  location       text not null references locations (slug),
  rating         numeric(2,1) check (rating between 0 and 5),
  text           text,
  sentiment      text check (sentiment in ('positive', 'neutral', 'negative', 'mixed')),
  posted_at      timestamptz,
  is_simulated   boolean not null default false,
  source         text not null,
  created_at     timestamptz not null default now()
);
create index reviews_location_idx on reviews (location, posted_at desc);

create table briefs (
  id             uuid primary key default gen_random_uuid(),
  location       text not null references locations (slug),
  week_of        date not null,
  data_through   date not null,
  metrics        jsonb not null,     -- computed in SQL; null = unavailable
  top_creators   jsonb not null default '[]'::jsonb,   -- computed in SQL
  review_summary jsonb,              -- {positive_share, is_simulated, themes[]}; null = no reviews
  content        jsonb not null,     -- wording from the model only
  is_simulated   boolean not null default false,
  generated_at   timestamptz not null default now()
);
create index briefs_location_week_idx on briefs (location, week_of desc);

create table audit_log (
  id         bigint generated always as identity primary key,
  actor_id   uuid,
  action     text not null,        -- e.g. redemption.create, redemption.void, campaign.create
  entity     text not null,
  entity_id  text not null,
  at         timestamptz not null default now(),
  meta       jsonb not null default '{}'::jsonb   -- never personal data
);
create index audit_log_entity_idx on audit_log (entity, entity_id);

-- ===========================================================================
-- Triggers
-- ===========================================================================
create trigger locations_updated_at         before update on locations         for each row execute function set_updated_at();
create trigger occasions_updated_at         before update on occasions         for each row execute function set_updated_at();
create trigger profiles_updated_at          before update on profiles          for each row execute function set_updated_at();
create trigger creators_updated_at          before update on creators          for each row execute function set_updated_at();
create trigger creator_posts_updated_at     before update on creator_posts     for each row execute function set_updated_at();
create trigger brand_corpus_updated_at      before update on brand_corpus      for each row execute function set_updated_at();
create trigger campaigns_updated_at         before update on campaigns         for each row execute function set_updated_at();
create trigger campaign_creators_updated_at before update on campaign_creators for each row execute function set_updated_at();
create trigger outreach_updated_at          before update on outreach          for each row execute function set_updated_at();
create trigger offer_codes_updated_at       before update on offer_codes       for each row execute function set_updated_at();
create trigger campaign_creators_version    before update on campaign_creators for each row execute function bump_version();
create trigger outreach_version             before update on outreach          for each row execute function bump_version();

-- ===========================================================================
-- Row-level security: on everywhere, no policies yet, so the browser's
-- publishable/anon key can read and write nothing. Server code with the
-- service-role key bypasses RLS. PENDING (D1, B1): per-role policies.
-- ===========================================================================
do $$
declare t text;
begin
  foreach t in array array['locations','occasions','app_settings','profiles','creators','creator_posts',
                           'brand_corpus','campaigns','campaign_creators','outreach','offer_codes',
                           'redemptions','reviews','briefs','audit_log']
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end;
$$;
