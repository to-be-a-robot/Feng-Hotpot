-- Campaign creation, redemption, voids and the public offer lookup, as database
-- functions so every caller (Tyler's routes, the simulator, tests) gets the
-- same atomic rules. Tyler's route calls them with the service-role key, e.g.
--   supabase.rpc('redeem_code', { p_code, p_location, p_party_size, p_actor_id, p_idempotency_key })
--
-- ERRORS: business errors are raised with SQLSTATE 'PT<http status>', so
-- PostgREST/supabase-js answer with that HTTP status. The error's
--   message = our error code (e.g. CODE_EXPIRED)
--   hint    = human-readable message
--   details = JSON text, e.g. {"ended":"2026-12-04"} or {"fields":{...}}
-- The route maps that onto the API error body { error: { code, message, details|fields, request_id } }.
--
-- Return-code rules (Tyler, 2026-11-18):
--   * one return code per first-visit redemption, regardless of party size
--   * valid from the next local day through day return_valid_days after the
--     first visit, until 23:59:59 local; same location; ignores campaign end
--   * void first visit, return code unused  -> return code voided (CODE_VOIDED)
--   * void first visit, return code used    -> blocked, 409 INVALID_TRANSITION
--   * void return visit                     -> return code usable again (uses = 0), expiry unchanged
--   * every void records voided_at, voided_reason and an audit_log entry

-- ---------------------------------------------------------------------------
-- Helpers
-- ---------------------------------------------------------------------------

create or replace function fh_raise(p_code text, p_http int, p_message text, p_details jsonb default null)
returns void language plpgsql as $$
begin
  raise exception using
    errcode = 'PT' || p_http::text,
    message = p_code,
    hint    = p_message,
    detail  = coalesce(p_details::text, '{}');
end;
$$;

create or replace function normalize_code(p text) returns text
language sql immutable as $$
  select upper(regexp_replace(coalesce(p, ''), '[^A-Za-z0-9]', '', 'g'))
$$;

create or replace function iso_utc(ts timestamptz) returns text
language sql immutable as $$
  select to_char(ts at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
$$;

create or replace function local_day_start(d date, tz text) returns timestamptz
language sql stable as $$ select d::timestamp at time zone tz $$;

create or replace function local_day_end(d date, tz text) returns timestamptz
language sql stable as $$ select ((d + 1)::timestamp at time zone tz) - interval '1 second' $$;

create or replace function setting(p_key text) returns text
language sql stable set search_path = public as $$ select value from app_settings where key = p_key $$;

-- n characters from an alphabet without look-alikes (no 0/O, 1/I/L), using the
-- CSPRNG behind gen_random_uuid(), with rejection sampling to avoid bias.
create or replace function random_code_chars(n int) returns text
language plpgsql volatile as $$
declare
  alphabet constant text := '23456789ABCDEFGHJKMNPQRSTUVWXYZ';   -- 31 chars
  out text := '';
  b bytea;
  v int;
begin
  while length(out) < n loop
    b := uuid_send(gen_random_uuid());
    for i in 0..15 loop
      continue when i in (6, 8);             -- version/variant bytes aren't fully random
      v := get_byte(b, i);
      continue when v >= 248;                -- 248 = 31 * 8
      out := out || substr(alphabet, (v % 31) + 1, 1);
      exit when length(out) >= n;
    end loop;
  end loop;
  return out;
end;
$$;

-- FENG-COLD-XXXXXX (creator) or BACK-XXXX-XXXX (return).
create or replace function new_code(p_prefix text, p_len int, p_grouped boolean) returns text
language plpgsql volatile set search_path = public as $$
declare
  s text;
  c text;
begin
  loop
    s := random_code_chars(p_len);
    if p_grouped then
      s := substr(s, 1, 4) || '-' || substr(s, 5);
    end if;
    c := p_prefix || s;
    exit when not exists (select 1 from offer_codes where code_normalized = normalize_code(c));
  end loop;
  return c;
end;
$$;

create or replace function offer_json(t_en text, t_zh text, d_en text, d_zh text) returns jsonb
language sql immutable as $$
  select jsonb_build_object('title',   jsonb_build_object('en', t_en, 'zh', t_zh),
                            'details', jsonb_build_object('en', d_en, 'zh', d_zh))
$$;

-- ---------------------------------------------------------------------------
-- Attribution: creator -> code -> first visits -> return visits
-- ---------------------------------------------------------------------------

create or replace view campaign_creator_stats with (security_invoker = true) as
select
  cc.id            as campaign_creator_id,
  cc.campaign_id,
  cc.creator_id,
  cc.cost_cents,
  cc.post_url,
  cc.post_date,
  count(r.id) filter (where r.type = 'first'  and r.voided_at is null)                        as first_visits,
  count(r.id) filter (where r.type = 'return' and r.voided_at is null)                        as return_visits,
  count(r.id) filter (where r.type = 'first'  and r.voided_at is null and not r.is_simulated) as first_visits_real,
  count(r.id) filter (where r.type = 'return' and r.voided_at is null and not r.is_simulated) as return_visits_real,
  cc.is_simulated or coalesce(bool_or(r.is_simulated) filter (where r.voided_at is null), false) as includes_simulated
from campaign_creators cc
left join redemptions r on r.campaign_creator_id = cc.id
group by cc.id;

create or replace function campaign_generation(p_campaign_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'status', case
                when count(*) = 0 then 'none'
                when count(*) filter (where generation_status = 'pending') > 0 then 'running'
                when count(*) filter (where generation_status = 'failed') = count(*) then 'failed'
                when count(*) filter (where generation_status = 'failed') > 0 then 'partial'
                else 'done' end,
    'total',  count(*),
    'done',   count(*) filter (where generation_status = 'ready'),
    'failed', count(*) filter (where generation_status = 'failed'))
  from outreach where campaign_id = p_campaign_id
$$;

create or replace function campaign_status(p_campaign_id uuid, p_now timestamptz default now()) returns text
language sql stable set search_path = public as $$
  select case when (p_now at time zone l.timezone)::date <= c.end_date then 'active' else 'ended' end
  from campaigns c join locations l on l.slug = c.location
  where c.id = p_campaign_id
$$;

-- ---------------------------------------------------------------------------
-- POST /campaigns
-- Creates the campaign, one campaign_creators row + creator code per creator,
-- and one pending outreach row per creator x language (the draft worker fills
-- them in). Codes exist before drafts, so drafts can include the offer link.
-- ---------------------------------------------------------------------------

create or replace function campaign_create_response(p_campaign_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'campaign', jsonb_build_object(
      'id', c.id, 'name', c.name,
      'status', campaign_status(c.id),
      'generation', campaign_generation(c.id)),
    'skipped', c.skipped)
  from campaigns c where c.id = p_campaign_id
$$;

create or replace function create_campaign(
  p_name             text,
  p_occasion_id      uuid,
  p_location         text,
  p_start_date       date,
  p_end_date         date,
  p_creator_ids      uuid[],
  p_languages        text[],
  p_created_by       uuid        default null,
  p_idempotency_key  uuid        default null,
  p_is_simulated     boolean     default false,
  p_now              timestamptz default now()
) returns jsonb
language plpgsql set search_path = public as $$
declare
  occ          occasions%rowtype;
  loc          locations%rowtype;
  v_id         uuid;
  v_cc_id      uuid;
  v_creator    creators%rowtype;
  v_cid        uuid;
  v_lang       text;
  v_langs      text[];
  v_offer      jsonb;
  v_skipped    jsonb := '[]'::jsonb;
  v_added      int := 0;
  v_fields     jsonb := '{}'::jsonb;
  v_today      date;
  v_max        int := coalesce(setting('max_creators_per_campaign')::int, 25);
begin
  if p_idempotency_key is not null then
    select id into v_id from campaigns where idempotency_key = p_idempotency_key;
    if found then
      return campaign_create_response(v_id);
    end if;
  end if;

  select * into occ from occasions where id = p_occasion_id and is_active;
  if not found then v_fields := v_fields || '{"occasion_id": "Choose an occasion"}'; end if;
  select * into loc from locations where slug = p_location and is_active;
  if not found then v_fields := v_fields || '{"location": "Unknown location"}'; end if;
  if p_name is null or length(trim(p_name)) not between 3 and 80 then
    v_fields := v_fields || '{"name": "Must be 3–80 characters"}';
  end if;
  if p_start_date is null or p_end_date is null then
    v_fields := v_fields || '{"start_date": "Required"}';
  elsif p_end_date < p_start_date then
    v_fields := v_fields || '{"end_date": "Must be on or after the start date"}';
  end if;
  if coalesce(cardinality(p_creator_ids), 0) not between 1 and v_max then
    v_fields := v_fields || jsonb_build_object('creator_ids', format('Choose 1–%s creators', v_max));
  end if;
  v_langs := array(select distinct x from unnest(coalesce(p_languages, '{}')) x order by x);
  if cardinality(v_langs) = 0 or not (v_langs <@ array['en', 'zh']) then
    v_fields := v_fields || '{"languages": "Choose English, Chinese or both"}';
  end if;
  if v_fields <> '{}'::jsonb then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', jsonb_build_object('fields', v_fields));
  end if;

  v_today := (p_now at time zone loc.timezone)::date;
  v_offer := offer_json(occ.offer_title_en, occ.offer_title_zh, occ.offer_details_en, occ.offer_details_zh);

  insert into campaigns (name, occasion_id, location, start_date, end_date, languages,
                         offer, return_offer, return_valid_days,
                         created_by, idempotency_key, is_simulated)
  values (trim(p_name), occ.id, loc.slug, p_start_date, p_end_date, v_langs,
          v_offer,
          offer_json(occ.return_offer_title_en, occ.return_offer_title_zh,
                     occ.return_offer_details_en, occ.return_offer_details_zh),
          occ.return_valid_days, p_created_by, p_idempotency_key, p_is_simulated)
  returning id into v_id;

  foreach v_cid in array array(select distinct x from unnest(p_creator_ids) x) loop
    select * into v_creator from creators where id = v_cid;
    if not found then
      v_skipped := v_skipped || jsonb_build_object('creator_id', v_cid, 'reason', 'CREATOR_NOT_FOUND');
      continue;
    end if;
    if exists (
      select 1 from campaign_creators cc join campaigns c on c.id = cc.campaign_id
      where cc.creator_id = v_cid and c.location = loc.slug and c.end_date >= v_today and c.id <> v_id
    ) then
      v_skipped := v_skipped || jsonb_build_object('creator_id', v_cid, 'reason', 'ALREADY_IN_ACTIVE_CAMPAIGN');
      continue;
    end if;

    insert into campaign_creators (campaign_id, creator_id, cost_cents, is_simulated)
    values (v_id, v_cid, occ.default_cost_cents, p_is_simulated)
    returning id into v_cc_id;

    insert into offer_codes (code, kind, campaign_id, campaign_creator_id, creator_id, location, offer,
                             starts_at, expires_at, is_simulated)
    values (new_code('FENG-' || occ.code_prefix || '-', 6, false), 'creator', v_id, v_cc_id, v_cid, loc.slug, v_offer,
            local_day_start(p_start_date, loc.timezone), local_day_end(p_end_date, loc.timezone), p_is_simulated);

    foreach v_lang in array v_langs loop
      insert into outreach (campaign_id, campaign_creator_id, creator_id, platform, lang, is_simulated)
      values (v_id, v_cc_id, v_cid, v_creator.platform, v_lang, p_is_simulated);
    end loop;
    v_added := v_added + 1;
  end loop;

  if v_added = 0 then
    -- Raising rolls back the campaign row too.
    perform fh_raise('VALIDATION_FAILED', 422, 'None of the selected creators can be added.',
                     jsonb_build_object('fields', jsonb_build_object('creator_ids', 'All selected creators were skipped'),
                                        'skipped', v_skipped));
  end if;

  update campaigns set skipped = v_skipped where id = v_id;
  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_created_by, 'campaign.create', 'campaign', v_id::text,
          jsonb_build_object('creators', v_added, 'skipped', jsonb_array_length(v_skipped), 'is_simulated', p_is_simulated));

  return campaign_create_response(v_id);
end;
$$;

-- ---------------------------------------------------------------------------
-- Redemption payloads (POST /redemptions, GET /redemptions/:id, /recent)
-- ---------------------------------------------------------------------------

create or replace function redemption_response(p_redemption_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'redemption', jsonb_build_object(
      'id', r.id, 'type', r.type, 'visit_number', r.visit_number,
      'redeemed_at', iso_utc(r.redeemed_at), 'location', r.location, 'party_size', r.party_size,
      'creator_handle', '@' || cr.handle, 'offer_title', oc.offer -> 'title' ->> 'en',
      'voided_at', iso_utc(r.voided_at), 'is_simulated', r.is_simulated),
    'return_offer', case when ret.id is not null then jsonb_build_object(
      'code', ret.code,
      'url', setting('public_base_url') || '/r/' || ret.code,
      'title', ret.offer -> 'title' ->> 'en',
      'starts_at', iso_utc(ret.starts_at),
      'expires_at', iso_utc(ret.expires_at)) end)
  from redemptions r
  join offer_codes oc on oc.id = r.offer_code_id
  join creators cr on cr.id = r.creator_id
  left join offer_codes ret on ret.parent_redemption_id = r.id and ret.status = 'active'
  where r.id = p_redemption_id
$$;

create or replace function recent_redemption_item(p_redemption_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'id', r.id, 'code', oc.code, 'type', r.type, 'party_size', r.party_size,
    'redeemed_at', iso_utc(r.redeemed_at),
    'voided_at', iso_utc(r.voided_at), 'voided_reason', r.voided_reason,
    'can_void_until', iso_utc(r.redeemed_at + make_interval(mins => coalesce(setting('staff_void_window_minutes')::int, 15))),
    'has_return_offer', exists (select 1 from offer_codes ret
                                where ret.parent_redemption_id = r.id and ret.status = 'active'),
    'is_simulated', r.is_simulated)
  from redemptions r join offer_codes oc on oc.id = r.offer_code_id
  where r.id = p_redemption_id
$$;

create or replace function recent_redemptions(p_location text, p_limit int default 10) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object('location', p_location, 'items', coalesce(jsonb_agg(item order by redeemed_at desc), '[]'::jsonb))
  from (
    select recent_redemption_item(id) as item, redeemed_at
    from redemptions where location = p_location
    order by redeemed_at desc limit least(greatest(p_limit, 1), 100)
  ) t
$$;

-- ---------------------------------------------------------------------------
-- POST /redemptions — atomic. The code row is locked FOR UPDATE, so a
-- single-use return code can't be redeemed twice by concurrent requests.
-- Rate limiting is the route's job (spec §5.5).
-- ---------------------------------------------------------------------------

create or replace function redeem_code(
  p_code             text,
  p_location         text,
  p_party_size       int,
  p_actor_id         uuid        default null,
  p_idempotency_key  uuid        default null,
  p_now              timestamptz default now(),
  p_is_simulated     boolean     default false
) returns jsonb
language plpgsql set search_path = public as $$
declare
  c         offer_codes%rowtype;
  loc       locations%rowtype;
  camp      campaigns%rowtype;
  v_id      uuid;
  v_day     date;
  v_used    redemptions%rowtype;
begin
  if p_party_size is null or p_party_size not between 1 and 50 then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.',
                     '{"fields": {"party_size": "Must be between 1 and 50"}}');
  end if;
  select * into loc from locations where slug = p_location;
  if not found then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.',
                     '{"fields": {"location": "Unknown location"}}');
  end if;

  select * into c from offer_codes where code_normalized = normalize_code(p_code) for update;
  if not found then
    perform fh_raise('CODE_INVALID', 422, 'We don''t recognize that code.');
  end if;

  -- Replay after the lock, so a retry of a successful request returns the
  -- original result instead of CODE_ALREADY_USED.
  if p_idempotency_key is not null then
    select id into v_id from redemptions where idempotency_key = p_idempotency_key;
    if found then
      return redemption_response(v_id);
    end if;
  end if;

  if c.status = 'voided' then
    perform fh_raise('CODE_VOIDED', 422, 'This code was cancelled.');
  end if;
  if c.location <> p_location then
    perform fh_raise('CODE_WRONG_LOCATION', 422, 'This code is valid at another location.',
                     jsonb_build_object('valid_location', c.location));
  end if;
  if p_now < c.starts_at then
    perform fh_raise('CODE_NOT_STARTED', 422, 'This offer hasn''t started yet.',
                     jsonb_build_object('starts', (c.starts_at at time zone loc.timezone)::date));
  end if;
  if p_now >= c.expires_at + interval '1 second' then
    perform fh_raise('CODE_EXPIRED', 422, 'This offer has ended.',
                     jsonb_build_object('ended', (c.expires_at at time zone loc.timezone)::date));
  end if;
  if c.max_uses is not null and c.uses >= c.max_uses then
    select * into v_used from redemptions
    where offer_code_id = c.id and voided_at is null order by redeemed_at desc limit 1;
    perform fh_raise('CODE_ALREADY_USED', 422, 'This code was already used.',
                     jsonb_build_object('used_at', iso_utc(v_used.redeemed_at), 'location', v_used.location));
  end if;

  update offer_codes set uses = uses + 1 where id = c.id;

  insert into redemptions (offer_code_id, campaign_id, campaign_creator_id, creator_id, type,
                           location, party_size, redeemed_at, redeemed_by, idempotency_key, is_simulated)
  values (c.id, c.campaign_id, c.campaign_creator_id, c.creator_id,
          case c.kind when 'creator' then 'first' else 'return' end,
          p_location, p_party_size, p_now, p_actor_id, p_idempotency_key, p_is_simulated)
  returning id into v_id;

  if c.kind = 'creator' then
    select * into camp from campaigns where id = c.campaign_id;
    v_day := (p_now at time zone loc.timezone)::date;
    insert into offer_codes (code, kind, campaign_id, campaign_creator_id, creator_id, location, offer,
                             parent_redemption_id, starts_at, expires_at, max_uses, is_simulated)
    values (new_code('BACK-', 8, true), 'return', c.campaign_id, c.campaign_creator_id, c.creator_id,
            p_location, camp.return_offer, v_id,
            local_day_start(v_day + 1, loc.timezone),
            local_day_end(v_day + camp.return_valid_days, loc.timezone),
            1, p_is_simulated);
  end if;

  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_actor_id, 'redemption.create', 'redemption', v_id::text,
          jsonb_build_object('kind', c.kind, 'code_id', c.id, 'is_simulated', p_is_simulated));

  return redemption_response(v_id);
