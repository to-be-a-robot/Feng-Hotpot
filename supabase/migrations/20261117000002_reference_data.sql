-- Reference data. Re-runnable; edits made later in the dashboard/SQL editor are
-- not overwritten (do nothing on conflict).

insert into locations (slug, name, timezone, address) values
  ('sunnyvale',    'Sunnyvale',    'America/Los_Angeles', null),   -- PENDING: addresses
  ('philadelphia', 'Philadelphia', 'America/New_York',    null),
  ('rockville',    'Rockville',    'America/New_York',    null)
on conflict (slug) do nothing;

-- Offer wording copied from Tyler's mocks/occasions.json. Chinese is placeholder
-- wording. PENDING (D3, Aolin): offers, costs, the return offer and the 30 days.
insert into occasions (
  slug, name, name_zh, code_prefix,
  offer_title_en, offer_title_zh, offer_details_en, offer_details_zh, default_cost_cents,
  return_offer_title_en, return_offer_title_zh, return_offer_details_en, return_offer_details_zh,
  return_valid_days, sort_order
) values
  ('birthday', 'Birthdays', '生日', 'BDAY',
   'Free birthday dessert', '生日免费甜点', 'For the birthday guest, dine-in only', '生日寿星专享，仅限堂食', 1200,
   'Welcome back: free dessert', '欢迎回来：免费甜点', 'One use · Dine-in', '限用一次 · 仅限堂食', 30, 1),
  ('group_night', 'Group nights', '聚餐之夜', 'GROUP',
   '10% off tables of 6 or more', '六人及以上八折', 'One use per table, dine-in only', '每桌限用一次，仅限堂食', 3000,
   'Welcome back: free dessert', '欢迎回来：免费甜点', 'One use · Dine-in', '限用一次 · 仅限堂食', 30, 2),
  ('cold_week', 'First cold week', '入冬第一周', 'COLD',
   'Free appetizer for your table', '桌上免费开胃菜', 'One per table · Dine-in', '每桌限一份 · 仅限堂食', 4500,
   'Welcome back: free dessert', '欢迎回来：免费甜点', 'One use · Dine-in', '限用一次 · 仅限堂食', 30, 3),
  ('finals_end', 'Finals ending', '期末结束', 'FINALS',
   'Free drink for each guest', '每位客人免费饮品', 'Show a student ID, dine-in only', '凭学生证，仅限堂食', 3500,
   'Welcome back: free dessert', '欢迎回来：免费甜点', 'One use · Dine-in', '限用一次 · 仅限堂食', 30, 4),
  ('payday', 'Payday', '发薪日', 'PAYDAY',
   'Free side dish with any broth', '任意锅底赠小菜一份', 'One per table, dine-in only', '每桌限一份，仅限堂食', 1500,
   'Welcome back: free dessert', '欢迎回来：免费甜点', 'One use · Dine-in', '限用一次 · 仅限堂食', 30, 5)
on conflict (slug) do nothing;

insert into app_settings (key, value) values
  ('public_base_url', 'https://creator-loop.example'),   -- PENDING: real site URL for /r/:code links
  ('staff_void_window_minutes', '15'),
  ('max_creators_per_campaign', '25')                    -- D8
on conflict (key) do nothing;
