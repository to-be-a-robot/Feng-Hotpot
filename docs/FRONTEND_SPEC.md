# Feng Hotpot Creator Loop: Frontend Spec and Backend Contract

**Version:** 1.1 (draft for team sign-off) · **Date:** 2026-11-18
**For:** Shinjini (backend/AI), Aolin (product), Tyler (frontend)
**Source documents:** the Nov 17 team plan (PDF) and the Converge.AI challenge brief for Feng Hotpot.

> **How to read this.** Section 0 lists what changed from the team plan and what still needs a decision. Sections 1–4 describe the screens (wireframes). Sections 5–6 are the contract Shinjini builds against. Section 7 is security. Section 8 is a test checklist.
> Items are tagged **P0** (needed for the demo loop), **P1** (should have), **P2** (stretch).
>
> **Status of this document.** It describes what the frontend assumes, as a proposal and a reference for the team, not a required way of working. If a backend choice needs a different shape, change it, tell Tyler, and update this file and the matching file in `mocks/` together.

---

## 0. Summary

### 0.1 What changed from the Nov 17 team plan

The team plan is kept as the base. These changes close logic gaps found while turning it into wireframes.

| # | Gap in the plan | How this spec handles it | Backend impact |
|---|---|---|---|
| 1 | **Repeat visits can't be measured.** `redemptions` has no customer identifier, so "visit #" can only count uses of a code. | **Single-use return codes.** When staff redeem a creator's code (first visit), the backend issues a one-time return code tied to that redemption. Redeeming it later = a repeat visit, attributed to the original creator. No diner personal data is collected. Staff no longer type a visit number; it is derived (1 or 2). | New code `kind`, `parent_redemption_id`, expiry; new `type` on redemptions |
| 2 | **No record of what happens after approval.** Statuses stop at draft/approved/rejected, yet the brief shows "response rate". | Outreach statuses extended: `draft → approved → sent → replied / declined`, plus `rejected`. The manager marks a message sent after sending it on the platform. Response rate = replied ÷ sent. | Extended status enum, `sent_at`, `replied_at`, transition rules |
| 3 | **Post link, post date and cost have no input.** The Campaigns page shows them but nothing collects them. | New `campaign_creators` table; the manager edits post link, post date and cost inline on the Campaigns page. | New table + `PATCH` endpoint |
| 4 | **Sequencing:** the offer code must exist before the draft is written, and the draft must contain the offer link. | `POST /campaigns` creates codes first, then generates drafts **asynchronously** with progress. Frontend warns if an edited message loses the offer link. | Async generation + progress status |
| 5 | **No campaign picker or list.** The outreach API filters by campaign but nothing lets the user choose one. | Added `GET /campaigns` (list) and a campaign dropdown on Outreach and Campaigns. A global **location selector** replaces the separate city filter. | New list endpoint |
| 6 | **No login or roles.** A public dashboard with write access could be edited by anyone with the URL. | Three roles (manager, staff, public) with sign-in, plus an audit log. Demo tools are gated. | `profiles`, auth, RLS, `audit_log` |
| 7 | **Language is unspecified for diners.** | Public offer page has an EN / 中文 toggle (defaults to browser language). | none |

### 0.2 Decisions still needed

| ID | Question | Owner | Default assumed in this spec |
|---|---|---|---|
| D1 | How do managers sign in? | Tyler + Shinjini | Email magic link (Supabase Auth) with an allowlist in `profiles` |
| D2 | Return-offer design: personal return code (no data) or capture phone/email (needs consent)? | Aolin | Return code, no personal data |
| D3 | What is the return offer, and for how long is it valid? | Aolin / Sherry Gu | "Welcome back" dessert, 30 days, same location |
| D4 | How is `cost` defined (meal value, creator fee, both)? | Aolin | Meal value per creator, entered in cents, editable |
| D5 | Are codes valid at one location or several? | Aolin | One location per campaign |
| D6 | Which stack builds the frontend (Enter generates React + Vite, not Next.js)? | Tyler + team | Contract below is stack-neutral JSON over HTTPS |
| D7 | How do judges access the demo? | Tyler + Aolin | A read-mostly demo account plus a "Reset demo" tool |
| D8 | Maximum creators per campaign (bounds AI cost) | Shinjini | 25 |

### 0.3 Traceability to the team plan

Nothing in the plan was dropped. Differences are noted.

