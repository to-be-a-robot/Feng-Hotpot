# Enter playbook and prompt pack

Step-by-step instructions and paste-ready prompts for building the Feng Hotpot Creator Loop screens in Enter **without the GitHub connector**. They follow Enter's own prompt guide (converge.ai/enter/blog/guide-to-prompt): clear requirements, the "why", a fixed design "box", and one screen at a time.

The prompts are built from `FRONTEND_SPEC.md` (section 4 for screens, section 5 for data) and the sample responses in `../mocks/`. If the spec changes, change the prompt too.

## The plan at a glance

| Phase | Starts when | What you do | Done when |
|---|---|---|---|
| 1. Setup | You open Enter | Paste Part 0 | Enter says it understands and builds nothing |
| 2. Build the screens | Phase 1 is done | Send prompts 1 to 7, one at a time. Styling stays plain and neutral. | All seven screens pass their "Done when" lists and the safety check passes |
| 3. Visual customization | Phase 2 is done, **not before** | Brand colors, fonts, logo; polish the phone pages | The whole demo path looks consistent on desktop and phone |
| 4. Real API | Shinjini's API has a public HTTPS URL | Send prompt 8A (preview key), then 8B (real sign-in) when it is set up | The demo path works on real data |
| 5. Export to GitHub | After each approved screen and at the end | Download, unzip into `app/`, scan for secrets, commit | The code is on your branch |

**When does the visual part start?** After Phase 2. In Phase 2 the look is deliberately plain: neutral grays and one placeholder red accent. Do not spend credits on looks until all seven screens work and the demo path is clickable. The only exceptions are bugs that make something unreadable, such as overflowing text. Phase 3 matches the team plan's "Day 2 PM: demo polish". Because every color lives in one set of variables, swapping in the brand colors (prompt 3A) is a single cheap prompt, so you can do that part as soon as Aolin sends the colors.

## Giving Enter the files

Enter's changelog says you can "drag files directly into Chat to start with your own assets and requirements" (June 2026), and it has an **Assets** panel for project assets, reachable in chat with `@assets` (September 2026). A hackathon builder also reports uploading a design image into Enter chat to set the visual direction. Not confirmed: whether your chat accepts text and JSON files (not only images), and whether the Assets panel lets you upload your own files. Check both when you open Enter.

- **Images** (the wireframes in `docs/wireframes/`): drag them into the chat as a visual reference.
- **Text and JSON** (the prompts and sample data): try dragging the file in. If Enter ignores it, paste the contents instead. The upload kit has one folder per screen so either way is quick.
- **Skills** (upload a `.zip` or `.skill` with a `SKILL.md`) are described by Enter as reusable expertise packages, not memory, so don't use them for project context.
- **Connectors** (GitHub, Figma and others) are not needed for this build.

## Before you open Enter

- [ ] One person drives Enter, so credits aren't split. Write down the credit balance.
- [ ] Look for these controls and note which exist: an attach/upload button for images, a Plan Mode switch, a Code tab, and a Publish button. The prompts mention them.
- [ ] Have the sample files open: everything in `mocks/`, and the images in `docs/wireframes/`.
- [ ] Ask Aolin now for the Phase 3 inputs: the logo file, one or two brand colors as hex codes, a font if the brand has one, and three words that describe the tone.
- [ ] Set a budget: keep about a quarter of your credits in reserve for fixes and Phase 3.

## Rules for every prompt

1. One screen per prompt. One change per fix-prompt.
2. Paste only what that screen needs: its prompt and its sample files.
3. Start with an active verb, and say what not to touch ("Do not change any other screen").
4. After every prompt: read what Enter says it did, click through the new screen, then click through the earlier screens for two minutes to catch anything it broke, and note the credits used.
5. Two failed attempts at the same fix: stop. Take a screenshot and describe what you see and what you expected. Enter's guide recommends screenshots for bugs.
6. After a bad change, use Enter's way of restoring an earlier version if it offers one. Otherwise send: "Undo your last change and restore the previous version of <screen>."
7. If Enter starts a new chat or you open a new project, paste Part 0 again. Assume it remembers nothing.
8. Keep a log: the prompt, credits before and after, and the result.

## What to look out for (every phase)

