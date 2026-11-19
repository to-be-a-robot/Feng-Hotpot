-- API-shaped functions: every endpoint's JSON (matching Tyler's mocks/) and the
-- write actions with their rules (spec §3.2, §5.3). Callers pass the actor and
-- an already-checked location; role/location checks happen in the API layer.
-- Errors use the same PT<http> convention as 20261117000003.

-- Which creator cities count as each location's area.
-- PENDING (Aolin): confirm the city lists.
alter table locations add column if not exists creator_cities text[] not null default '{}';
update locations set creator_cities = array['Sunnyvale','San Jose','Santa Clara','Mountain View','Cupertino','Palo Alto',
                                            'Milpitas','Fremont','Los Altos','Campbell','San Francisco','Oakland']
  where slug = 'sunnyvale' and creator_cities = '{}';
update locations set creator_cities = array['Philadelphia','Camden','Cherry Hill','King of Prussia']
  where slug = 'philadelphia' and creator_cities = '{}';
update locations set creator_cities = array['Rockville','Bethesda','Gaithersburg','Silver Spring','Washington']
  where slug = 'rockville' and creator_cities = '{}';

create or replace function parse_cursor(p_cursor text) returns int
language plpgsql immutable as $$
begin
  if p_cursor is null or p_cursor = '' then return 0; end if;
  if p_cursor !~ '^[0-9]{1,9}$' then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"cursor": "Invalid cursor"}}');
  end if;
  return p_cursor::int;
end;
$$;

create or replace function clamp_limit(p_limit int) returns int
language sql immutable as $$ select least(greatest(coalesce(p_limit, 50), 1), 100) $$;

create or replace function excerpt(p text) returns text
language sql immutable as $$ select left(regexp_replace(coalesce(p, ''), '\s+', ' ', 'g'), 140) $$;

-- Drafts store the placeholder {{offer_link}} instead of the full link (spec §5.6),
-- so changing the site URL (app_settings.public_base_url) never breaks drafts.
create or replace function offer_link(p_code text) returns text
language sql stable set search_path = public as $$ select setting('public_base_url') || '/r/' || p_code $$;

create or replace function render_offer_link(p_text text, p_code text) returns text
language sql stable set search_path = public as $$
  select case when p_text is null or p_code is null then p_text
              else replace(p_text, '{{offer_link}}', offer_link(p_code)) end
$$;

create or replace function store_offer_link(p_text text, p_code text) returns text
language sql stable set search_path = public as $$
  select case when p_text is null or p_code is null then p_text
              else replace(p_text, offer_link(p_code), '{{offer_link}}') end
$$;

-- ===========================================================================
-- Occasions
-- ===========================================================================
create or replace function api_occasions() returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object('items', coalesce(jsonb_agg(jsonb_build_object(
      'id', o.id, 'slug', o.slug, 'name', o.name, 'name_zh', o.name_zh,
      'offer_title',   jsonb_build_object('en', o.offer_title_en,   'zh', o.offer_title_zh),
      'offer_details', jsonb_build_object('en', o.offer_details_en, 'zh', o.offer_details_zh),
      'default_cost_cents', o.default_cost_cents,
      'return_offer', jsonb_build_object(
          'title',   jsonb_build_object('en', o.return_offer_title_en,   'zh', o.return_offer_title_zh),
          'details', jsonb_build_object('en', o.return_offer_details_en, 'zh', o.return_offer_details_zh)),
      'return_valid_days', o.return_valid_days) order by o.sort_order, o.name), '[]'::jsonb),
    'next_cursor', null)
  from occasions o where o.is_active
$$;