| Plan requirement | Where |
|---|---|
| Ranked creators table with score + reason; expandable breakdown | §4.2 |
| Filters: location, platform, min score | §4.2 (location moved to header) |
| Multi-select + "Add to campaign" (occasion) | §4.2, §4.3 |
| Draft cards: platform, EN/ZH, message, referenced posts; inline edit, approve, reject; persist | §4.4 |
| "Nothing sends automatically"; approve copies or marks ready | §4.4 (Copy button + Mark as sent) |
| Campaigns: code, post link, post date, redemptions, 2nd visits, cost; QR download | §4.5 |
| QR landing page and staff redemption form | §4.7, §4.8 (visit # now derived) |
| Weekly brief: tiles, creators by visits, review sentiment, 3 actions | §4.6 |
| "Simulated data" badge + "Fast-forward 2 weeks" | §4.5, §7 |

### 0.4 Other differences from the team plan, and who builds what

| Area | Team plan | This spec | Why |
|---|---|---|---|
| Stack | Next.js (App Router), Tailwind, Supabase | Stack-neutral JSON contract (D6) | Enter generates React and Vite, not Next.js |
| Simulate endpoint | `POST /api/simulate` | `POST /simulate` with `campaign_id` | Same endpoint, no `/api` prefix in this document |
| Redemption flow and API routes | Tyler owns the QR page, the redemption form and its API routes | The page and form stay with Tyler. Return-code issuance, single-use checks and attribution need database logic, so Shinjini provides it (a function or RPC) and Tyler's route calls it | Return codes make redemption more than "two simple writes". Confirm with Aolin: the plan sends cross-lane decisions to the product owner |
| Code format | Readable, for example `FENG-COLD-AMY7` | `FENG-COLD-` plus 6 random characters | Codes built from names are easy to guess |
| Brief wording | "redemptions", "2nd visits", "cost per redemption" | "First visits", "Return visits", "Cost per first visit" | Same measures: a redemption of a creator code is a first visit, and a 2nd visit is a return-code redemption |
| Visit number | Staff form shows an auto-suggested visit # | Not entered; derived from the code type | Removes a field and a source of errors |
| Location filter | A filter on the Creators page | A selector in the header that scopes every page | Location also scopes campaigns, briefs and staff access |

The plan's schema, API list, pages, demo path, working agreements and cut order are otherwise followed, including "never cut the weekly brief".

---

## 1. Users and roles

| Role | Who | Can see | Can do |
|---|---|---|---|
| **Manager** | Feng Hotpot owner/marketing | All dashboard pages for their location(s) | Everything except demo tools |
| **Staff** | Restaurant staff on a shared phone/tablet | Only the Redeem page for their location | Redeem codes, void a recent mistake |
| **Admin / demo** | The hackathon team | Everything, plus demo tools | Simulate, reset, regenerate |
| **Public (diner)** | Anyone with a QR or link | Only `/r/:code` | View an offer |
| **Creator** | External | Nothing | Receives messages sent outside the app |

Route guards in the browser are for usability only. The backend enforces every permission (see §7).

---

## 2. Site map and navigation

```text
/login ────────────────────────────────────────────────────────────┐
   │ (after sign-in, returns to the page you came from)             │
   ▼                                                                │
/creators ── select + "Add to campaign" ──► dialog ──► /outreach?campaign_id=…
   │                                                  │
   │                                    approve / copy / mark sent (outside the app: send DM)
   ▼                                                  ▼
/campaigns ─► /campaigns/:id (codes, QR, post links, results)
   │
   ▼
/brief (weekly summary + 3 actions)

PUBLIC:  /r/:code   (diner sees offer; "Show to staff")
STAFF:   /redeem    (enter code + party size → first visit issues a return code)
OTHER:   /403  /404
```

| Route | Access | Purpose | URL state (shareable) |
|---|---|---|---|
| `/login` | public | Sign in | `?next=/path` (same-origin paths only) |
| `/` | any signed-in | Redirects to `/creators` (manager) or `/redeem` (staff) | |
| `/creators` | manager | Discover and select | `?loc&platform&min_score&q&sort` |
| `/outreach` | manager | Review, edit, approve, track drafts | `?campaign_id&status&lang` |
| `/campaigns` | manager | Campaign list | `?status` |
| `/campaigns/:id` | manager | Codes, QR, posts, results | |
| `/brief` | manager | Weekly brief | `?week&loc` |
| `/redeem` | staff, manager | Redeem codes | |
| `/r/:code` | public | Offer page | `?lang=en` or `zh` |

Navigation rules:
- Browser Back/Forward and reload work on every route. Filters live in the URL.
- The nav shows a badge on **Outreach** with the number of drafts waiting for review (P1, from `GET /summary`).
- Manager nav is a top bar on desktop and a bottom tab bar on phones. Staff and public pages have no nav.
- Unknown route → 404 page with a link home. Signed in without permission → 403 page.

---

## 3. End-to-end flow and state machines

### 3.1 The loop

1. Manager opens **Creators**, filters, and selects creators.
2. **Add to campaign**: pick an occasion, dates and languages. Backend creates the campaign, one offer code per creator, and AI drafts (async).
3. Manager opens **Outreach**, edits and approves drafts. **Nothing is sent by the app.**
4. Manager copies a message, sends it on Instagram / TikTok / Xiaohongshu, then clicks **Mark as sent**.
5. Creator replies. Manager clicks **Mark replied** (or **Declined**).
6. Creator posts. Manager records the **post link and date** on the Campaigns page.
7. Diner scans the QR / opens the link → sees the offer → **Show to staff**.
8. Staff redeem the code on `/redeem`. The backend records a **first visit** and issues a single-use **return code**; staff give it to the guest.
9. Guest returns and shows the return code; staff redeem it → **repeat visit**, attributed to the original creator.
10. **Weekly Brief** summarizes results and suggests 3 actions.

### 3.2 Outreach status machine

Statuses: `draft`, `approved`, `rejected`, `sent`, `replied`, `declined`.

| Current status | Allowed actions → resulting status |
|---|---|
| `draft` | `edit` → draft · `approve` → approved · `reject` → rejected |
| `approved` | `edit` → **draft** (text changed, so it needs review again) · `reopen` → draft · `reject` → rejected · `mark_sent` → sent |
| `rejected` | `reopen` → draft |
| `sent` | `mark_replied` → replied · `mark_declined` → declined (text locked) |
| `replied` | `mark_declined` → declined (text locked) |
| `declined` | none (locked) |

Rules:
- Repeating an action that already produced the current state returns **200 with the current item** (safe against double-clicks).
- Any other combination returns `409 INVALID_TRANSITION`. The UI only shows allowed actions, so this happens only with stale screens.
- Every write carries the item's `version`. A mismatch returns `409 STALE_VERSION` with the current item.
- `mark_sent` is irreversible, so the UI confirms it first.
- `mark_sent`, `mark_replied` and `mark_declined` are manual tracking only. The app never sends a message or contacts a platform; the manager records what they did outside the app.
- `mark_declined` also sets `replied_at` if it is empty, because a decline is a response.

### 3.3 Code lifecycle

| Kind | Created | Uses | Valid | Ends |
|---|---|---|---|---|
| `creator` | When the campaign is created | Many (each use is one diner's first visit) | Campaign dates at the campaign's location | Expires at end of local end date |
| `return` | When a first visit is redeemed: one per redemption, whatever the party size | Exactly 1 | From the next local day for 30 days (`return_valid_days`, configurable), same location | Used, expired or voided |

Derived values:
- `type` of a redemption = `first` (creator code) or `return` (return code).
- `visit_number` = 1 for first, 2 for return. Visit 3+ is out of scope (return codes don't issue new return codes).
- A return code expires at 23:59:59 local time on its last day. It does not end with the campaign.
- Voiding a **first visit** cancels its unused return code (it stays unusable and returns `CODE_VOIDED`), and is blocked if the return code was already used. Voiding a **return visit**, for example when staff used the wrong code, makes that return code usable again if it has not expired.
- A repeat visit is attributed to the creator of its parent first-visit redemption.

---

## 4. Wireframes

Wireframes are low-fidelity: layout and behavior, not style. Numbered notes below each wireframe are the requirements. Images of the same screens are in `docs/wireframes/`; the numbered dots on them match these notes.

### 4.0 Shared shell and standard states

```text
DESKTOP (≥1024px)
+----------------------------------------------------------------------------------+
| (1) FENG HOTPOT · Creator Loop   (2) [Sunnyvale ▾]   (3) ● Includes demo data   (4) Tyler ▾ |
+----------------------------------------------------------------------------------+
| (5) Creators    Outreach [2]    Campaigns    Weekly Brief                        |
+----------------------------------------------------------------------------------+
| (6) page content                                                                 |
+----------------------------------------------------------------------------------+

PHONE (<640px): header collapses; (5) becomes a bottom tab bar with 4 icons + labels.
```

1. Logo links to `/`.
2. **Location selector**: Sunnyvale, Philadelphia, Rockville, or All. Scopes every page. Defaults to the user's profile location. Stored in the URL (`?loc=`). Times display in the selected location's time zone (Sunnyvale `America/Los_Angeles`; Philadelphia and Rockville `America/New_York`).
3. Shown when any data on screen has `is_simulated = true`. Clicking explains what "demo data" means.
4. User menu: email, role, **Sign out**.
5. Active item is marked with text and underline, not color alone. The Outreach badge is the number of drafts that are written and waiting for review (`drafts_waiting` from `GET /summary`). Drafts still being written, or that failed, are not counted.

```text
LOADING                 EMPTY                          ERROR (recoverable)
+---------------+       +------------------------+     +-------------------------------+
| ▒▒▒▒▒▒▒▒      |       | No creators match.     |     | ⚠ Couldn't load creators.     |
| ▒▒▒▒▒▒▒▒▒▒▒   |       | [Reset filters]        |     | [Try again]   Ref: req_8f2a   |
+---------------+       +------------------------+     +-------------------------------+
```

Standard state rules (apply to every screen):
- Show a skeleton after 300 ms of loading; never a blank page.
- Empty states say what is missing and give the next action.
- Errors show a message, **Try again**, and the `request_id`. Never show stack traces or database errors.
- If a refresh fails but data is already on screen, keep the data and show a banner "Showing saved results. Couldn't refresh."
- `401` → login with return path. `403` → 403 page. `429` → "Too many requests. Try again in {n}s."
- Refetch data when the browser tab regains focus.
- Offline: a banner "You're offline"; actions are disabled; never show success for an action that didn't reach the server.

### 4.1 Login (`/login`)

```text
+------------------------------------+
|  FENG HOTPOT · Creator Loop        |
|  Sign in                           |
|  (1) Email [____________________]  |
|  (2) [Send sign-in link]           |
|  (3) Check your email for a link.  |
|      [Resend in 30s]               |
+------------------------------------+
```

1. Validates email format before sending.
2. Always responds with "If this email is on the team list, a sign-in link is on its way", whether or not it is allowed (prevents guessing who has access).
3. After sending: show the confirmation and a resend button that is disabled for 30 seconds.
- Expired or used link → "That link has expired. Request a new one."
- `next` parameter must be a same-origin path starting with `/` (blocks open redirects).

### 4.2 Creators (`/creators`) — manager

```text
+----------------------------------------------------------------------------------+
| Creators in Sunnyvale                                        (1) 42 creators     |
| (2) Search [____________]  (3) Platform [All ▾]  (4) Min score [o------] 0       |
| (5) Sort [Score high→low ▾]                              (6) [Reset filters]     |
+----------------------------------------------------------------------------------+
| [ ] | Platform | Creator          | City      | Followers | Score  | Why         |
| [x] | IG       | @bayareabites    | Sunnyvale | 18.4k     | 87 Strong | Posts group-dinner content; most… |
|   (7) ▾ Locality .90  Niche .85  Engagement .80  Comments .75  Cadence .90  Brand fit .90 |
|        Recent posts: "Hot pot night with the crew" Nov 3 ↗ · "Cold-weather eats under $20" Oct 28 ↗ |
|        In campaigns: none yet                                                    |
| [x] | TikTok   | @southbayfood    | Sunnyvale | 52k       | 79 Good   | Strong local audience; posts…     |
| [x] | XHS      | @xiaochi.sv      | Sunnyvale | 9.1k      | Not scored | No reason available              |
| [ ] | IG       | @finalsweekeats  | Sunnyvale | 31k       | 72 Good   | In: Finals week (can't add)       |
+----------------------------------------------------------------------------------+
| (8) 5 selected   [Clear]                                  [Add to campaign →]    |
+----------------------------------------------------------------------------------+
```

1. Count of creators matching the filters.
2. Search by handle or name; debounced 250 ms.
3. Platform: Instagram, TikTok, Xiaohongshu (multi-select).
4. Minimum score 0–100, step 5, default 0 (nothing hidden unexpectedly). Active filters show as removable chips.
5. Sort: score (default), followers, recent activity.
7. **Expandable row** shows the six score parts with plain-language labels, the one-line reason, up to 3 recent posts (external links), and which active campaigns include this creator. Goal from the plan: the manager can explain any rank from the screen alone.
8. **Selection bar** (sticky at the bottom): count, how many selected items are hidden by current filters, **Clear**, **Add to campaign** (disabled at 0 selected). Cap is 25 (D8); at the cap, other checkboxes are disabled with an explanation.

Score badge text bands (shown as words, not color alone): 80+ Strong, 60–79 Good, 40–59 Mixed, below 40 Weak, `null` = "Not scored".

Phone: rows become cards (handle, platform, score badge, 2-line reason, checkbox); expansion is in place; the selection bar stays at the bottom above the tab bar.

Edge cases:
- `score` or any breakdown value `null` → show "—"; reason empty → "No reason available".
- A minimum score above 0 hides creators who are not scored.
- Very long handle/name → truncate with full text on hover/focus; never widen the page.
- Missing `profile_url` → no link rendered. Only `https://` profile and post links are rendered as links.
- Creator already in an active campaign at this location → shows the campaign name as a chip; blocked from being added twice.
- Selection persists across filter changes and is cleared on location change.
- The wireframe shows the moment before the campaign exists. `mocks/creators.json` shows the same creators afterwards, with `active_campaigns` filled in.

### 4.3 Add to campaign (dialog from Creators)

```text
+------------------------------------------------------+
| Add 5 creators to a campaign                     [x] |
| (1) Occasion *    [First cold week ▾]                |
|     Offer: Free appetizer for your table             |
| (2) Name          [First cold week · Sunnyvale     ] |
| (3) Dates         Start [Nov 20]   End [Dec 4]       |
| (4) Location      Sunnyvale (from header)            |
| (5) Languages     [x] English   [x] 中文             |
| (6) Creators      [@bayareabites ×] [@southbayfood ×]|
|                   [@xiaochi.sv ×] [@foodiesv ×]      |
|                   [@小吃日记 ×]                       |
|     ⚠ @finalsweekeats is already in "Finals week" and was removed. |
| (7) This will create 5 offer codes and 10 drafts.    |
|     Nothing is sent.                                 |
|                    [Cancel]   [Create campaign →]    |
+------------------------------------------------------+
```

1. Occasions from `GET /occasions` (birthdays, group nights, first cold week, finals ending, payday). Required. Shows the default offer.
2. Name prefilled, editable (3–80 characters).
3. Start must be today or later (in the location's time zone); end ≥ start and ≤ start + 90 days.
5. At least one language selected (P1; default both).
7. Count = creators × selected languages.
- **Create** is disabled while submitting and sends an `idempotency_key`, so a double-click or retry creates one campaign.
- On success: navigate to `/outreach?campaign_id=…` and show the generation progress bar.
- If some creators were skipped (server returns `skipped`), show which and why before navigating.
- Unknown outcome (network dropped after sending): look the campaign up in the list before allowing a retry.
- Closing with changes asks "Discard this campaign?".

### 4.4 Outreach Queue (`/outreach`) — manager

```text
+----------------------------------------------------------------------------------+
| Outreach                                                                         |
| (1) Campaign [First cold week · Sunnyvale ▾]        (2) Language [All ▾]         |
| (3) [Draft 3] [Approved 1] [Sent 1] [Replied 3] [Declined 1] [Rejected 1] [All 10] |
| (4) ⟳ Writing drafts… 8 of 10 done · 1 failed                                    |
| (5) ⓘ AI-written drafts. Nothing is sent automatically. Copy a message, send it  |
|     yourself on the platform, then mark it as sent.                              |
+----------------------------------------------------------------------------------+
| (6) ▾ @xiaochi.sv · Xiaohongshu · 9.1k · [Open profile ↗]                        |
|  +----------------------------------------------------------------------------+  |
|  | EN  [Draft]                                              (7) 111 / 1000    |  |
|  | Hi! We'd love to host you at Feng Hotpot Sunnyvale. Your offer:            |  |
|  | [site]/r/FENG-COLD-4TWE6V                                                  |  |
|  | No recent posts to reference  ·  (8) Offer link included ✓                 |  |
|  | (9) [Edit]  [Approve]  [Reject]                                            |  |
|  +----------------------------------------------------------------------------+  |
|   ▾ @foodiesv · TikTok · 14.2k                                                   |
|  +----------------------------------------------------------------------------+  |
|  | 中文 [Draft]   Draft couldn't be written.                    [Try again]   |  |
|  +----------------------------------------------------------------------------+  |
|   ▾ @小吃日记 · Xiaohongshu · 6.4k                                               |
|  +----------------------------------------------------------------------------+  |
|  | EN  [Draft]   ⟳ Writing this draft…                                        |  |
|  +----------------------------------------------------------------------------+  |
+----------------------------------------------------------------------------------+

EDIT MODE (the first card above, after the link was deleted)
|  | EN  [Editing]                                              63 / 1000       |
|  | +--------------------------------------------------------------------+     |
|  | | (textarea)                                                         |     |
|  | +--------------------------------------------------------------------+     |
|  | ⚠ This message doesn't include the offer link. Creators won't receive a code.|
|  | [Cancel]   [Save]   [Save and approve]                                      |
```

1. Campaign dropdown (from `GET /campaigns`); required. Without a campaign selected, show "Pick a campaign" with a link to Creators.
3. Status tabs with counts. A tab with 0 items shows an empty state naming the status.
4. Generation progress from the campaign's `generation` object. Polls every 3 s while running; after 60 s poll every 10 s; stop at 5 minutes with "Taking longer than expected. Drafts that finish will appear when you refresh." Drafts appear as they complete.
5. Always visible. The AI-written label is required.
6. Cards grouped by creator (collapsible). Cards that failed show "Draft couldn't be written" with **Try again** (P1).
7. Character count counts characters (Unicode code points), not bytes. Soft warning above 1000, hard stop at 2000 (assumption; confirm per platform).
8. Shows whether the text contains the offer link. If the manager edits the link out, a warning appears; approving still works after an explicit "Approve without link" confirmation.
9. Buttons depend on status:

| Status | Buttons |
|---|---|
| draft | Edit · Approve · Reject |
| approved | Copy message · Mark as sent… · Edit (returns to draft) · Reject |
| rejected | Reopen (shows the reject reason) |
| sent | Mark replied · Mark declined (text is read-only; shows "Sent {date}") |
| replied | Mark declined (read-only) |
| declined | none (read-only) |

Dialogs:
- **Reject**: optional reason, up to 280 characters.
- **Mark as sent**: "Did you send this message on {platform}? This can't be undone." [Cancel] [Yes, mark as sent].

Edge cases:
- Approve is blocked for empty text or text over the hard cap.
- Leaving the page with unsaved edits asks for confirmation. Edit → reload keeps the saved text and status (plan's "done when").
- Two people edit the same draft: the second save gets `STALE_VERSION`; show "Someone else changed this draft" with both versions and a choice to keep yours or theirs.
- Copy failure (permission denied): select the text and show "Press Ctrl/⌘+C".
- All draft and post text renders as plain text. Never as HTML or Markdown.
- A referenced post that no longer exists → hide its link; the card still renders.
- Chinese text uses a font stack with a CJK fallback; line breaks follow CJK rules.
- Counts on tabs refresh after every action and on window focus.
- Mobile: cards stack; action buttons wrap and stay at least 44 px tall.

### 4.5 Campaigns (`/campaigns`, `/campaigns/:id`) — manager

List:

```text
+----------------------------------------------------------------------------------+
| Campaigns                                              [+ New: pick creators →]  |
| Name                    Dates          Creators  Sent  Replied  First visits  Status |
| First cold week · SV    Nov 20–Dec 4   5         5     3        12            ● Active |
+----------------------------------------------------------------------------------+
```

Detail:

```text
+----------------------------------------------------------------------------------+
| ← Campaigns / First cold week · Sunnyvale                (1) [Fast-forward 2 weeks]* |
| Nov 20 – Dec 4 · Sunnyvale · Offer: Free appetizer for your table                |
| (2) First visits 12 | Return visits 3 | Repeat rate 25% | Cost / first visit $18.75 |
+----------------------------------------------------------------------------------+
| Creator       | Code (3)       | QR | Outreach | Post link (4)     | Post date | First | Return | Cost |
| @bayareabites | FENG-COLD-K7M2QD [copy] | [⬇] | Replied | creators.example/instagram/… [✎] | Nov 22 | 5 | 2 | $45 |
| @southbayfood | FENG-COLD-9QXA4R [copy] | [⬇] | Replied | creators.example/tiktok/… [✎] | Nov 23 | 4 | 1 | $45 |
| @xiaochi.sv   | FENG-COLD-4TWE6V [copy] | [⬇] | Sent    | [+ Add post link]  | —    | 0 | 0 | $45 |
+----------------------------------------------------------------------------------+
| (5) Row actions: Go to messages · Edit cost                                       |
+----------------------------------------------------------------------------------+
* demo tool: visible only to admin/demo role
```

1. **Fast-forward** (demo only): confirm dialog "Add simulated data for 14 days? Demo data is clearly labeled." Calls simulate; disabled while running; pressing again does not duplicate data (idempotent per campaign + seed).
2. Tiles show "—" for undefined values (e.g. cost per first visit with zero first visits). Tiles that include simulated data carry a **Simulated** badge.
3. Codes show with a copy button. The QR encodes `https://<site>/r/<CODE>` and is generated in the browser; **Download** saves a PNG named `<CODE>.png` (error correction M, quiet zone included).
4. **Post link**: inline edit. Must be `https://`, trimmed, at most 2048 characters. Domain is shown; links open in a new tab with `rel="noopener noreferrer"`. A domain outside the known list (instagram.com, tiktok.com, xiaohongshu.com, xhslink.com) gets a soft warning, not a block.
5. **Post date**: not more than 1 day in the future; a date before the campaign starts gets a warning.
- **Cost** is entered in dollars, stored in cents, default from the occasion (D4). Range $0–$10,000.
- Campaigns whose end date has passed are read-only and marked **Ended**.
- Simulated rows show a **Simulated** badge; they are never mixed silently with real ones.
- Sample numbers in the wireframe are illustrative (the table shows 3 of the campaign's 5 creators; totals cover all 5).
- The **Outreach** column shows the furthest status among a creator's messages: replied or declined, then sent, approved, draft; `rejected` only if nothing else applies. In the campaign list, **Sent** counts messages marked sent, replied or declined, and **Replied** counts replied.

### 4.6 Weekly Brief (`/brief`) — manager

```text
+----------------------------------------------------------------------------------+
| Weekly Brief · Sunnyvale        (1) [◀] Week of Nov 30–Dec 6 [▶]   Data through Dec 4 |
| (2) ● Includes demo data (53% of redemptions)           Updated Dec 5, 9:02 AM   |
+----------------------------------------------------------------------------------+
| (3) [First visits 12] [Return visits 3] [Repeat rate 25%] [Cost / first visit $18.75] |
|     [Response rate 80%] [Hours saved ≈ 3.5 (estimate)]                           |
+----------------------------------------------------------------------------------+
| (4) Two creators drove 80% of visits for the same $45 each. (headline, AI-written)|
|     • highlight • highlight                                                      |
| (5) Creators ranked by visits driven                                             |
|     @bayareabites   7 visits   $45   [View campaign →]                           |
| (6) Review signals: 68% positive · Theme: "Friday wait time" (4 mentions)        |
| (7) Recommended actions                                                          |
|     [1 Rebook @bayareabites…  Go to creator →] [2 Add Friday staffing…] [3 Follow up with @xiaochi.sv…] |
| (8) Numbers come from your records. The wording is written by AI.               |
+----------------------------------------------------------------------------------+
```

1. Week navigation (P1). P0 shows only the latest.
2. Shows the share of redemptions that are simulated and when the brief was generated. If the brief is older than 8 days: banner "This brief is out of date." Numbers are totals to date for the campaigns active that week, not weekly changes.
3. Metric tiles are rendered **only from `metrics`**, never parsed from text. `null` → "—". Hours saved is always labeled **estimate**.
4. Headline and highlights from `content`; rendered as plain text.
6. Review signals come from `reviews` (simulated in the demo and badged).
7. Exactly 3 actions normally; the UI renders whatever count it receives (0–5). A creator link is disabled if the creator no longer exists.
- No brief yet: "Your first brief arrives after the first full week." Demo role also sees **Generate brief**.
- If generation failed, show the last successful brief with its date.

### 4.7 Offer page (`/r/:code`) — public, phone-first

```text
OFFER                               SHOW TO STAFF (full screen)
+--------------------------+        +--------------------------+
| FENG HOTPOT   [EN | 中文]|        | ← Back                   |
| Sunnyvale                |        |  Show this to staff      |
|                          |        |                          |
| Free appetizer for       |        |  FENG-COLD-K7M2QD        |
| your table               |        |  (large, grouped)        |
| Recommended by           |        |  [QR]                    |
| @bayareabites            |        |  Valid at Sunnyvale      |
|                          |        |  until Dec 4             |
| Valid Nov 20 – Dec 4     |        +--------------------------+
| One per table · Dine-in  |
| [Restaurant address]     |
|  [ Show to staff ]       |
+--------------------------+
```

- A return offer uses the same layout with a "Welcome back" title.
- Language defaults to the browser language (`zh*` → 中文); the toggle persists for the visit.
- No sign-in, no cookies, no tracking scripts, no personal data collected. The page sets `noindex`.
- Content comes from `GET /public/offers/:code` only. It never receives internal data (scores, costs, campaign names).

| Status from API | What the diner sees |
|---|---|
| `active` | The offer |
| `not_started` | "This offer starts {date}." |
| `expired` | "This offer ended {date}." |
| unknown, voided or used | "This offer isn't available." (one generic message; no detail) |
| network error | "Can't load right now. Try again." The code from the URL is still shown on the Show-to-staff screen, with "Staff will check it". |
| `429` | "Please try again in a minute." |

Edge cases: code with lowercase, spaces or trailing slash is normalized; layout works at 320 px width and at large system font sizes; no horizontal scroll.

### 4.8 Redeem (`/redeem`) — staff, phone or tablet

```text
REDEEM                       RESULT (first visit)           RESULT (return visit)
+-----------------------+    +-----------------------+      +-----------------------+
| Redeem a code         |    | ✓ Redeemed            |      | ✓ Return offer used   |
| Sunnyvale             |    | First visit           |      | Welcome back          |
| Code                  |    | @bayareabites         |      | Free dessert          |
| [ FENG-____-____ ]    |    | Free appetizer        |      | [Redeem another]      |
| Party size  [−] 2 [+] |    | ── Return offer ──    |      +-----------------------+
| [      Redeem      ]  |    | Give the guest:       |
|                       |    | BACK-7H2K-QX9M  [QR]  |      ERROR
| Recent (last 10)      |    | Valid until Dec 27    |      +-----------------------+
| 6:42 PM FENG… ×2 [Void]|   | [Redeem another]      |      | ✕ Already used on     |
+-----------------------+    +-----------------------+      | Nov 27, 6:20 PM       |
                                                            +-----------------------+
```

- **Location** is fixed from the staff profile (not typed). Staff can't redeem for other locations.
- **Code input** is uppercased, trimmed, accepts missing hyphens and spaces. Codes use an alphabet with no look-alike characters (no `0/O`, `1/I/L`), so most typos are caught.
- **Party size**: whole number 1–50, default 2.
- **Visit number is not entered.** It comes from the code type.
- **Redeem** disables while sending and sends an `idempotency_key`. A retry after a dropped connection can't create a second redemption.
- If the network fails after tapping, show "We couldn't confirm this went through." and point to **Recent**; do not claim success or failure.
- The **return offer** screen stays until dismissed. **Recent** entries for first visits have **Show return offer again**.
- **Void** (P1): staff can void a redemption made in the last 15 minutes with a confirm step. A first-visit redemption can't be voided once its return code was used. Voiding a return visit makes its return code usable again if it has not expired. If staff void a first visit because of a typo, they redeem the creator code again; that issues a new return code and the old one stops working.
- Shared device: sign out automatically after 15 minutes of inactivity; no codes stored in browser storage.

| API error code | Message to staff |
|---|---|
| `CODE_INVALID` | "We don't recognize that code. Check the spelling." |
| `CODE_NOT_STARTED` | "This offer starts {date}." |
| `CODE_EXPIRED` | "This offer ended {date}." |
| `CODE_ALREADY_USED` | "Already used on {date} at {time}." |
| `CODE_WRONG_LOCATION` | "This code is valid at {location} only." |
| `CODE_VOIDED` | "This code was cancelled." |
| `RATE_LIMITED` | "Too many tries. Wait {n} seconds." |
| network | "No connection. Nothing was recorded." |

---

## 5. API contract (for Shinjini)

Transport is open (D6): endpoints below can be Supabase Edge Functions, RPC, or a small service. Whatever the choice, the browser only ever holds the **publishable key and the user's session token**.

### 5.1 Conventions

- JSON over HTTPS. Header: `Authorization: Bearer <session token>` (except `/public/*`).
- Paths in this document omit the `/api` prefix used in the team plan (`GET /creators` here is `GET /api/creators` there).
- IDs are UUID strings. Timestamps are ISO-8601 UTC. Dates (`start_date`, `end_date`, `post_date`) are `YYYY-MM-DD` interpreted in the **location's time zone**; a campaign ends at 23:59:59 local time on `end_date`. Money is **integer cents**.
- Lists use cursor pagination: `?limit=50&cursor=…`, response `{ "items": [...], "next_cursor": null }`. Default 50, max 100.
- Writes to `outreach` and `campaign_creators` include `version` (integer). Mismatch → `409 STALE_VERSION`.
- Creating records accepts `idempotency_key` (UUID, valid 24 h). Same key → same result, no duplicate.
- Any row from simulated data has `is_simulated: true`.

Error shape (all errors):

```json
{
  "error": {
    "code": "VALIDATION_FAILED",
    "message": "Human-readable summary",
    "fields": { "party_size": "Must be between 1 and 50" },
    "request_id": "req_8f2a"
  }
}
```

| HTTP | `code` examples |
|---|---|
| 401 | `UNAUTHENTICATED` |
| 403 | `FORBIDDEN` |
| 404 | `NOT_FOUND`, `OFFER_UNAVAILABLE` |
| 409 | `STALE_VERSION`, `INVALID_TRANSITION`, `DUPLICATE` |
| 422 | `VALIDATION_FAILED`, `CODE_INVALID`, `CODE_EXPIRED`, `CODE_NOT_STARTED`, `CODE_ALREADY_USED`, `CODE_WRONG_LOCATION`, `CODE_VOIDED` |
| 429 | `RATE_LIMITED` (with `retry_after` seconds) |
| 5xx | `INTERNAL` (never include internal details) |

Domain errors can also include a `details` object (for example `used_at`, `starts`, `ended`, `valid_location`) so the UI can fill in its message. `STALE_VERSION` includes `current`, the latest version of the item.

### 5.2 Endpoints at a glance

| Priority | Method + path | Role | Purpose |
|---|---|---|---|
| P0 | `GET /me` | any signed-in | Role, locations, feature flags |
| P0 | `GET /creators` | manager | Ranked creators |
| P0 | `GET /occasions` | manager | Occasion list with offers |
| P0 | `GET /campaigns` | manager | Campaign list |
| P0 | `POST /campaigns` | manager | Create campaign + codes + start drafts |
| P0 | `GET /campaigns/:id` | manager | Detail, results, generation progress |
| P0 | `PATCH /campaigns/:id/creators/:ccid` | manager | Post link, post date, cost |
| P0 | `GET /outreach` | manager | Draft cards |
| P0 | `PATCH /outreach/:id` | manager | Edit and status actions |
| P0 | `GET /public/offers/:code` | public | Offer page data |
| P0 | `POST /redemptions` | staff, manager | Redeem a code |
| P0 | `GET /briefs/latest` | manager | Latest brief |
| P0-demo | `POST /simulate` | admin, demo mode only | Fast-forward data (same endpoint as the team plan) |
| P0-demo | `POST /briefs/generate` | admin, demo mode only | Rebuild brief after simulate |
| P1 | `GET /summary` | manager | Nav badge counts |
| P1 | `POST /outreach/:id/regenerate` | manager | Retry a failed or unwanted draft |
| P1 | `GET /redemptions/recent` | staff, manager | Last 10 for this location |
| P1 | `GET /redemptions/:id` | staff, manager | Re-show the return offer |
| P1 | `POST /redemptions/:id/void` | staff (15 min), manager | Void a mistake |
| P1 | `GET /briefs` | manager | Past weeks |
| P2 | `POST /demo/reset` | admin | Reset demo data |

### 5.3 Key payloads

**`GET /me`**
```json
{ "user_id": "u_1", "email": "manager@example.com", "role": "manager",
  "locations": ["sunnyvale"], "features": { "demo_tools": false } }
```

**`GET /creators?location=sunnyvale&platform=instagram&min_score=60&q=&sort=score_desc&limit=50`** — item:
```json
{
  "id": "c_1", "handle": "@bayareabites", "platform": "instagram",
  "profile_url": "https://creators.example/instagram/bayareabites",
  "city": "Sunnyvale", "followers": 18400,
  "score": 87, "score_reason": "Posts group-dinner content; most followers are in the Bay Area",
  "score_breakdown": { "locality": 0.90, "niche": 0.85, "engagement": 0.80,
                       "comment_quality": 0.75, "cadence": 0.90, "brand_fit": 0.90 },
  "scored_at": "2026-11-17T20:00:00Z",
  "recent_posts": [ { "id": "p_1", "url": "https://creators.example/instagram/bayareabites/p/1", "excerpt": "Hot pot night with the crew", "posted_at": "2026-11-03T02:10:00Z" } ],
  "active_campaigns": [ { "id": "cmp_1", "name": "First cold week · Sunnyvale" } ],
  "source": "hand-collected 2026-11-16"
}
```
`score`, `score_reason`, `score_breakdown` may be `null` (not yet scored). `score_breakdown` values are 0–1 or `null`. The list response also includes `total`, the count of creators matching the filters.

**`POST /campaigns`**
```json
{ "name": "First cold week · Sunnyvale", "occasion_id": "occ_cold_week",
  "location": "sunnyvale", "start_date": "2026-11-20", "end_date": "2026-12-04",
  "creator_ids": ["c_1", "c_2", "c_3", "c_5", "c_7"], "languages": ["en", "zh"],
  "idempotency_key": "5c7e…" }
```
Response `201`:
```json
{ "campaign": { "id": "cmp_1", "name": "First cold week · Sunnyvale", "status": "active",
                "generation": { "status": "running", "total": 10, "done": 0, "failed": 0 } },
  "skipped": [] }
```
`skipped` lists creators the server left out, for example because another campaign took them in the meantime, each with a `reason` such as `ALREADY_IN_ACTIVE_CAMPAIGN`. Rules: 1–25 creators; at least one language; creators already in an active campaign at the same location are skipped, not failed; codes are created **before** drafts so drafts can include the offer link.

**`GET /campaigns/:id`**
```json
{
  "id": "cmp_1", "name": "First cold week · Sunnyvale", "occasion": { "id": "occ_cold_week", "name": "First cold week" },
  "location": "sunnyvale", "start_date": "2026-11-20", "end_date": "2026-12-04", "status": "active",
  "offer": { "title": "Free appetizer for your table", "value_cents": 4500 },
  "generation": { "status": "running", "total": 10, "done": 8, "failed": 1 },
  "totals": { "first_visits": 12, "return_visits": 3, "cost_cents": 22500, "includes_simulated": true },
  "creators": [ {
      "campaign_creator_id": "cc_1", "version": 3,
      "creator": { "id": "c_1", "handle": "@bayareabites", "platform": "instagram", "profile_url": "https://…" },
      "code": { "value": "FENG-COLD-K7M2QD", "url": "https://creator-loop.example/r/FENG-COLD-K7M2QD", "expires_at": "2026-12-05T07:59:59Z" },
      "outreach_summary": { "draft": 0, "approved": 1, "sent": 0, "replied": 1, "declined": 0, "rejected": 0 },
      "post_url": "https://creators.example/instagram/bayareabites/p/9", "post_date": "2026-11-22",
      "cost_cents": 4500, "first_visits": 5, "return_visits": 2, "is_simulated": false } ]
}
```
`generation.status`: `none` | `running` | `done` | `failed` | `partial`.

**`PATCH /campaigns/:id/creators/:ccid`** → body `{ "post_url": "https://…", "post_date": "2026-11-22", "cost_cents": 4500, "version": 3 }`. Any field optional; returns the updated row. Validation: `post_url` https only, ≤ 2048 chars; `post_date` ≤ today + 1 day; `cost_cents` 0–1,000,000.

**`GET /outreach?campaign_id=cmp_1&status=draft&lang=en&limit=50`** — item:
```json
{
  "id": "o_5", "version": 5, "campaign_id": "cmp_1", "campaign_creator_id": "cc_3",
  "creator": { "id": "c_3", "handle": "@xiaochi.sv", "platform": "xiaohongshu",
               "profile_url": "https://creators.example/xiaohongshu/xiaochi.sv", "followers": 9100 },
  "platform": "xiaohongshu", "lang": "en",
  "draft_text": "Hi! We'd love to host you at Feng Hotpot Sunnyvale. Your offer: https://creator-loop.example/r/FENG-COLD-4TWE6V",
  "edited_text": null,
  "current_text": "Hi! We'd love to host you at Feng Hotpot Sunnyvale. Your offer: https://creator-loop.example/r/FENG-COLD-4TWE6V",
  "status": "draft",
  "has_offer_link": true,
  "referenced_posts": [],
  "generation_status": "ready",
  "reject_reason": null, "approver": null, "decided_at": null,
  "sent_at": null, "replied_at": null, "updated_at": "2026-11-18T00:45:00Z",
  "is_simulated": false
}
```
`current_text` = `edited_text` if present, else `draft_text`. `generation_status`: `pending` | `ready` | `failed`.

**`PATCH /outreach/:id`**
```json
{ "action": "edit", "edited_text": "Hi Amy! …", "version": 4 }
{ "action": "approve", "version": 5 }
{ "action": "reject", "reason": "Too formal", "version": 4 }
{ "action": "reopen" | "mark_sent" | "mark_replied" | "mark_declined", "version": 6 }
```
Returns the updated item. Server enforces: transition table (§3.2); text 1–2000 characters on `edit` and `approve`; `reason` ≤ 280; recomputes `has_offer_link`; sets `approver`/`decided_at`/`sent_at`/`replied_at`; increments `version`; writes an `audit_log` entry.

**`GET /public/offers/:code`** (no auth, rate-limited)
```json
{ "status": "active",
  "offer": { "title": { "en": "Free appetizer for your table", "zh": "…" },
             "details": { "en": "One per table · Dine-in", "zh": "…" },
             "kind": "creator", "starts": "2026-11-20", "ends": "2026-12-04" },
  "restaurant": { "name": "Feng Hotpot", "location_name": "Sunnyvale", "address": "…" },
  "recommended_by": "@bayareabites" }
```
`status`: `active` | `not_started` | `expired`. Unknown, voided or used codes return `404 OFFER_UNAVAILABLE` with an identical body. Never return scores, costs, ids or campaign names.

**`POST /redemptions`**
```json
{ "code": "FENG-COLD-K7M2QD", "location": "sunnyvale", "party_size": 2, "idempotency_key": "9a1b…" }
```
Response `201`:
```json
{ "redemption": { "id": "r_3", "type": "first", "visit_number": 1,
                  "redeemed_at": "2026-11-28T02:42:00Z", "location": "sunnyvale",
                  "party_size": 2, "creator_handle": "@bayareabites",
                  "offer_title": "Free appetizer for your table" },
  "return_offer": { "code": "BACK-7H2K-QX9M", "url": "https://creator-loop.example/r/BACK-7H2K-QX9M",
                    "title": "Welcome back: free dessert", "expires_at": "2026-12-28T07:59:59Z" } }
```
For a return code, `type` is `return`, `visit_number` is 2, and `return_offer` is `null`. The server must make redemption **atomic** (a single-use code can be used once even under concurrent requests). Location comes from the user's profile; a mismatch with `location` → `CODE_WRONG_LOCATION`.

**`GET /briefs/latest?location=sunnyvale`**
```json
{
  "id": "b_1", "week_of": "2026-11-30", "location": "sunnyvale",
  "generated_at": "2026-12-05T17:02:00Z", "data_through": "2026-12-04",
  "metrics": { "first_visits": 12, "return_visits": 3, "repeat_visit_rate": 0.25,
               "cost_per_first_visit_cents": 1875, "response_rate": 0.8,
               "sent_count": 5, "response_count": 4, "hours_saved_estimate": 3.5,
               "simulated_share": 0.53 },
  "top_creators": [ { "creator_id": "c_1", "handle": "@bayareabites",
                      "visits": 7, "cost_cents": 4500, "campaign_id": "cmp_1" } ],
  "review_summary": { "positive_share": 0.68, "is_simulated": true,
                      "themes": [ { "label": "Friday wait time", "count": 4 } ] },
  "content": { "headline": "…", "highlights": ["…"], "review_signals": ["…"],
               "actions": [ { "title": "…", "detail": "…", "creator_id": "c_1" } ] }
}
```
**Numbers come from SQL; the model writes only `content` wording.** Ratios are `null` (not 0 or NaN) when the denominator is 0.

**Other payloads** (full examples are in `mocks/`)

- `GET /occasions` → `{ "items": [ { "id", "name", "offer_title": {en, zh}, "offer_details": {en, zh}, "default_cost_cents" } ] }`
- `GET /campaigns` → `{ "items": [ { "id", "name", "occasion": {id, name}, "location", "start_date", "end_date", "status": "active" or "ended", "creator_count", "outreach_counts": {draft, approved, sent, replied, declined, rejected}, "first_visits", "return_visits", "generation": {status, total, done, failed}, "is_simulated" } ], "next_cursor" }`
- `GET /summary?location=` → `{ "location", "drafts_waiting", "approved_unsent", "active_campaigns", "redemptions_today" }`
- `GET /redemptions/recent` → `{ "location", "items": [ { "id", "code", "type", "party_size", "redeemed_at", "voided_at", "voided_reason", "can_void_until", "has_return_offer" } ] }`
- `GET /redemptions/:id` → same shape as the `POST /redemptions` response, so a first visit's return offer can be shown again.
- `POST /redemptions/:id/void` with `{ "reason": "Wrong party size" }` → the updated recent-redemption item. Allowed for 15 minutes; `409 INVALID_TRANSITION` if the return code was already used. Voiding a return visit restores that return code if it has not expired.
- `POST /simulate` with `{ "campaign_id": "cmp_1", "days": 14 }` → `{ "campaign_id", "days", "added": {redemptions, reviews}, "brief": {status} }`. Repeating it does not add duplicate rows.
- `POST /outreach/:id/regenerate` with `{ "version": 3 }` → the updated outreach item, with `generation_status` back to `pending`. Rewriting replaces the AI draft and clears `edited_text`, so the UI confirms first.
- `POST /briefs/generate` with `{ "location": "sunnyvale" }` → `202` with `{ "status": "generating" }`.

### 5.4 Metric definitions

| Metric | Definition |
|---|---|
| First visits | Non-voided redemptions of type `first`, from each campaign's start through `data_through` |
| Return visits | Non-voided redemptions of type `return`, from each campaign's start through `data_through` |
| Repeat visit rate | Return visits ÷ first visits. Because each return code is single-use and tied to one first visit, this is the share of first-time guests who have come back. `null` if no first visits. |
| Cost per first visit | Sum of the campaign creators' `cost_cents` ÷ first visits. `null` if no first visits. |
| Response rate | Messages that got a response (status `replied` or `declined`) ÷ messages sent (status `sent`, `replied` or `declined`). `null` if none sent. |
| Hours saved | Estimate = counts × per-action minutes in config. Always labeled estimate. |

Brief numbers are totals to date for the campaigns active that week, not weekly changes. Weekly changes are out of scope for v1.

### 5.5 Rate limits and limits (starting values, adjust as needed)

| Item | Limit |
|---|---|
| `GET /public/offers/:code` | 30 requests/min per IP; after 5 invalid codes in a minute, 5-minute block |
| `POST /redemptions` | 20/min per user; same code-guess limit as above |
| `POST /campaigns` | 10/hour per user |
| Draft generation | Concurrency cap on AI calls; 25 creators × 2 languages max per campaign |
| Message text | 1–2000 chars (UI warns above 1000) |
| Reject reason | ≤ 280 chars |
| Campaign name | 3–80 chars |
| Party size | 1–50 |
| URLs | https only, ≤ 2048 chars |

---

## 6. Database changes (for Shinjini)

Relative to the 9 tables in the team plan (`creators`, `creator_posts`, `brand_corpus`, `campaigns`, `outreach`, `offer_codes`, `redemptions`, `reviews`, `briefs`). All timestamps are `timestamptz`; all tables get `created_at` and, where edited, `updated_at`.

| Table | Change |
|---|---|
| `profiles` (new) | `user_id`, `role` (`manager`/`staff`/`admin`), `locations text[]`, `display_name` |
| `creators` | add `profile_url` and `scored_at`. The API's `recent_posts` come from `creator_posts` (caption shortened to `excerpt`) |
| `occasions` (new) | `id`, `name`, `offer_title_en/zh`, `offer_details_en/zh`, `default_cost_cents`, `return_offer_title_en/zh`, `return_valid_days` |
| `campaigns` | replace the plan's `occasion` text with `occasion_id`; add `location` (enum), `created_by`; `start_date`/`end_date` as dates in location time zone; `generation_status`, `generation_total/done/failed`; `is_simulated` |
| `campaign_creators` (new) | `id`, `campaign_id`, `creator_id`, `cost_cents`, `post_url`, `post_date`, `version`; **unique** `(campaign_id, creator_id)` |
| `outreach` | add `campaign_creator_id`; status enum `draft, approved, rejected, sent, replied, declined`; `version`, `sent_at`, `replied_at`, `reject_reason`, `has_offer_link`, `generation_status`, `generation_error`, `referenced_post_ids uuid[]`, `updated_at`; **unique** `(campaign_creator_id, platform, lang)` |
| `offer_codes` | add `kind` (`creator`/`return`), `campaign_creator_id`, `parent_redemption_id` (return codes), `location`, `starts_at`, `expires_at`, `max_uses` (null for creator, 1 for return), `uses`, `status` (`active`/`voided`); **unique** on normalized `code` |
| `redemptions` | add `offer_code_id`, `type` (`first`/`return`), `redeemed_by`, `idempotency_key` (**unique**), `voided_at`, `voided_reason`; `party_size` check 1–50; derive `visit_number` (do not accept from the client) |
| `reviews` | no change (the team plan already has `location` and `is_simulated`) |
| `briefs` | add `location`, `data_through` |
| `audit_log` (new) | `id`, `actor_id`, `action`, `entity`, `entity_id`, `at`, `meta jsonb` |

Notes:
- API names versus the plan's columns: `draft_text` is the plan's `draft`; `visit_number` stays a column but is set by the server.
- The audit log supports the plan's evaluation metric "draft acceptance rate" (approved ÷ approved plus rejected).
- Add `is_simulated boolean not null default false` to every table that simulation writes to. Aggregates must be computed with and without simulated rows so the UI can label them.
- **Code format:** readable prefix + random part from an alphabet without look-alikes, e.g. `FENG-COLD-` + 6 random characters; return codes `BACK-` + 8. Compare case-insensitively after stripping spaces and hyphens. The plan's example (`FENG-COLD-AMY7`) is too guessable; don't derive codes from creator names.
- Single-use enforcement: update `uses` with a conditional atomic update (`... where uses < max_uses`), or a unique constraint on `parent_redemption_id`.
- Voiding a first-visit redemption voids its unused return code; it is blocked if the return code was already used. Voiding a return-visit redemption sets that code's `uses` back to 0 if it has not expired.
- Occasions live in the `occasions` table, seeded with the plan's five. Copy the occasion's offer into `offer_codes.offer` when a campaign is created, so editing an occasion later does not change live offers. Add `is_active` to hide old occasions instead of deleting them.
- Audit events: `campaign.create`, `outreach.approve`, `outreach.reject`, `outreach.mark_sent`, `outreach.mark_replied`, `redemption.create`, `redemption.void`, `simulate.run`, `brief.generate`.
- AI draft generation: treat creator captions as **untrusted data** (they could contain instructions). Wrap them in clear delimiters, validate structured output, only allow referenced post ids that exist for that creator, strip any URL except the offer link, and keep numbers/claims out of drafts that aren't in the offer. Drafts should state the offer plainly and not pressure for positive coverage; remind creators to disclose per platform rules (confirm wording with Aolin/Sherry).

---

## 7. Security

This section lists what the frontend does and what it depends on the backend to do. No document can make a system "unbreakable"; this reduces common risks, and §8 gives tests to find the rest.

### 7.1 Frontend rules

| # | Rule | Why |
|---|---|---|
| F1 | Sign-in required for every manager and staff route; render nothing private until the session is confirmed. | Stops casual access; backend still enforces. |
| F2 | The browser holds only the Supabase URL and **publishable** key plus the user's session token. Never the secret/service-role key or any AI key. Env vars with `VITE_`/`NEXT_PUBLIC_` prefixes are public by design. | Anything in browser code is visible to everyone. |
| F3 | Render all text from creators, posts, drafts and AI as **plain text**. No `dangerouslySetInnerHTML`, no Markdown-to-HTML on drafts or briefs. | Prevents XSS from scraped or AI text. |
| F4 | Only render a link when the URL parses and the protocol is `https:`. Open external links in a new tab with `rel="noopener noreferrer"`. | Blocks `javascript:` links and tab-napping. |
| F5 | Don't load creator avatars or images from external hosts. Use initials and platform icons. | Avoids tracking pixels and mixed content. |
| F6 | Set security headers at the host if it allows: CSP (`script-src 'self'`, `connect-src` only the API host), `frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`. | Defense in depth. |
| F7 | Session token goes in the `Authorization` header (not a cookie). If cookies are used instead, add `SameSite` and CSRF protection. | Avoids CSRF. |
| F8 | `next`/redirect parameters accepted only if they start with `/` and not `//`. | Blocks open redirects. |
| F9 | Public page has no cookies, no analytics, no PII, `noindex`, and no requests except its own API. | Privacy and data minimization. |
| F10 | Disable submit buttons while a request is in flight and send `idempotency_key` on creates and redemptions. | Prevents duplicates. |
| F11 | Client validation mirrors server limits for friendly errors; **the server is authoritative**. | Client checks are bypassable. |
| F12 | Staff devices sign out after 15 minutes of inactivity; no codes or tokens in `localStorage` beyond the auth library's own session. | Shared tablets. |
| F13 | Show demo tools only when `GET /me` says `features.demo_tools`. Hiding is cosmetic; the backend must refuse. | Prevents misleading buttons. |
| F14 | Errors display message + `request_id` only. No `console.log` of tokens, codes or personal data in production builds. | Information leakage. |
| F15 | Commit `package-lock.json`; pin dependency versions; run `npm audit` before the demo; add no third-party scripts in v1. | Supply-chain risk. |
| F16 | Label AI output ("AI-written draft") and never auto-send. | Honesty and brand safety. |

### 7.2 What the frontend needs from the backend

| # | Requirement |
|---|---|
| B1 | Row Level Security on every table. Managers access only their locations; staff can call only redemption endpoints; anon reaches only the public offer endpoint. No direct table access for anon. |
| B2 | Server-side role checks on every endpoint (including simulate, generate, void). Demo endpoints return 404 unless demo mode is on. |
| B3 | Server-side validation of every field in §5 and the transition table in §3.2. |
| B4 | Atomic single-use redemption and idempotency-key handling. |
| B5 | Rate limiting and lockout per §5.5; identical responses for unknown, voided and used codes. |
| B6 | High-entropy codes (§6). |
| B7 | CORS restricted to the site origin. |
| B8 | Secrets only in server environment variables; none in the repo (`.env` is already gitignored). |
| B9 | Audit log for sensitive actions; never log personal data. |
| B10 | AI safety: untrusted-input handling, schema-validated output, allowlisted URLs (§6). |

### 7.3 Privacy

- No personal data about diners is collected in v1. Return codes are anonymous.
- If a later version captures phone or email, it needs explicit consent text, a stated purpose and a deletion path before it ships (D2).
- Creator data is public information gathered by hand (per the team plan); don't expose raw scraped records beyond what the Creators page shows.

---

## 8. Edge cases and QA checklist

Tick each before the 2 pm demo freeze. Items marked ★ are the ones most likely to break a live demo.

### 8.1 Everywhere
- [ ] ★ Every route works on reload, deep link, and Back/Forward.
- [ ] ★ Signed-out user opening a manager route is sent to login and returned to the same page afterwards.
- [ ] Session expires during an edit: the unsaved text is kept in memory and the user is prompted to sign in again.
- [ ] Every screen has loading, empty and error states (§4.0).
- [ ] Throttle to slow 3G: spinners appear, nothing double-submits.
- [ ] Offline: banner appears; no action reports success.
- [ ] Two tabs open: an action in one shows in the other after refocus.
- [ ] Dates and times correct per location, including month ends and daylight-saving changes.
- [ ] Very long names, emoji, Chinese text: truncate or wrap, never break the layout.
- [ ] Numbers: 0, 999, 1,000, 12,345, 1.2M format correctly; `null` shows "—"; no NaN or Infinity anywhere.
- [ ] 320 px phone width, landscape, 200% zoom, large system font: no horizontal scroll.
- [ ] Keyboard only: every flow completes; focus is visible; dialogs trap focus, close with Esc, and return focus.
- [ ] Screen reader: statuses announced (`aria-live`), controls named, table headers present.
- [ ] Contrast at least 4.5:1; status never conveyed by color alone.

### 8.2 Creators and campaign dialog
- [ ] 0, 1 and 500 results; filter combinations; reset.
- [ ] `score` null, partial `score_breakdown`, empty reason.
- [ ] Selection survives filter changes and shows "hidden by filters"; cap of 25 enforced.
- [ ] Add-to-campaign disabled at 0 selected.
- [ ] Creator already in an active campaign is blocked or skipped with an explanation.
- [ ] ★ Double-click **Create campaign** creates exactly one campaign.
- [ ] Dates: start in the past, end before start, range over 90 days are rejected with clear messages.
- [ ] Network drops during create: no duplicate on retry; list is checked first.
- [ ] Partial skip result is shown before navigating.

### 8.3 Outreach
- [ ] ★ Generation states: pending, running, partial, failed (with retry), 5-minute timeout message.
- [ ] ★ Edit → reload keeps edited text and status.
- [ ] Leaving with unsaved edits asks first.
- [ ] Concurrent edit gives the stale-version message with both versions.
- [ ] Approve blocked for empty or over-cap text; soft warning above 1000.
- [ ] Editing an approved draft returns it to draft and says why.
- [ ] Removing the offer link triggers the warning and the "approve without link" confirmation.
- [ ] Copy works; on failure, text is selected with instructions.
- [ ] **Mark as sent** requires confirmation, then locks the text and shows the time.
- [ ] Only allowed actions are shown for each status; forced invalid actions return a friendly message and refresh the card.
- [ ] Tab counts update after each action and on focus.
- [ ] Script/HTML in a draft or caption displays as inert text.
- [ ] Missing referenced post doesn't break the card.
- [ ] Character count is correct for Chinese and emoji.

### 8.4 Campaigns
- [ ] Zero redemptions shows zeros or "—", never NaN.
- [ ] Post link: `javascript:`, `http://`, no scheme, 2049 characters, and spaces are rejected or trimmed; valid https saves and opens safely.
- [ ] Post date more than 1 day ahead is rejected; before campaign start warns.
- [ ] QR downloads as `<CODE>.png` and scans correctly from a phone at normal print size.
- [ ] Fast-forward asks for confirmation, can't be double-clicked, is idempotent, and badges simulated data; hidden for non-demo users.
- [ ] Ended campaigns are read-only.

### 8.5 Weekly Brief
- [ ] No brief: empty state. Brief older than 8 days: out-of-date banner.
- [ ] `null` metrics show "—".
- [ ] Simulated share and badge appear when applicable.
- [ ] 0–5 actions render; deleted-creator links are disabled.
- [ ] HTML in AI text displays as text.
- [ ] After fast-forward + generate, tiles change and the badge shows.

### 8.6 Offer page and redeem
- [ ] ★ Offer page states: active, not started, expired, unavailable, offline, slow, rate-limited.
- [ ] Lowercase, spaces and trailing slash in the URL are normalized.
- [ ] No console errors; no requests to other hosts; `noindex` present.
- [ ] EN/中文 toggle works; Chinese font displays correctly; works on iPhone Safari and Android Chrome.
- [ ] ★ Redeem: lowercase, spaces, missing hyphens accepted.
- [ ] Party size 0, 51, 2.5, blank rejected.
- [ ] ★ Double-tap **Redeem** creates one redemption; a dropped connection shows "couldn't confirm" and a retry is safe.
- [ ] Wrong location, expired, already used, voided each show their own message.
- [ ] First visit shows the return offer; **Show return offer again** works from Recent.
- [ ] ★ Return code can be redeemed once; a second try says already used.
- [ ] Void inside 15 minutes works; after the return code was used it is blocked.
- [ ] Staff session auto-signs out after 15 minutes idle.

### 8.7 Security checks
- [ ] Search the production build for `service_role`, `sb_secret`, and any AI key: none found.
- [ ] Network tab shows only the publishable key and the user token.
- [ ] Staff token on a manager endpoint → 403; no token → 401; a different location's ids → 403/404.
- [ ] XSS probes (`<img src=x onerror=alert(1)>`) in caption, draft, handle, post URL and reason are inert.
- [ ] `javascript:` in profile or post URL is never rendered as a link.
- [ ] Guessing codes triggers 429 after the limit.
- [ ] Replaying the same `idempotency_key` returns the same result with no duplicate.
- [ ] Simulate/generate with a non-admin user → 403; with demo mode off → 404.
- [ ] CORS rejects other origins.
- [ ] `npm audit` shows no high or critical production issues.

---

## 9. Responsive, accessibility and language

- **Breakpoints:** phone < 640 px, tablet 640–1023, desktop ≥ 1024. Tables become cards on phone. Tap targets ≥ 44 px.
- **Theme:** light theme only in v1 (fewer states to test).
- **Accessibility:** semantic headings and landmarks, labeled form fields, visible focus, `aria-live` for toasts and generation progress, dialogs with focus trap, respects reduced-motion.
- **Language:** dashboard UI strings in English. Message drafts in EN/ZH. Public offer page bilingual. Dates use the location's time zone and the viewer's language format.
- **Fonts:** system font stack with a CJK fallback (e.g. Noto Sans SC / PingFang SC / Microsoft YaHei).

---

## 10. Mock data and test fixtures

Keep one JSON file per endpoint in `/mocks`, matching §5 exactly, with `is_simulated` set where relevant. Include these edge fixtures so the UI is tested against them before the real backend exists:

| File | Must include |
|---|---|
| `creators.json` | A normal creator; `score: null`; partial breakdown; 60-character handle; Chinese-name creator on Xiaohongshu; creator already in an active campaign; missing `profile_url`; a scraped caption containing HTML |
| `outreach.json` | One item in **each** status; one `generation_status: failed`; one `pending`; one with `has_offer_link: false`; Chinese text; a referenced post whose excerpt contains HTML (must show as plain text); empty `referenced_posts` |
| `campaigns_list.json`, `campaign_detail.json` | Active, ended, 0 redemptions, with simulated data; `generation` in running and partial |
| `public_offer_*.json` | One each for active, not_started, expired, and the 404 body |
| `redemption_*.json`, `redemptions_recent.json` | Success (first), success (return), one body for each error code, and a recent list with a voided item |
| `brief.json`, `brief_empty_metrics.json` | Normal; all-null ratios; 0 actions. Add variants with 5 actions and a 100% simulated share when testing the layout |
| `errors.json` | 401, 403, 409 STALE_VERSION (with current item), 422 with `fields`, 429, 500 |

Rule: when a payload shape changes, update the mock and this spec in the same commit, and announce it in team chat. The files are in `mocks/` (see `mocks/README.md`); where this table and the files differ, the files are the current version.

---

## 11. Assumptions, open questions, out of scope

**Assumptions** (change if wrong)
- Sunnyvale is the demo location; Philadelphia and Rockville exist as options.
- One return offer per first visit; no visit 3+.
- Message limits (1000 soft, 2000 hard) are guesses; platform DM limits should be checked.
- 25 creators per campaign and the rate limits in §5.5 are starting values.

**Open questions for Sherry Gu / Aolin**
- Who uses the tool daily, and on what device?
- How does the restaurant track redemptions today? Would staff log codes?
- What is the creator offer, and what is the return offer?
- Are creators asked to disclose the free meal, and what wording should drafts use?
- Do any creators need to be excluded (existing partners, conflicts)?

**Out of scope for v1**
- Sending messages automatically or reading replies from platforms.
- Collecting diner phone/email.
- Payments, POS integration, loyalty points.
- Live scraping or platform APIs (hand-collected seed data only).
- Multi-user editing presence, notifications, and dark theme.