- **Things you didn't ask for.** Enter adding a database, Enter Cloud, Supabase, a login page, or extra pages. Reply: "Remove <thing>. Build only what I described."
- **Data typed into screens.** Sample data must live only behind `src/lib/api.ts`. The safety check below tests this.
- **Earlier screens breaking** when a new screen is added.
- **Text problems.** Overflowing text, squares instead of Chinese characters, long handles breaking the layout.
- **Off-by-one dates.** The samples use Nov 20 to Dec 4, 2026. Check that no date shows a day early or late.
- **Fictional dates.** All sample dates are made up and some are in the future. Statuses and counts must come from the data, never from today's date.
- **Wasted credits.** Repeated failed attempts, or big prompts for small changes.
- **Secrets and unsafe text.** The safety check below covers both.

## Fix-prompt templates

Replace the angle brackets. Each one limits the change.

```text
Layout: On the <screen>, the <element> <what is wrong>. It should <what you expect>. Change only that. Do not change any other screen, any text, or any data.
```
```text
Wrong data: On the <screen>, <field> shows <what you see> but the sample data says <what it should be>. Fix only that.
```
```text
Behavior: When I <do this> on the <screen>, <what happens>. It should <what you expect>. Change only that behavior.
```
```text
Too much: You added <thing I did not ask for>. Remove it and change nothing else.
```
```text
Undo: Undo your last change and restore the previous version of <screen>.
```

## Phase 1: Setup

### Part 0: project brief (paste once, first)

```text
I am building a small web app for Feng Hotpot, a Sichuan hotpot restaurant with locations in Sunnyvale, Philadelphia and Rockville. It helps a restaurant manager find local social media creators, send them personalized invitations (the manager reviews and sends every message themselves), give each creator an offer code, and see which creators bring in first visits and repeat visits.

USERS: (1) a manager, who uses a desktop dashboard with four pages: Creators, Outreach, Campaigns, Weekly Brief; (2) restaurant staff, who use a phone page to redeem codes; (3) diners, who open a public offer page on their phone from a QR code or link.

STACK: React, Vite, TypeScript and Tailwind. Do NOT create a database, do NOT use Enter Cloud, and do NOT connect Enter's own Supabase or any other backend integration. (Later, in prompt 8B, sign-in will call a Supabase project that the backend team owns, using two public settings.) All data goes through one file, src/lib/api.ts, which has one function per endpoint. It reads the base URL from VITE_API_BASE_URL. When VITE_USE_MOCKS is "true" (the default), it returns the JSON sample data kept in src/mocks/, with a short delay, and keeps any changes in memory so the screens are interactive. The screens must never read the sample files directly. api.ts unwraps responses, so screens never see an envelope.

API FUNCTIONS: api.ts will export exactly these functions, with these names. Do not create them yet. When a screen needs one, create it with this exact name, and reuse it on every later screen instead of making a new one: getMe(), getSummary(location), getCreators({location, platform, minScore, q, sort}), getOccasions(), getCampaigns(), createCampaign(body), getCampaign(id), patchCampaignCreator(campaignId, campaignCreatorId, body), getOutreach({campaignId, status, lang}), patchOutreach(id, body), regenerateOutreach(id, version), getPublicOffer(code), redeem(body), getRecentRedemptions(), getRedemption(id), voidRedemption(id, reason), getLatestBrief(location), generateBrief(location), simulate(campaignId, days). Define TypeScript types for each response in src/lib/types.ts, based on the sample data sent with each screen, and reuse them everywhere.

DATA RULES: Use the fields in the data exactly as given. Do not compute statuses, ages or counts from today's date, because the sample dates are fictional and some are in the future.

TEST TOOLS (mock mode only): when the URL has ?dev=1, show a small floating panel with four switches: "Next request fails with a network error", "Next save returns a stale-version conflict", "Slow responses (3 seconds)", and "No brief yet" (getLatestBrief then answers 404 NOT_FOUND). Hide the panel whenever VITE_USE_MOCKS is not "true".

DESIGN RULES (the "box"):
- Light theme only. Font: Inter, with fallbacks for Chinese text (PingFang SC, Noto Sans SC, Microsoft YaHei). The UI is in English; message text can be English or Chinese.
- Define all colors, fonts, radii and spacing as CSS variables in one place. Neutral grays (ink #1D2330, muted #5B6472, lines #CFD4DC, fill #F3F4F7) and one red accent (a placeholder brand red, easy to change). Border radius 8px. Clean, simple, data-friendly layout.
- Never rely on color alone: show status as words. Visible keyboard focus. Touch targets at least 44px on phone pages.
- Every screen needs loading, empty and error states. Errors show a message, a Try again button, and the request id if present.
- Slow server: if a request takes longer than 3 seconds, add the line "Waking up the server. This can take up to a minute." under the loading skeleton. Wait up to 75 seconds before showing the error state.
- Ids are opaque strings (the real server uses long random ids, not c_1 or cmp_1). Never parse them or depend on their format.

SAFETY RULES:
- Render all text (creator captions, AI drafts, brief text) as plain text. Never use dangerouslySetInnerHTML or convert text to HTML.
- Only render a link if its URL starts with https://. External links open in a new tab with rel="noopener noreferrer". Do not load images from external sites; use initials and platform names instead.
- Put no secrets or API keys in the code. Read settings from environment variables whose names start with VITE_.
- Buttons that send data are disabled while the request is running, so a double-click cannot send it twice.

Confirm you understand. Do not build anything yet.
```

