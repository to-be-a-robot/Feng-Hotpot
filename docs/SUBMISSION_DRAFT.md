# Feng Hotpot Creator Loop: written submission (draft)

> Draft by the backend lane. Numbers marked **[fill]** come from the final run (evaluation and demo data); don't submit them as written.

## The problem

Feng Hotpot's creator marketing is manual. Managers find creators by scrolling, judge them by follower count, send generic messages, comp meals, and then can't tell which collaborations brought anyone through the door. Without that link, the team can't decide which creators to work with again or what each visit cost.

## What we built

A loop that connects each creator collaboration to real visits:

1. **Discover and rank.** Creators near each location (Sunnyvale, Philadelphia, Rockville) on Instagram, TikTok and Xiaohongshu get a 0–100 score from six explainable parts: local audience, food fit (embeddings against Feng Hotpot's own posts and menu), engagement, comment quality, posting rhythm, and a Claude brand-fit check. Each creator gets a one-line reason a manager can read and overrule. Weights were set by our product lead.
2. **Reach out.** Claude drafts a personal message per creator, platform and language (English and Chinese) that references the creator's own recent posts and the occasion. A manager edits and approves every draft; **nothing is sent automatically**.
3. **Track.** Each creator gets a unique offer code and QR link. Staff redeem it at the table, which records a **first visit** and issues a **single-use return code**. When the guest comes back with it, that **return visit** is credited to the same creator. Repeat visits are measured without collecting any diner's personal data.
4. **Learn.** A weekly brief joins campaigns, redemptions and reviews. **Every number comes from the database; the AI only writes the wording**, and a check rejects any number in the text that isn't in the data. It ranks creators by visits driven, summarizes review themes and recommends three next actions.

Campaigns are built around hotpot occasions (birthdays, group nights, the first cold week, finals ending, payday), which gives each message a concrete hook and each offer a reason to come in now.

## Expected value

| Metric (from the brief) | How the system measures it |
|---|---|
| Offer redemptions | First visits: redemptions of creator codes, per creator |
| Repeat visits | Return visits ÷ first visits, per creator and campaign |
| Cost per redemption | What it cost to get each creator's post (comped meal + fee) ÷ first visits |
| Outreach response rate | Replies (including declines) ÷ messages sent, tracked in the approval queue |
| Research and coordination time saved | Estimate: creators researched, drafts written and visits logged × minutes per task (shown as an estimate) |
| Repeat-collaboration rate | The brief recommends which creators to rebook based on visits and cost |

The headline comparison the brief makes possible, "creator A drove 3× the visits of creator B at a third of the cost," can't be made today, because nothing links a post to a visit.

## Feasibility

- **Built and working end to end:** creator ranking, bilingual drafts with human approval, codes and QR links, staff redemption with return codes and voids, campaign results, weekly brief, demo fast-forward. **[fill: number]** automated tests cover the rules (for example, a return code can be used once even when two staff redeem it at the same moment).
- **Stack:** React frontend (built in Enter), Python FastAPI backend, Postgres on Supabase with pgvector, and Claude for the brand-fit check, drafts and brief wording, using structured outputs validated against a schema.
- **Safety by design:** creator captions and reviews are treated as untrusted text; drafts can only reference the creator's real posts and contain no links except the offer link; every approval, redemption and void is in an audit log; staff can only void within 15 minutes.
- **Evaluation:** precision@10 of the ranking against **[fill: 20]** hand-labeled creators, including deliberate traps (big but low-engagement accounts, creators who moved away, "湾区" meaning the Guangdong Greater Bay Area): **[fill]**. Draft acceptance rate from the approval log: **[fill]**.

## Key assumptions

- **Data access:** the demo uses a hand-collected seed of public creator profiles and posts, not live platform APIs. Instagram's business discovery and TikTok's research API are documented routes; Xiaohongshu has no public API, so it stays manual.
- **Simulated results:** visits, return visits and reviews after the fast-forward are simulated, go through the same redemption rules as real ones, and are labeled "Simulated" wherever they appear. A real pilot needs staff to enter codes at the counter (or a POS integration, which is out of scope).
- **Cost** means what Feng Hotpot spends to get a creator's post (comped meal plus any fee), not the value of offers diners redeem. Otherwise the creators who drive the most visits would look the most expensive.
- **Human in the loop:** every message is approved by a person, and every score explains itself so a manager can overrule it.
- One location per campaign; return offers are valid for 30 days at the same location.

## Broader application

The loop (rank local creators → personal outreach with approval → unique codes → first and return visits → weekly brief) fits any business where a creator post should turn into a visit: other restaurants and chains, cafés, salons, gyms, local retail. The single-use return code is a privacy-friendly way to measure repeat business without a loyalty program or customer data, and the occasion framing carries over to other categories.
