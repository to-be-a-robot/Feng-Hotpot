# Mock data

Sample responses that show the shape the frontend expects from each endpoint in `docs/FRONTEND_SPEC.md` (section 5). They are a reference for connecting features, not a requirement on how the backend is built. If a real response needs a different shape, change it and update the matching file here in the same commit.

All handles, links, names and numbers are invented. Profile and post links use `creators.example` so they never point at real accounts; the site link uses `creator-loop.example`. Because post links are not on a known platform domain, the real UI will show its soft "unknown domain" warning for them. That is expected. Chinese text is placeholder wording and should be reviewed by a native speaker.

Timestamps are UTC. Money is in integer cents. Dates are in the location's time zone (Sunnyvale is `America/Los_Angeles`).

## The sample story

The files describe one consistent campaign so they can be compared with each other.

- **Campaign:** "First cold week · Sunnyvale" (`cmp_1`), Nov 20 – Dec 4, 2026, 5 creators, 10 drafts, offer "Free appetizer for your table", $45 per creator. Cost means what the restaurant spends per creator (decision D4), so `offer.value_cents` is `null`: the diner offer's value is not tracked and the UI shows only the offer title.
- **Creators in it:** `c_1` @bayareabites, `c_2` @southbayfood, `c_3` @xiaochi.sv, `c_5` @foodiesv, `c_7` @小吃日记. A second campaign, "Finals week" (`cmp_2`), has `c_4`.
- **Results to date (through Dec 4):** 12 first visits and 3 return visits, $225 total cost, so $18.75 per first visit and a 25% repeat rate.
- **Outreach:** 10 messages: 3 replied, 1 approved, 1 sent, 1 declined, 1 rejected, 3 drafts (one ready, one failed, one still being written).
- **Staff examples** happen on Fri Nov 27 at about 6 PM Sunnyvale time. The brief is for the week of Nov 30, with data through Dec 4.
- **Codes:** creator codes are `FENG-COLD-` plus 6 random characters. Return codes are `BACK-` plus 8, shown as two groups of 4. A return offer starts the next local day and lasts 30 days.
- `creators.json` shows the creators **after** `cmp_1` was created, so `active_campaigns` is filled in. The Creators and Add-to-campaign wireframes show the moment **before** it was created.

If you change a number in one file, check the others. The checks that were run on these files are listed at the bottom.

## Files

| File | Endpoint | What it contains |
|---|---|---|
| `me.json` | `GET /me` | Manager session with demo tools off |
| `summary.json` | `GET /summary` | Nav badge counts (drafts waiting = written drafts, not failed or pending) |
| `occasions.json` | `GET /occasions` | Occasion list with offers |
| `creators.json` | `GET /creators` | 8 creators including edge cases |
| `campaigns_list.json` | `GET /campaigns` | Active, ended and zero-redemption campaigns |
| `campaign_create_response.json` | `POST /campaigns` (201) | The new campaign, drafts running, nobody skipped |
| `campaign_detail.json` | `GET /campaigns/:id` | 5 creators; totals add up |
| `outreach.json` | `GET /outreach` | 10 messages covering every status |
| `public_offer_active.json` | `GET /public/offers/:code` | Active creator offer |
| `public_offer_return.json` | same | Return offer ("welcome back") |
| `public_offer_not_started.json` | same | Offer that starts later |
| `public_offer_expired.json` | same | Offer that has ended |
| `public_offer_unavailable.json` | same (404) | Unknown, used or cancelled code |
| `redemption_first.json` | `POST /redemptions` (201) | First visit, return offer issued |
| `redemption_return.json` | `POST /redemptions` (201) | Return visit, no new code |
| `redemption_errors.json` | `POST /redemptions` errors | One body per error code |
| `redemptions_recent.json` | `GET /redemptions/recent` | Recent redemptions including a voided one |
| `simulate_response.json` | `POST /simulate` | Demo fast-forward result |
| `brief.json` | `GET /briefs/latest` | Normal brief; numbers match `campaign_detail.json` |
| `brief_empty_metrics.json` | same | All-null ratios, no actions, no reviews |
| `errors.json` | any | Standard error bodies, including a stale-version conflict |

## Edge cases built into the data

- `creators.json`: a creator with `score: null` and no breakdown; a partial breakdown; a 60-character handle; 1.2M followers; 120 followers; a Chinese handle with no `profile_url`; a creator already in a different active campaign; and a scraped post caption that contains HTML and a `<script>` tag on purpose. It must display as plain text and never run.
- `outreach.json`: every status; an approved message with no offer link (`has_offer_link: false`); `generation_status` of `failed` and `pending`; empty `referenced_posts`; a referenced post whose excerpt contains HTML.
- `campaign_detail.json`: two creators with no post link and zero visits; one real and two simulated rows.
- `brief_empty_metrics.json`: every ratio is `null`. The UI shows a dash, never 0, NaN or Infinity.

## Checks that were run

Cross-file checks that passed when these files were last edited: every file parses; campaign totals equal the sum of the creator rows; outreach statuses match each creator's summary and the campaign list; generation counts match the outreach items; every creator with visits has a post link and a reply; the brief's numbers match the campaign and the outreach list; codes in message text match each creator's code; the offer-link flag matches the text; code expiry times match the local end of day; the return offer's 30-day window matches the redemption date; the return code used in `redemptions_recent.json` was not the one just issued; summary counts match the data; and every link uses a `.example` host.