**Watch for:** Enter should only confirm. If it starts building, tell it: "Stop. Build nothing until I send a screen." **Done when:** it replies that it understands.

## Phase 2: Build the screens

Each prompt assumes Part 0 was sent first. After each one, do the checks in "Rules for every prompt".

### 1. App shell and Creators page

Sample data: `mocks/creators.json`. Image: `docs/wireframes/02-creators.png`.

```text
Create the app shell and the Creators page (route /creators). Build this one screen only.

SHELL: a header with the title "FENG HOTPOT · Creator Loop", a location selector (Sunnyvale, Philadelphia, Rockville, All), a pill "Includes demo data" shown when any visible row has is_simulated true, and a user menu. Under it, a nav with four tabs: Creators, Outreach (with a small count badge), Campaigns, Weekly Brief. Only Creators works now; the other tabs show a "Coming soon" placeholder. On a phone, the nav becomes a bottom tab bar. The selected location is kept in the URL (?loc=).

CREATORS TABLE, ranked by score, highest first, creators with no score last. Columns: checkbox, platform (Instagram, TikTok, Xiaohongshu), handle, city, followers (18400 shows as 18.4k, 1200000 as 1.2M), score, and a one-line reason (truncate with an ellipsis). Show the score as words: 80 and above "Strong", 60-79 "Good", 40-59 "Mixed", below 40 "Weak", null "Not scored". Clicking a row expands it to show "Why this score" (six small bars for locality, niche, engagement, comment quality, cadence, brand fit; values 0 to 1; a dash if null), up to 3 recent posts as links with the date, and the active campaigns.

FILTERS: a search box for handle, a platform dropdown, a minimum score slider (0 to 100, default 0; creators with no score are hidden when the minimum is above 0), a sort dropdown (score, followers), and a Reset button.

SELECTION: a sticky bottom bar showing "N selected", a Clear button, and an "Add to campaign" button that is disabled at 0 selected. Maximum 25 selected; at 25, other checkboxes are disabled with an explanation. A creator whose active_campaigns list is not empty shows an "In: <campaign name>" chip, and its checkbox is disabled. Selection stays when filters change.

EDGE CASES: long handles truncate with the full text on hover; null values show a dash; no results shows "No creators match" with a Reset button; a creator with no profile_url shows no link.

On a phone, rows become cards.

SAMPLE DATA (use exactly, as src/mocks/creators.json):
[paste mocks/creators.json here]
```

**Watch for:**
- Extra pages, a database, or data typed straight into the table component.
- Score words at the edges: 87 shows Strong, 79 shows Good, a missing score shows Not scored.
- Followers: 18400 shows 18.4k, 1200000 shows 1.2M, 120 shows 120.
- The 60-character handle truncating instead of widening the page.
- The creator with the Chinese name displaying real characters, not squares.
- Creators that already belong to a campaign: the checkbox must be disabled with the chip.

**Done when:** the ranked table loads from the sample data; expanding a row shows the six bars, recent posts and campaigns; the platform filter, search and minimum score work (a minimum above 0 hides the "Not scored" creator); the selection bar counts correctly and "Add to campaign" is disabled at 0 selected.

### 2. Add to campaign dialog

Sample data: `mocks/occasions.json` and `mocks/campaign_create_response.json`. Image: `docs/wireframes/03-add-to-campaign.png`.

