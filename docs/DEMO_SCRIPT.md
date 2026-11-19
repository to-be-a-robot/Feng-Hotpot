# Demo script: "First cold week" at Feng Hotpot Sunnyvale

**Length:** 3 minutes · **Presenter:** one person driving, one narrating · **Screens:** Tyler's app (manager view, then staff view on a phone)

## Before recording (10 minutes)

1. Reset: admin `POST /demo/reset` with `{"confirm": "RESET"}` (or `python -m feng_workers.devdb --reset` locally, then load, embed and score).
2. Check creators are scored with Claude reasons (`ANTHROPIC_API_KEY` set), not template text.
3. Open two windows: the manager dashboard (desktop) and `/redeem` signed in as staff (phone-sized).
4. Have one creator's offer link (`/r/<code>`) ready to open on the phone after step 2.

## The run

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00 | Creators | Show the ranked list for Sunnyvale. Expand the top row. | "Today a manager finds creators by scrolling. Here the shortlist is ranked by how local the audience is, food fit, engagement, comment quality and posting rhythm, and every score explains itself." |
| 0:25 | Creators | Point at a trap from Aolin's label set, whichever ranks low in the real data: a big account with generic comments, or a "湾区" account that's really the Guangdong Greater Bay Area. | "Follower count isn't fit. This big account ranks below a small local reviewer, and the reason says why." (Use the real numbers on screen.) |
| 0:40 | Add to campaign | Select 5, pick **First cold week**, English + 中文, create. | "Each campaign is built around a hotpot occasion, so the offer has a reason to come in now. Codes are created first, then drafts." |
| 0:55 | Outreach | Open a Chinese Xiaohongshu draft. Show the referenced post, edit one line, approve. | "Drafts reference the creator's own recent posts, in their language. Nothing sends automatically: a manager edits and approves, then copies it into the DM." |
| 1:20 | Campaign detail | Show the code and QR per creator. Add a post link. | "Every creator gets their own code, so every visit is attributed." |
| 1:35 | Phone: offer page → Redeem | Open the offer link, "Show to staff", redeem with party size 4. Show the return code. | "Staff redeem the code at the table. That first visit issues a single-use return code for the guest's next visit. That's how we measure repeat visits without collecting anyone's personal data." |
| 2:00 | Campaign detail | **Fast-forward 2 weeks** (clearly labeled *Simulated*). | "We can't wait two weeks on stage, so this fast-forward adds simulated visits through the same redemption rules, and labels every number that includes them." |
| 2:15 | Weekly Brief | Show the tiles, the creators ranked by visits, review signals, 3 actions. | "The brief closes the loop. Every number comes from the records; the AI only writes the words. Here: one creator drove most return visits at the same cost, Friday waits show up in reviews, and the next actions follow from that." |
| 2:45 | Brief | Point at the "Simulated" badge and the hours-saved *estimate*. | "Results in this demo are simulated. In a pilot, the same loop runs on real codes at the counter." |
| 3:00 | | End. | |

## If something goes wrong

- **Drafts still "writing":** keep talking over the progress bar; template drafts appear within seconds, Claude drafts within about a minute.
- **The deployed API is waking up** (free plan sleeps): open the app once a few minutes before recording.
- **A redemption error:** read the message aloud (e.g. "This code was already used"). It shows the single-use rule working.