-- ===========================================================================
-- Creators
-- ===========================================================================
create or replace function creator_json(p_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'id', c.id, 'handle', '@' || c.handle, 'display_name', c.display_name, 'platform', c.platform,
    'profile_url', c.profile_url, 'city', c.city, 'followers', c.followers,
    'score', round(c.score)::int, 'score_reason', c.score_reason, 'score_breakdown', c.score_breakdown,
    'scored_at', iso_utc(c.scored_at),
    'recent_posts', coalesce((
      select jsonb_agg(jsonb_build_object('id', p.id, 'url', p.url, 'excerpt', excerpt(p.caption),
                                          'posted_at', iso_utc(p.posted_at)) order by p.posted_at desc nulls last)
      from (select * from creator_posts where creator_id = c.id order by posted_at desc nulls last limit 3) p), '[]'::jsonb),
    'active_campaigns', coalesce((
      select jsonb_agg(jsonb_build_object('id', k.id, 'name', k.name) order by k.start_date)
      from campaigns k
      join campaign_creators cc on cc.campaign_id = k.id
      join locations l on l.slug = k.location
      where cc.creator_id = c.id and k.end_date >= (now() at time zone l.timezone)::date), '[]'::jsonb),
    'source', c.source)
  from creators c where c.id = p_id
$$;

create or replace function api_creators(
  p_location   text    default null,
  p_platforms  text[]  default null,
  p_min_score  numeric default 0,
  p_q          text    default null,
  p_sort       text    default 'score_desc',
  p_limit      int     default 50,
  p_cursor     text    default null
) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_offset int := parse_cursor(p_cursor);
  v_limit  int := clamp_limit(p_limit);
  v_cities text[];
  v_total  int;
  v_items  jsonb;
begin
  if p_sort is not null and p_sort not in ('score_desc', 'followers_desc', 'recent') then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"sort": "Unknown sort"}}');
  end if;
  if p_location is not null then
    select array(select lower(x) from unnest(creator_cities || name) x) into v_cities
    from locations where slug = p_location;
    if not found then
      perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"location": "Unknown location"}}');
    end if;
  end if;

  with base as (
    select c.id, c.score, c.followers, c.handle,
           (select max(posted_at) from creator_posts p where p.creator_id = c.id) as last_post
    from creators c
    where (v_cities is null or lower(c.city) = any(v_cities))
      and (coalesce(cardinality(p_platforms), 0) = 0 or c.platform = any(p_platforms))
      and (coalesce(p_min_score, 0) <= 0 or c.score >= p_min_score)
      and (coalesce(p_q, '') = '' or strpos(lower(c.handle), lower(ltrim(p_q, '@'))) > 0
                                  or strpos(lower(coalesce(c.display_name, '')), lower(p_q)) > 0)
  ), ranked as (
    select id, count(*) over () as total,
           row_number() over (order by
             case when p_sort = 'followers_desc' then followers end desc nulls last,
             case when p_sort = 'recent' then last_post end desc nulls last,
             case when coalesce(p_sort, 'score_desc') = 'score_desc' then score end desc nulls last,
             handle, id) as rn
    from base
  )
  select coalesce(max(total), 0),
         coalesce(jsonb_agg(creator_json(id) order by rn) filter (where rn > v_offset and rn <= v_offset + v_limit), '[]'::jsonb)
  into v_total, v_items
  from ranked;

  return jsonb_build_object('total', v_total, 'items', v_items,
    'next_cursor', case when v_offset + v_limit < v_total then (v_offset + v_limit)::text end);
end;
$$;

-- ===========================================================================
-- Campaigns
-- ===========================================================================
create or replace function outreach_counts(p_where_campaign uuid, p_where_cc uuid default null) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'draft',    count(*) filter (where status = 'draft'),
    'approved', count(*) filter (where status = 'approved'),
    'sent',     count(*) filter (where status = 'sent'),
    'replied',  count(*) filter (where status = 'replied'),
    'declined', count(*) filter (where status = 'declined'),
    'rejected', count(*) filter (where status = 'rejected'))
  from outreach
  where campaign_id = p_where_campaign and (p_where_cc is null or campaign_creator_id = p_where_cc)
$$;