```text
Add the "Add to campaign" dialog, opened from the Creators selection bar. Build only this dialog. Do not change the Creators page except to open the dialog.

FIELDS: Occasion (required dropdown loaded from the occasions data; show the selected occasion's offer title under it), Campaign name (prefilled as "<occasion name> · <location>", editable, 3 to 80 characters), Start date and End date (start is today or later; end is on or after start and within 90 days), Location (read-only, from the header), Languages (checkboxes English and 中文, both checked, at least one required), and the selected creators as removable chips. Creators who already have an active campaign are left out and listed with a warning that explains why.

FOOTER: a summary line, "This will create N offer codes and M drafts. Nothing is sent." (N is the number of creators, M is creators times languages), a Cancel button, and "Create campaign". Closing with changes asks "Discard this campaign?".

BEHAVIOR: Create is disabled while sending and sends an idempotency_key (a new random id per attempt). On success, go to the Outreach route (a placeholder for now) with ?campaign_id=<id>. If the server returns skipped creators, show who and why before leaving. Show validation messages next to each field.

SAMPLE DATA: occasions.json and campaign_create_response.json:
[paste both files here]
```

**Watch for:** the dialog changing the Creators page; the summary line not updating when you remove a chip or untick a language; date validation letting an end date before the start through; the Create button working twice on a double-click. **Done when:** validation messages appear next to fields, the summary line updates live, and Create works in mock mode and navigates to the Outreach placeholder.

### 3. Outreach queue

Sample data: `mocks/outreach.json` and `mocks/campaigns_list.json`. Image: `docs/wireframes/04-outreach.png`. Start in Plan Mode: ask for a plan only, review it, then ask it to build.

```text
Build the Outreach page (route /outreach). Build only this page.

TOP: a campaign dropdown (from the campaigns list; required; if none is chosen, show "Pick a campaign" with a link to Creators), a language filter (All, English, 中文), status tabs with counts (Draft, Approved, Sent, Replied, Declined, Rejected, All), and a progress line "Writing drafts… X of Y done" when the campaign's generation status is running (X is generation.done, Y is generation.total; add "· N failed" if any failed). Show an info banner: "AI-written drafts. Nothing is sent automatically. Copy a message, send it yourself on the platform, then mark it as sent."

CARDS: group cards by creator (collapsible) with the handle, platform, followers and an "Open profile" link. Each card shows: language, a status pill, the current_text as plain text, a character count (count characters, not bytes; warn above 1000), "Based on:" links for referenced_posts, and whether the offer link is included. If generation_status is "pending" show "Writing this draft…"; if "failed" show "Draft couldn't be written" with a Try again button.

BUTTONS BY STATUS: draft: Edit, Approve, Reject. approved: Copy message, Mark as sent, Edit (returns it to draft), Reject. rejected: Reopen. sent: Mark replied, Mark declined (text read-only). replied: Mark declined. declined: none. Mark as sent asks for confirmation ("Did you send this message on <platform>? This can't be undone."). Reject takes an optional reason (up to 280 characters). Nothing in this app sends a message.

EDITING: Edit turns the text into a textarea with Cancel, Save, and Save and approve. If the offer link is no longer in the text, show a warning. Approving then needs an explicit confirmation. Block Approve for empty text. Warn before leaving with unsaved edits. Copy uses the clipboard; if it fails, select the text and say to press Ctrl or Cmd+C.

DATA: every change calls patchOutreach with an action (edit, approve, reject, reopen, mark_sent, mark_replied, mark_declined) and the item's version. If it fails with a stale-version error, show "Someone else changed this draft" with both versions and a choice. In mock mode, update the item in memory and increase its version. Counts on tabs update after every action.

SAMPLE DATA: outreach.json and campaigns_list.json:
[paste both files here]
```

**Watch for:**
- Each status showing exactly its own buttons (use the table in the prompt as your checklist).
- Mark as sent asking for confirmation. Nothing in the app should ever say a message was sent by the app.
- The message with a `<script>` tag inside a post excerpt (creator @foodiesv) showing as plain text and never running.
- The approved Chinese message with no offer link showing the "link missing" warning.
- Tab counts changing after every action.
- The failed and pending cards (o_8 and o_9) showing their special states.
- Use the dev panel (`?dev=1`) to force a stale-version conflict and a network error.

**Done when:** each of the ten sample messages shows the right buttons for its status; approve, reject, reopen and mark sent change the status and the tab counts; editing warns when the link is removed; the conflict and error cases show clear messages.

### 4. Campaigns

Sample data: `mocks/campaigns_list.json` and `mocks/campaign_detail.json`. Image: `docs/wireframes/05-campaign-detail.png`.