end;
$$;

-- ---------------------------------------------------------------------------
-- POST /redemptions/:id/void
-- p_actor_role 'staff' is limited to staff_void_window_minutes; managers and
-- admins aren't. The route still checks the caller's role and location.
-- ---------------------------------------------------------------------------

create or replace function void_redemption(
  p_redemption_id  uuid,
  p_reason         text,
  p_actor_id       uuid        default null,
  p_actor_role     text        default 'staff',
  p_now            timestamptz default now()
) returns jsonb
language plpgsql set search_path = public as $$
declare
  r        redemptions%rowtype;
  ret      offer_codes%rowtype;
  v_until  timestamptz;
begin
  select * into r from redemptions where id = p_redemption_id for update;
  if not found then
    perform fh_raise('NOT_FOUND', 404, 'We couldn''t find that.');
  end if;
  if r.voided_at is not null then
    return recent_redemption_item(r.id);              -- repeat = same result
  end if;
  if p_reason is null or length(trim(p_reason)) not between 1 and 280 then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.',
                     '{"fields": {"reason": "Give a reason (up to 280 characters)"}}');
  end if;

  v_until := r.redeemed_at + make_interval(mins => coalesce(setting('staff_void_window_minutes')::int, 15));
  if p_actor_role = 'staff' and p_now > v_until then
    perform fh_raise('INVALID_TRANSITION', 409, 'This visit can no longer be voided here. Ask a manager.',
                     jsonb_build_object('reason', 'VOID_WINDOW_PASSED', 'can_void_until', iso_utc(v_until)));
  end if;

  if r.type = 'first' then
    select * into ret from offer_codes where parent_redemption_id = r.id for update;
    if found and ret.uses > 0 then
      perform fh_raise('INVALID_TRANSITION', 409, 'The return offer from this visit was already used, so it can''t be voided.',
                       jsonb_build_object('reason', 'RETURN_CODE_USED', 'return_code', ret.code));
    end if;
    if found then
      update offer_codes set status = 'voided', voided_at = p_now, voided_reason = trim(p_reason)
      where id = ret.id;
    end if;
  end if;

  -- Give the use back: creator code count stays honest; a return code becomes
  -- usable again (its expiry is unchanged).
  update offer_codes set uses = greatest(uses - 1, 0) where id = r.offer_code_id;

  update redemptions set voided_at = p_now, voided_reason = trim(p_reason), voided_by = p_actor_id
  where id = r.id;

  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_actor_id, 'redemption.void', 'redemption', r.id::text,
          jsonb_build_object('type', r.type, 'reason', trim(p_reason), 'role', p_actor_role,
                             'return_code_voided', ret.id is not null));

  return recent_redemption_item(r.id);