create or replace function campaign_creator_item(p_cc_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'campaign_creator_id', cc.id, 'version', cc.version,
    'creator', jsonb_build_object('id', c.id, 'handle', '@' || c.handle, 'platform', c.platform, 'profile_url', c.profile_url),
    'code', (select jsonb_build_object('value', oc.code, 'url', setting('public_base_url') || '/r/' || oc.code,
                                       'expires_at', iso_utc(oc.expires_at))
             from offer_codes oc where oc.campaign_creator_id = cc.id and oc.kind = 'creator'),
    'outreach_summary', outreach_counts(cc.campaign_id, cc.id),
    'post_url', cc.post_url, 'post_date', cc.post_date, 'cost_cents', cc.cost_cents,
    'first_visits', s.first_visits, 'return_visits', s.return_visits, 'is_simulated', s.includes_simulated)
  from campaign_creators cc
  join creators c on c.id = cc.creator_id
  join campaign_creator_stats s on s.campaign_creator_id = cc.id
  where cc.id = p_cc_id
$$;

create or replace function campaign_list_item(p_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'id', k.id, 'name', k.name,
    'occasion', jsonb_build_object('id', o.id, 'slug', o.slug, 'name', o.name),
    'location', k.location, 'start_date', k.start_date, 'end_date', k.end_date,
    'status', campaign_status(k.id),
    'creator_count', (select count(*) from campaign_creators where campaign_id = k.id),
    'outreach_counts', outreach_counts(k.id),
    'first_visits',  coalesce((select sum(first_visits)  from campaign_creator_stats where campaign_id = k.id), 0),
    'return_visits', coalesce((select sum(return_visits) from campaign_creator_stats where campaign_id = k.id), 0),
    'generation', campaign_generation(k.id),
    'is_simulated', k.is_simulated or coalesce((select bool_or(includes_simulated) from campaign_creator_stats where campaign_id = k.id), false))
  from campaigns k join occasions o on o.id = k.occasion_id
  where k.id = p_id
$$;

create or replace function api_campaigns(p_location text default null, p_status text default null,
                                         p_limit int default 50, p_cursor text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_offset int := parse_cursor(p_cursor);
  v_limit  int := clamp_limit(p_limit);
  v_ids    uuid[];
  v_total  int;
begin
  if p_status is not null and p_status not in ('active', 'ended') then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"status": "Use active or ended"}}');
  end if;
  select array_agg(id order by start_date desc, created_at desc), count(*) into v_ids, v_total
  from campaigns k
  where (p_location is null or k.location = p_location)
    and (p_status is null or campaign_status(k.id) = p_status);
  return jsonb_build_object(
    'items', coalesce((select jsonb_agg(campaign_list_item(x) order by ord)
                       from unnest(v_ids[v_offset + 1 : v_offset + v_limit]) with ordinality t(x, ord)), '[]'::jsonb),
    'next_cursor', case when v_offset + v_limit < v_total then (v_offset + v_limit)::text end);
end;
$$;

create or replace function api_campaign(p_id uuid) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  k campaigns%rowtype;
begin
  select * into k from campaigns where id = p_id;
  if not found then
    perform fh_raise('NOT_FOUND', 404, 'We couldn''t find that.');
  end if;
  return (
    select jsonb_build_object(
      'id', k.id, 'name', k.name,
      'occasion', jsonb_build_object('id', o.id, 'slug', o.slug, 'name', o.name),
      'location', k.location, 'start_date', k.start_date, 'end_date', k.end_date,
      'status', campaign_status(k.id),
      'offer', jsonb_build_object('title', k.offer -> 'title' ->> 'en', 'title_zh', k.offer -> 'title' ->> 'zh',
                                  'value_cents', k.offer_value_cents),
      'generation', campaign_generation(k.id),
      'totals', (select jsonb_build_object(
                   'first_visits', coalesce(sum(first_visits), 0),
                   'return_visits', coalesce(sum(return_visits), 0),
                   'cost_cents', sum(cost_cents),
                   'includes_simulated', k.is_simulated or coalesce(bool_or(includes_simulated), false))
                 from campaign_creator_stats where campaign_id = k.id),
      'creators', coalesce((select jsonb_agg(campaign_creator_item(cc.id) order by cc.created_at, cc.id)
                            from campaign_creators cc where cc.campaign_id = k.id), '[]'::jsonb),
      'is_simulated', k.is_simulated)
    from occasions o where o.id = k.occasion_id);