```text
Build the Campaigns pages. Build only these.

LIST (route /campaigns): a table with name, dates, creators, sent, replied, first visits and status (Active or Ended), and a "New campaign" button that goes to Creators. "Sent" counts messages marked sent, replied or declined; "Replied" counts replied. Take the status from the data; do not work it out from today's date.

DETAIL (route /campaigns/:id): a header with the campaign name, a status pill, dates, location and the offer title (show only the title; offer.value_cents is null, never show or use it). Four summary tiles: First visits, Return visits, Repeat rate (return visits divided by first visits, shown as a percent), Cost per first visit (total cost divided by first visits, in dollars; a dash if there are no first visits). Show a "Simulated" badge on tiles when totals.includes_simulated is true. Then a table, one row per creator: handle, code with a Copy button and a "QR ↓" button that downloads a PNG named <CODE>.png (the QR encodes the code's url; generate it in the browser), outreach status (the furthest status among the creator's messages: replied or declined, then sent, approved, draft), post link, post date, first visits, return visits, cost, and a Simulated badge where is_simulated is true.

INLINE EDITS: the post link is editable in the row: only https:// links, trimmed, at most 2048 characters, with the message "Use a link that starts with https://" otherwise. The post date cannot be more than 1 day in the future. Cost is entered in dollars and stored in cents. Saves send the row's version; handle a stale-version error with a clear message. Ended campaigns are read-only.

A "Fast-forward 2 weeks" button is shown only when the user has the demo_tools feature. It asks for confirmation, is disabled while running, and calls simulate.

SAMPLE DATA: campaigns_list.json and campaign_detail.json:
[paste both files here]
```

**Watch for:**
- The tile math with the sample data: 12 first visits, 3 return visits, 25%, $18.75.
- The QR download: the file name must be the full code, and the QR should scan from a phone.
- The inline link editor rejecting `http://` and showing the message.
- The Fast-forward button staying hidden. To see it, change `features.demo_tools` to `true` in the sample `me.json` data in your project.

**Done when:** list and detail match the sample numbers, inline edits validate, copy and QR download work, and the Simulated badges appear on the right rows.

### 5. Weekly Brief

Sample data: `mocks/brief.json` and `mocks/brief_empty_metrics.json`. Image: `docs/wireframes/06-weekly-brief.png`.

```text
Build the Weekly Brief page (route /brief). Build only this page.

HEADER: "Weekly Brief · <location>", the week ("Week of Nov 30 – Dec 6", from week_of), "Data through <date>" and "Updated <date and time>". A banner shows "Includes demo data (N% of redemptions)" from simulated_share. Show "This brief is out of date." only when generated_at is more than 8 days before the current time. The sample dates are in the future, so the banner should not show for them.

TILES (render only from the metrics object, never from text): First visits, Return visits, Repeat visit rate (percent), Cost per first visit (cents to dollars), Response rate (percent), Hours saved ("≈ 3.5 h", always labeled "estimate"). A null value shows a dash, never 0, NaN or Infinity.

BODY: an "AI-written" label with the headline and highlights from content. A "Creators by visits driven" list (handle, visits, cost) and a "Review signals" card (percent positive with a Simulated badge when review_summary.is_simulated is true, and the themes). A "Recommended actions" row of cards from content.actions (show however many arrive, 0 to 5); a card with a creator_id shows "Go to creator", otherwise no link. A footer line: "Numbers come from your records. The wording is written by AI."

EMPTY AND FAILURE: getLatestBrief answers 404 with error code NOT_FOUND when no brief exists yet. Treat that one answer as the empty state (not an error) and show "Your first brief arrives after the first full week." Test it with the "No brief yet" switch in the test-tools panel. Any other failure shows the normal error state with a Retry button.

SAMPLE DATA: brief.json and brief_empty_metrics.json (use the second to test the empty case):
[paste both files here]
```

**Watch for:** percentages (0.25 shows 25%, 0.8 shows 80%, 0.53 shows 53%); the empty brief showing dashes everywhere, never 0 or NaN; a creator-less action card having no link; the "out of date" banner wrongly appearing. **Done when:** both sample briefs render correctly and the headline, creators, review signals and three action cards match the sample text.

### 6. Public offer page and show-to-staff screen

Sample data: the five `mocks/public_offer_*.json` files. Images: `docs/wireframes/07-offer-page.png` and `08-show-to-staff.png`.

