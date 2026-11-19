-- POST /demo/reset (spec §5.2, P2): clear campaign activity so the demo can be
-- run again from the start. Keeps creators, posts, scores, brand corpus,
-- occasions, locations, settings, profiles and real (non-simulated) reviews.
-- The API only allows it for admins with DEMO_MODE on.

create or replace function demo_reset(p_actor_id uuid default null) returns jsonb
language plpgsql set search_path = public as $$
declare
  v_campaigns   int;
  v_redemptions int;
  v_reviews     int;
  v_briefs      int;
begin
  select count(*) into v_campaigns from campaigns;
  select count(*) into v_redemptions from redemptions;
  -- Codes reference redemptions and back; deleting campaigns cascades to
  -- campaign_creators, outreach, offer_codes and redemptions.
  delete from campaigns;
  delete from reviews where is_simulated;
  get diagnostics v_reviews = row_count;
  delete from briefs;
  get diagnostics v_briefs = row_count;
  insert into audit_log (actor_id, action, entity, entity_id, meta)
  values (p_actor_id, 'demo.reset', 'demo', 'all',
          jsonb_build_object('campaigns', v_campaigns, 'redemptions', v_redemptions,
                             'simulated_reviews', v_reviews, 'briefs', v_briefs));
  return jsonb_build_object('deleted', jsonb_build_object(
    'campaigns', v_campaigns, 'redemptions', v_redemptions, 'simulated_reviews', v_reviews, 'briefs', v_briefs));
end;
$$;

do $$
begin
  revoke execute on function demo_reset(uuid) from public;
  if exists (select 1 from pg_roles where rolname = 'anon') then
    revoke execute on function demo_reset(uuid) from anon, authenticated;
  end if;
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    grant execute on function demo_reset(uuid) to service_role;
  end if;
end;
$$;