end;
$$;

-- PATCH /campaigns/:id/creators/:ccid — p_patch holds only the fields sent,
-- plus "version". A key present with null clears that field.
create or replace function update_campaign_creator(
  p_campaign_id uuid, p_cc_id uuid, p_patch jsonb, p_actor_id uuid default null, p_now timestamptz default now()
) returns jsonb
language plpgsql set search_path = public as $$
declare
  cc       campaign_creators%rowtype;
  loc      locations%rowtype;
  v_fields jsonb := '{}'::jsonb;
  v_url    text;
  v_date   date;
  v_cost   int;
begin
  select * into cc from campaign_creators where id = p_cc_id and campaign_id = p_campaign_id for update;
  if not found then
    perform fh_raise('NOT_FOUND', 404, 'We couldn''t find that.');
  end if;
  if campaign_status(p_campaign_id, p_now) = 'ended' then
    perform fh_raise('INVALID_TRANSITION', 409, 'This campaign has ended and can''t be edited.');
  end if;
  if jsonb_typeof(p_patch -> 'version') is distinct from 'number' then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"version": "Required"}}');
  end if;
  if (p_patch ->> 'version')::int <> cc.version then
    perform fh_raise('STALE_VERSION', 409, 'Someone else changed this row.',
                     jsonb_build_object('current', campaign_creator_item(cc.id)));
  end if;
  select l.* into loc from locations l join campaigns k on k.location = l.slug where k.id = p_campaign_id;

  if p_patch ? 'post_url' then
    v_url := nullif(trim(p_patch ->> 'post_url'), '');
    if v_url is not null and (v_url !~ '^https://[^\s]+$' or length(v_url) > 2048) then
      v_fields := v_fields || '{"post_url": "Use a link that starts with https://"}';
    end if;
  end if;
  if p_patch ? 'post_date' and p_patch ->> 'post_date' is not null then
    begin
      v_date := (p_patch ->> 'post_date')::date;
      if v_date > (p_now at time zone loc.timezone)::date + 1 then
        v_fields := v_fields || '{"post_date": "Can''t be more than 1 day in the future"}';
      end if;
    exception when others then
      v_fields := v_fields || '{"post_date": "Use YYYY-MM-DD"}';
    end;
  end if;
  if p_patch ? 'cost_cents' and p_patch ->> 'cost_cents' is not null then
    if jsonb_typeof(p_patch -> 'cost_cents') <> 'number' or (p_patch ->> 'cost_cents') !~ '^[0-9]+$'
       or (p_patch ->> 'cost_cents')::bigint > 1000000 then
      v_fields := v_fields || '{"cost_cents": "Must be a whole number of cents from 0 to 1,000,000"}';
    else
      v_cost := (p_patch ->> 'cost_cents')::int;
    end if;
  end if;
  if v_fields <> '{}'::jsonb then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', jsonb_build_object('fields', v_fields));
  end if;

  update campaign_creators set
    post_url   = case when p_patch ? 'post_url'   then v_url  else post_url end,
    post_date  = case when p_patch ? 'post_date'  then v_date else post_date end,
    cost_cents = case when p_patch ? 'cost_cents' then v_cost else cost_cents end
  where id = cc.id;

  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_actor_id, 'campaign_creator.update', 'campaign_creator', cc.id::text,
          jsonb_build_object('fields', (select jsonb_agg(k) from jsonb_object_keys(p_patch - 'version') k)));
  return campaign_creator_item(cc.id);
end;
$$;