```text
Build the public offer page (route /r/:code), designed for a phone first. It needs no sign-in, no cookies and no analytics, and it must set a noindex meta tag. Build only this page.

OFFER VIEW: "FENG HOTPOT" with an EN / 中文 toggle (default from the browser language; the choice stays for the visit), the location name, the offer title in large type, "Recommended by <handle>" when present, and a box with Valid dates, Terms, and the restaurant address. A large "Show to staff" button (at least 44px tall) opens a full-screen view.

SHOW-TO-STAFF VIEW: a Back button, "Show this to staff", the code in very large monospace type, a QR placeholder block, "Valid at <location> until <date>", and "Staff will check this code." The code comes from the page address, so this view still shows it if the offer details fail to load.

STATES: active shows the offer. not_started shows "This offer starts <date>." expired shows "This offer ended <date>." An unavailable offer (the error code OFFER_UNAVAILABLE) shows one generic message, "This offer isn't available." A network error shows "Can't load right now. Try again." and a rate-limit error shows "Please try again in a minute." A return offer (kind "return") uses the same layout with a "Welcome back" title. Normalize the code from the address: uppercase, no spaces, trailing slash ignored. The layout must work at 320px wide with no sideways scroll.

MOCK MODE: the code in the address picks the sample. FENG-COLD-K7M2QD returns the active offer, BACK-7H2K-QX9M returns the return offer, TEST-NOTSTARTED returns the not-started offer, TEST-EXPIRED returns the expired offer, and any other code returns the unavailable error.

SAMPLE DATA: the five public_offer_*.json files (the unavailable one is the error body):
[paste the files here]
```

**Watch for:** the noindex tag (open the Code tab and look in the page head); no cookies or tracking scripts; layout at 320px; the Chinese toggle switching all text; no external images or fonts. Try each test code in the address bar. **Done when:** all five states render, the toggle works, and Show to staff displays the code large even for the unavailable case.

### 7. Staff redeem

Sample data: `mocks/redemption_first.json`, `redemption_return.json`, `redemption_errors.json`, `redemptions_recent.json`. Images: `docs/wireframes/09-staff-redeem.png` and `10-staff-first-visit-result.png`. Start in Plan Mode.

```text
Build the staff redeem page (route /redeem), designed for a phone. Build only this page.

FORM: the header shows "Redeem a code", the staff member's location (fixed, not editable) and a Sign out button. A Code field (uppercase it, trim it, accept missing dashes and spaces), a Party size stepper (whole number 1 to 50, default 2), and a large Redeem button that is disabled while sending and sends an idempotency_key (a new random id per attempt). Staff never enter a visit number.

RESULT, first visit: "✓ Redeemed", "First visit", the creator handle, the offer title, "Party of N · time". Below it, a "Return offer for this guest" card with the return code in large monospace type, a QR placeholder, "valid until <date> · one use", and "Show or read this to the guest." The screen stays until dismissed with "Redeem another". RESULT, return visit: "Return offer used" with the offer title and no new code.

ERRORS (one message each): CODE_INVALID "We don't recognize that code. Check the spelling."; CODE_NOT_STARTED "This offer starts <date>."; CODE_EXPIRED "This offer ended <date>."; CODE_ALREADY_USED "Already used on <date> at <time>."; CODE_WRONG_LOCATION "This code is valid at <location> only."; CODE_VOIDED "This code was cancelled."; RATE_LIMITED "Too many tries. Wait <n> seconds."; network failure "No connection. Nothing was recorded." If the connection drops after tapping, say "We couldn't confirm this went through. Check Recent." and never claim success or failure.

RECENT: a list of the last 10 redemptions (time, code, party size, a "Return" pill for return visits, "Voided" with a struck-through code). Each first visit has "Show return offer again". A Void button shows while now is before can_void_until, with a confirmation step. In mock mode, make a new redemption voidable for 15 minutes.

Staff pages sign out after 15 minutes of inactivity, and never store codes in browser storage.

MOCK MODE: FENG-COLD-K7M2QD returns the first-visit success (with the return offer), any code starting with BACK- returns the return-visit success, TEST-INVALID, TEST-NOTSTARTED, TEST-EXPIRED, TEST-USED, TEST-WRONGLOC, TEST-VOIDED and TEST-RATELIMIT return the matching error, and any other code returns CODE_INVALID.

SAMPLE DATA: redemption_first.json, redemption_return.json, redemption_errors.json, redemptions_recent.json:
[paste the files here]
```