end;
$$;

-- ---------------------------------------------------------------------------
-- GET /public/offers/:code — unknown, voided and used codes all get the same
-- 404, and nothing internal (scores, costs, ids, campaign names) is returned.
-- ---------------------------------------------------------------------------

create or replace function public_offer(p_code text, p_now timestamptz default now()) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  c    offer_codes%rowtype;
  loc  locations%rowtype;
  cr   creators%rowtype;
begin
  select * into c from offer_codes where code_normalized = normalize_code(p_code);
  if not found or c.status = 'voided' or (c.max_uses is not null and c.uses >= c.max_uses) then
    perform fh_raise('OFFER_UNAVAILABLE', 404, 'This offer isn''t available.');
  end if;
  select * into loc from locations where slug = c.location;
  select * into cr  from creators  where id = c.creator_id;

  return jsonb_build_object(
    'status', case when p_now < c.starts_at then 'not_started'
                   when p_now >= c.expires_at + interval '1 second' then 'expired'
                   else 'active' end,
    'offer', c.offer || jsonb_build_object(
               'kind',   c.kind,
               'starts', (c.starts_at  at time zone loc.timezone)::date,
               'ends',   (c.expires_at at time zone loc.timezone)::date),
    'restaurant', jsonb_build_object('name', 'Feng Hotpot', 'location_name', loc.name, 'address', loc.address),
    'recommended_by', case when c.kind = 'creator' then '@' || cr.handle end);
end;
$$;

-- ---------------------------------------------------------------------------
-- Only trusted server code (service role) may call these. Supabase grants
-- EXECUTE on new functions to anon/authenticated by default, so revoke it.
-- ---------------------------------------------------------------------------
do $$
declare
  f text;
  fns text[] := array[
    'create_campaign(text,uuid,text,date,date,uuid[],text[],uuid,uuid,boolean,timestamptz)',
    'redeem_code(text,text,int,uuid,uuid,timestamptz,boolean)',
    'void_redemption(uuid,text,uuid,text,timestamptz)',
    'public_offer(text,timestamptz)',
    'redemption_response(uuid)',
    'recent_redemption_item(uuid)',
    'recent_redemptions(text,int)',
    'campaign_create_response(uuid)',
    'campaign_generation(uuid)',
    'campaign_status(uuid,timestamptz)',
    'new_code(text,int,boolean)'];
begin
  foreach f in array fns loop
    execute format('revoke execute on function %s from public', f);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke execute on function %s from anon, authenticated', f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f);
    end if;
  end loop;
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke all on campaign_creator_stats from anon, authenticated;
  end if;
end;
$$;