-- ===========================================================================
-- Outreach
-- ===========================================================================
create or replace function outreach_item(p_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'id', o.id, 'version', o.version, 'campaign_id', o.campaign_id, 'campaign_creator_id', o.campaign_creator_id,
    'creator', jsonb_build_object('id', c.id, 'handle', '@' || c.handle, 'platform', c.platform,
                                  'profile_url', c.profile_url, 'followers', c.followers),
    'platform', o.platform, 'lang', o.lang,
    'draft_text', coalesce(render_offer_link(o.draft_text, oc.code), ''),
    'edited_text', render_offer_link(o.edited_text, oc.code),
    'current_text', coalesce(render_offer_link(coalesce(o.edited_text, o.draft_text), oc.code), ''),
    'status', o.status, 'has_offer_link', o.has_offer_link,
    'referenced_posts', coalesce((
      select jsonb_agg(jsonb_build_object('id', p.id, 'url', p.url, 'excerpt', excerpt(p.caption),
                                          'posted_at', iso_utc(p.posted_at)) order by p.posted_at desc nulls last)
      from creator_posts p where p.id = any(o.referenced_post_ids) and p.creator_id = o.creator_id), '[]'::jsonb),
    'generation_status', o.generation_status, 'reject_reason', o.reject_reason,
    'approver', coalesce(o.approver, o.approver_id::text), 'decided_at', iso_utc(o.decided_at),
    'sent_at', iso_utc(o.sent_at), 'replied_at', iso_utc(o.replied_at),
    'updated_at', iso_utc(o.updated_at), 'is_simulated', o.is_simulated)
  from outreach o join creators c on c.id = o.creator_id
  left join offer_codes oc on oc.campaign_creator_id = o.campaign_creator_id and oc.kind = 'creator'
  where o.id = p_id
$$;

create or replace function api_outreach(p_campaign_id uuid, p_status text default null, p_lang text default null,
                                        p_limit int default 50, p_cursor text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_offset int := parse_cursor(p_cursor);
  v_limit  int := clamp_limit(p_limit);
  v_ids    uuid[];
  v_total  int;
begin
  if p_status is not null and p_status not in ('draft', 'approved', 'rejected', 'sent', 'replied', 'declined') then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"status": "Unknown status"}}');
  end if;
  if p_lang is not null and p_lang not in ('en', 'zh') then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"lang": "Use en or zh"}}');
  end if;
  select array_agg(o.id order by cc.created_at, cc.id, o.lang), count(*) into v_ids, v_total
  from outreach o join campaign_creators cc on cc.id = o.campaign_creator_id
  where o.campaign_id = p_campaign_id
    and (p_status is null or o.status = p_status)
    and (p_lang is null or o.lang = p_lang);
  return jsonb_build_object(
    'items', coalesce((select jsonb_agg(outreach_item(x) order by ord)
                       from unnest(v_ids[v_offset + 1 : v_offset + v_limit]) with ordinality t(x, ord)), '[]'::jsonb),
    'next_cursor', case when v_offset + v_limit < v_total then (v_offset + v_limit)::text end);
end;
$$;

-- PATCH /outreach/:id — spec §3.2 transition table.
create or replace function outreach_action(
  p_id          uuid,
  p_action      text,
  p_version     int,
  p_edited_text text        default null,
  p_reason      text        default null,
  p_actor_id    uuid        default null,
  p_actor_name  text        default null,
  p_now         timestamptz default now()
) returns jsonb
language plpgsql set search_path = public as $$
declare
  o         outreach%rowtype;
  v_target  text;
  v_allowed text[];
  v_text    text;
  v_code    text;