**Watch for:** every test code giving its own message (try all of them); the first-visit result staying on screen until dismissed; the party size stepper refusing 0 and 51; lowercase and dash-less codes being accepted; a double-tap on Redeem making only one request; the dev panel's network-error switch producing the "couldn't confirm" message, not success. **Done when:** every test code behaves as described, the return offer screen appears, and Recent lists the sample entries.

### Safety check (after prompt 7, in Plan Mode)

```text
Do a read-only check and change nothing. (1) List every file that imports from src/mocks; it should be only src/lib/api.ts. (2) Search the whole project for dangerouslySetInnerHTML, innerHTML, eval, and any hard-coded keys, tokens or passwords, and list every match with its file and line. (3) List every place a link is rendered from data and confirm it only renders https:// links. (4) List every external URL the code loads (images, fonts, scripts) and why. (5) Confirm no database, Enter Cloud or Supabase is used. Report as a short list; do not fix anything yet.
```

Anything it finds gets its own fix-prompt. **Phase 2 is done when** all seven screens meet their "Done when" lists, the safety check is clean, and you can click through this demo path with the sample data: Creators, select five, Add to campaign, Outreach, Campaigns, Weekly Brief, the offer page, and the staff redeem page.

## Phase 3: Visual customization

**It starts only when Phase 2 is done.** Until then the styling stays plain. The exception is prompt 3A (colors and fonts), which only changes variables and can be done any time after prompt 1 once Aolin sends the brand colors.