begin
  select * into o from outreach where id = p_id for update;
  if not found then
    perform fh_raise('NOT_FOUND', 404, 'We couldn''t find that.');
  end if;

  v_target := case p_action
    when 'edit' then 'draft' when 'approve' then 'approved' when 'reject' then 'rejected'
    when 'reopen' then 'draft' when 'mark_sent' then 'sent' when 'mark_replied' then 'replied'
    when 'mark_declined' then 'declined' end;
  if v_target is null then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.', '{"fields": {"action": "Unknown action"}}');
  end if;

  -- Repeating an action that already produced the current state is a no-op
  -- (double-click safe), even with the now-stale version.
  if (p_action not in ('edit') and o.status = v_target)
     or (p_action = 'edit' and o.status = 'draft' and o.edited_text is not distinct from
         store_offer_link(trim(p_edited_text), (select code from offer_codes
                                                where campaign_creator_id = o.campaign_creator_id and kind = 'creator'))) then
    return outreach_item(o.id);
  end if;

  if p_version is null or p_version <> o.version then
    perform fh_raise('STALE_VERSION', 409, 'Someone else changed this draft.', jsonb_build_object('current', outreach_item(o.id)));
  end if;

  v_allowed := case p_action
    when 'edit' then array['draft', 'approved'] when 'approve' then array['draft']
    when 'reject' then array['draft', 'approved'] when 'reopen' then array['approved', 'rejected']
    when 'mark_sent' then array['approved'] when 'mark_replied' then array['sent']
    when 'mark_declined' then array['sent', 'replied'] end;
  if not (o.status = any(v_allowed)) then
    perform fh_raise('INVALID_TRANSITION', 409, 'That action isn''t available for this message''s status.',
                     jsonb_build_object('status', o.status, 'action', p_action));
  end if;

  if p_action = 'edit' then
    v_text := trim(coalesce(p_edited_text, ''));
    if length(v_text) not between 1 and 2000 then
      perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.',
                       '{"fields": {"edited_text": "Message must be 1–2000 characters"}}');
    end if;
  else
    v_text := coalesce(o.edited_text, o.draft_text, '');
  end if;
  if p_action = 'approve' and (o.generation_status <> 'ready' and o.edited_text is null
                               or length(trim(v_text)) not between 1 and 2000) then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.',
                     '{"fields": {"text": "The message is empty or longer than 2000 characters"}}');
  end if;
  if p_action = 'reject' and length(coalesce(p_reason, '')) > 280 then
    perform fh_raise('VALIDATION_FAILED', 422, 'Check the highlighted fields.',
                     '{"fields": {"reason": "Up to 280 characters"}}');
  end if;

  select code into v_code from offer_codes where campaign_creator_id = o.campaign_creator_id and kind = 'creator';
  if p_action = 'edit' then
    v_text := store_offer_link(v_text, v_code);
  end if;

  update outreach set
    status          = v_target,
    edited_text     = case when p_action = 'edit' then v_text else edited_text end,
    has_offer_link  = strpos(v_text, '{{offer_link}}') > 0
                      or (v_code is not null and strpos(upper(v_text), upper(v_code)) > 0),
    approver_id     = case when p_action in ('approve', 'reject') then p_actor_id
                           when v_target = 'draft' then null else approver_id end,
    approver        = case when p_action in ('approve', 'reject') then p_actor_name
                           when v_target = 'draft' then null else approver end,
    decided_at      = case when p_action in ('approve', 'reject') then p_now
                           when v_target = 'draft' then null else decided_at end,
    reject_reason   = case when p_action = 'reject' then nullif(trim(p_reason), '')
                           when v_target = 'draft' then null else reject_reason end,
    sent_at         = case when p_action = 'mark_sent' then p_now else sent_at end,
    replied_at      = case when p_action in ('mark_replied', 'mark_declined') then coalesce(replied_at, p_now)
                           else replied_at end
  where id = o.id;

  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_actor_id, 'outreach.' || p_action, 'outreach', o.id::text,
          jsonb_build_object('from', o.status, 'to', v_target, 'edited', o.edited_text is not null or p_action = 'edit',
                             'campaign_id', o.campaign_id));
  return outreach_item(o.id);
end;
$$;

-- POST /outreach/:id/regenerate — back to pending; the draft worker rewrites it.
create or replace function outreach_regenerate(p_id uuid, p_version int, p_actor_id uuid default null) returns jsonb
language plpgsql set search_path = public as $$
declare
  o outreach%rowtype;
begin
  select * into o from outreach where id = p_id for update;
  if not found then
    perform fh_raise('NOT_FOUND', 404, 'We couldn''t find that.');
  end if;
  if o.generation_status = 'pending' then
    return outreach_item(o.id);
  end if;
  if p_version is null or p_version <> o.version then
    perform fh_raise('STALE_VERSION', 409, 'Someone else changed this draft.', jsonb_build_object('current', outreach_item(o.id)));
  end if;
  if o.status not in ('draft', 'approved', 'rejected') then
    perform fh_raise('INVALID_TRANSITION', 409, 'Messages that were sent can''t be rewritten.');
  end if;
  update outreach set status = 'draft', generation_status = 'pending', generation_error = null,
                      draft_text = null, edited_text = null, has_offer_link = false,
                      referenced_post_ids = '{}', approver = null, approver_id = null,
                      decided_at = null, reject_reason = null
  where id = o.id;
  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_actor_id, 'outreach.regenerate', 'outreach', o.id::text, '{}'::jsonb);
  return outreach_item(o.id);
end;
$$;

-- ===========================================================================
-- Summary (nav badges)
-- ===========================================================================
create or replace function api_summary(p_location text, p_now timestamptz default now()) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object(
    'location', p_location,
    'drafts_waiting', (select count(*) from outreach o join campaigns k on k.id = o.campaign_id
                       where k.location = p_location and o.status = 'draft' and o.generation_status = 'ready'),
    'approved_unsent', (select count(*) from outreach o join campaigns k on k.id = o.campaign_id
                        where k.location = p_location and o.status = 'approved'),
    'active_campaigns', (select count(*) from campaigns k where k.location = p_location
                         and k.end_date >= (p_now at time zone l.timezone)::date),
    'redemptions_today', (select count(*) from redemptions r where r.location = p_location and r.voided_at is null
                          and (r.redeemed_at at time zone l.timezone)::date = (p_now at time zone l.timezone)::date))
  from locations l where l.slug = p_location
$$;

-- ===========================================================================
-- Briefs: every number here comes from SQL (spec §5.4).
-- ===========================================================================
create or replace function brief_metrics(p_location text, p_week_of date, p_data_through date) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_campaigns uuid[];
  v_first     int;
  v_return    int;
  v_sim       int;
  v_cost      bigint;
  v_sent      int;
  v_resp      int;
  v_tz        text;
begin
  select timezone into v_tz from locations where slug = p_location;
  select coalesce(array_agg(id), '{}') into v_campaigns from campaigns
  where location = p_location and start_date <= p_week_of + 6 and end_date >= p_week_of;

  select count(*) filter (where r.type = 'first'), count(*) filter (where r.type = 'return'),
         count(*) filter (where r.is_simulated)
  into v_first, v_return, v_sim
  from redemptions r join campaigns k on k.id = r.campaign_id
  where r.campaign_id = any(v_campaigns) and r.voided_at is null
    and (r.redeemed_at at time zone v_tz)::date between k.start_date and p_data_through;

  select sum(cost_cents) into v_cost from campaign_creators where campaign_id = any(v_campaigns);
  select count(*) filter (where status in ('sent', 'replied', 'declined')),
         count(*) filter (where status in ('replied', 'declined'))
  into v_sent, v_resp from outreach where campaign_id = any(v_campaigns);

  return jsonb_build_object(
    'campaign_ids', to_jsonb(v_campaigns),
    'metrics', jsonb_build_object(
      'first_visits', v_first,
      'return_visits', v_return,
      'repeat_visit_rate', case when v_first > 0 then round(v_return::numeric / v_first, 4) end,
      'cost_per_first_visit_cents', case when v_first > 0 and v_cost is not null then round(v_cost::numeric / v_first)::int end,
      'response_rate', case when v_sent > 0 then round(v_resp::numeric / v_sent, 4) end,
      'sent_count', v_sent,
      'response_count', v_resp,
      'simulated_share', case when v_first + v_return > 0 then round(v_sim::numeric / (v_first + v_return), 4) else 0 end),
    'counts_for_hours_saved', jsonb_build_object(
      'creators_in_campaigns', (select count(*) from campaign_creators where campaign_id = any(v_campaigns)),
      'drafts_written', (select count(*) from outreach where campaign_id = any(v_campaigns) and generation_status = 'ready'),
      'redemptions_logged', v_first + v_return),
    'top_creators', coalesce((
      select jsonb_agg(t order by (t ->> 'visits')::int desc, t ->> 'handle')
      from (
        select jsonb_build_object('creator_id', c.id, 'handle', '@' || c.handle, 'campaign_id', cc.campaign_id,
                                  'visits', count(r.id), 'first_visits', count(r.id) filter (where r.type = 'first'),
                                  'return_visits', count(r.id) filter (where r.type = 'return'),
                                  'cost_cents', cc.cost_cents) as t
        from campaign_creators cc
        join creators c on c.id = cc.creator_id
        join campaigns k on k.id = cc.campaign_id
        join redemptions r on r.campaign_creator_id = cc.id and r.voided_at is null
             and (r.redeemed_at at time zone v_tz)::date between k.start_date and p_data_through
        where cc.campaign_id = any(v_campaigns)
        group by c.id, c.handle, cc.campaign_id, cc.cost_cents
        order by count(r.id) desc, c.handle
        limit 5) s), '[]'::jsonb));