**Gather first** (from Aolin, the restaurant's website and Instagram, or the brand corpus):
- the logo as an image file (SVG or PNG);
- one or two brand colors as hex codes (use a color picker on the logo to get them);
- a font if the brand has one;
- three words for the tone (for example warm, bold, welcoming);
- the style of photos, if any (this build does not use external images).

**Budget:** keep at least a quarter of your credits for this phase and for the final fixes. Spend less on dashboard looks than on the two customer-facing pages, because the diner and staff screens are what people see on their phones. Stop visual work well before the demo freeze, and after that fix bugs only.

### 3A. Brand colors and fonts (variables only)

```text
Change only the design variables. Do not change layout, text or behavior. Set the accent color to <#hex> and its hover color to <#hex>. Keep the neutral grays. Use <font> for headings and keep Inter for body text, with the same Chinese fallbacks. Make sure all text on the accent color has a contrast ratio of at least 4.5:1; if it does not, use white or near-black text, whichever passes. Apply the change to every screen, and list the variables you changed.
```

### 3B. Logo

Upload the logo file if the chat accepts images. Otherwise describe it and skip this step.

```text
Add the attached Feng Hotpot logo to the dashboard header and to the top of the public offer page. Keep its proportions, make it smaller on phones, and give it the alt text "Feng Hotpot". Do not change anything else.
```

### 3C. Customer-facing pages (offer page and show-to-staff)

```text
Restyle only the public offer page and the show-to-staff screen so they feel warm, welcoming and trustworthy, using the brand colors. Make the offer title larger, add generous spacing, keep one brand-colored button, and show the restaurant name and address clearly. Keep every state, message and behavior exactly as they are. Do not load any external images or fonts. Check it at 320px and 390px wide.
```

### 3D. Dashboard polish

```text
Polish only the visual spacing and alignment of the four dashboard pages: consistent padding, aligned columns, comfortable row height, clear headings, and tidy empty states. Do not change any text, data, behavior or colors. List what you changed on each page.
```

### 3E. Consistency and final check (Plan Mode)

```text
Read-only: walk through the whole demo path (Creators, Add to campaign, Outreach, Campaigns, Weekly Brief, the offer page, staff redeem) and list every inconsistency in spacing, colors, button styles, labels, empty states and phone layout. Rank the top five by how visible they are. Change nothing yet.
```

Then fix the top issues with the templates above, one at a time.

### Final visual checks

- [ ] Text on the accent color passes contrast (a mid-tone red with white text often does; light accents do not).
- [ ] Every screen at phone width, about 390px, and a narrow 320px.
- [ ] Chinese text still shows real characters.
- [ ] The keyboard focus outline is visible on every control.
- [ ] No screen relies on color alone to show status.

## Phase 4: Real API and sign-in

Send these only after Shinjini's API has a public HTTPS URL and you have its address. The backend's own guides are `docs/BACKEND_GUIDE.md` (how the app calls it) and `docs/DEPLOY.md` (how it is put online) on the `backend` branch; the API's live documentation is at `<API address>/docs`.

### 8A. Connect to the real API in preview mode (shared key)

**Do this only after Shinjini confirms:** (1) the API has a public `https://` address, (2) the server's `CORS_ORIGINS` list includes your Enter preview address (or `CORS_ORIGIN_REGEX` covers `enter.pro` addresses), and (3) you have the shared preview key, sent privately. Until real sign-in is set up, the deployed server runs in a preview mode that has no sign-in and wants a shared key in a request header instead.

**About the key.** It will be visible in the published page's code to anyone who looks. Use it only with fictional data, and do not post the published address publicly. Keep it out of the chat, out of the code and out of GitHub: set `VITE_DEV_KEY` where Enter keeps project environment variables or secrets (look in Project Settings). If Enter has no such place, do not paste the key anywhere; ask the team to go straight to 8B instead. Also set `VITE_API_BASE_URL` there.

```text
Switch the app from sample data to the real API in preview mode. Set VITE_USE_MOCKS to "false". Read VITE_API_BASE_URL (an https address) and VITE_DEV_KEY from environment variables; never write either value into the code. Send the header X-Dev-Key with the value of VITE_DEV_KEY on every request except those to /public/*. Add a small "Preview role" menu, shown only when VITE_DEV_KEY is set, with the choices manager, staff and admin; it sends the header X-Dev-Role with the chosen value (default admin), and the app reloads GET /me when it changes. Do not build a sign-in page in this mode: the role from GET /me decides what the user sees (managers see the dashboard, staff see only /redeem). A 401 answer here means the key is missing or wrong: show "The preview key is missing or wrong. Ask Shinjini." instead of redirecting to /login. Treat all ids as opaque strings. Keep working with sample data when VITE_USE_MOCKS is "true". Change nothing about the screens themselves.
```

**Watch for:** the key appearing in the code or in the chat (search for it); the API address typed with `http://`; a browser CORS error (send the exact preview address to Shinjini); the first request taking about a minute because the free server was asleep (the screen should say it is waking up, not fail); ids that are long random strings working everywhere. **Done when:** the Creators page shows the server's creators, you can create a campaign and see drafts appear, and switching the preview role to staff leaves only `/redeem`.

### 8B. Switch to real sign-in

**Do this only after Shinjini confirms:** (1) accounts exist (created with the `users add` command), (2) the server runs with `AUTH_MODE=supabase`, and (3) your Enter preview and published addresses are on Supabase's redirect list. Ask Shinjini for the two public Supabase settings (the project URL and the publishable key). Never accept a service or secret key.

```text
Replace the preview key with real sign-in. Remove the Preview role menu and every use of VITE_DEV_KEY, X-Dev-Key, X-Dev-Role and X-Dev-Locations. Add sign-in using Supabase Auth with magic links (VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY from environment variables), and a password form as a backup for demo accounts. Send the session token in an Authorization: Bearer header on every request except /public/*. Redirect signed-out users to /login and return them to the page they asked for afterwards (accept only paths starting with /). After sign-in call GET /me and show only the pages the role allows: managers see the dashboard, staff see only /redeem. Always respond to a magic-link request with "If this email is on the team list, a sign-in link is on its way." Never put a service or secret key anywhere in the code.
```

**Watch for:** any leftover `X-Dev-*` header (search the code); the sign-in link opening an address that is not on the redirect list; any secret or service key in the code. **Done when:** you can sign in, the Creators page shows real data, staff accounts can open only `/redeem`, and signing out returns you to `/login`.

## Phase 5: Getting the code into GitHub without the connector

Enter's feature pages say the source code can be exported at any time, and that code download depends on your plan. Check that your account can do it before you rely on it. The preview also lets you open the source in a Code tab.

1. When a screen is approved, export or download the project from Enter. Do this after Phase 2, after Phase 3, and at the end.
2. Unzip it into the repo's `app/` folder, replacing the old contents.
3. Before committing, search for secrets: `grep -rEi "sb_secret|service_role|sk-|password" app/` (run it in the repo, and check that no `.env` file is included).
4. Commit and push with GitHub Desktop (or git) to your branch.
5. If download is not available on your plan, copy files from the Code tab one by one, or ask a mentor how to export.

GitHub is the backup and the handoff. The demo itself runs from Enter's published page.