end;
$$;

create or replace function brief_json(p_id uuid) returns jsonb
language sql stable set search_path = public as $$
  select jsonb_build_object('id', b.id, 'week_of', b.week_of, 'location', b.location,
                            'generated_at', iso_utc(b.generated_at), 'data_through', b.data_through,
                            'metrics', b.metrics, 'top_creators', b.top_creators,
                            'review_summary', b.review_summary, 'content', b.content,
                            'is_simulated', b.is_simulated)
  from briefs b where b.id = p_id
$$;

create or replace function api_brief_latest(p_location text) returns jsonb
language plpgsql stable set search_path = public as $$
declare v_id uuid;
begin
  select id into v_id from briefs where location = p_location order by week_of desc, generated_at desc limit 1;
  if v_id is null then
    perform fh_raise('NOT_FOUND', 404, 'No brief yet.');
  end if;
  return brief_json(v_id);
end;
$$;

create or replace function api_briefs(p_location text, p_limit int default 50, p_cursor text default null) returns jsonb
language plpgsql stable set search_path = public as $$
declare
  v_offset int := parse_cursor(p_cursor);
  v_limit  int := clamp_limit(p_limit);
  v_ids    uuid[];
begin
  -- Latest brief per week only.
  select array_agg(id order by week_of desc) into v_ids from (
    select distinct on (week_of) id, week_of from briefs where location = p_location
    order by week_of desc, generated_at desc) t;
  return jsonb_build_object(
    'items', coalesce((select jsonb_agg(brief_json(x) order by ord)
                       from unnest(v_ids[v_offset + 1 : v_offset + v_limit]) with ordinality t(x, ord)), '[]'::jsonb),
    'next_cursor', case when v_offset + v_limit < coalesce(cardinality(v_ids), 0) then (v_offset + v_limit)::text end);
end;
$$;

-- ===========================================================================
-- Server-only: revoke EXECUTE from browser roles on everything above.
-- ===========================================================================
do $$
declare
  f regprocedure;
begin
  for f in
    select p.oid::regprocedure from pg_proc p
    where p.pronamespace = 'public'::regnamespace
      and p.proname = any(array['parse_cursor','clamp_limit','excerpt','offer_link','render_offer_link',
        'store_offer_link','api_occasions','creator_json','api_creators',
        'outreach_counts','campaign_creator_item','campaign_list_item','api_campaigns','api_campaign',
        'update_campaign_creator','outreach_item','api_outreach','outreach_action','outreach_regenerate',
        'api_summary','brief_metrics','brief_json','api_brief_latest','api_briefs'])
  loop
    execute format('revoke execute on function %s from public', f);
    if exists (select 1 from pg_roles where rolname = 'anon') then
      execute format('revoke execute on function %s from anon, authenticated', f);
    end if;
    if exists (select 1 from pg_roles where rolname = 'service_role') then
      execute format('grant execute on function %s to service_role', f);
    end if;
  end loop;
end;
$$;
