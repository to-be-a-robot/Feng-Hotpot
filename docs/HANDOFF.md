# Handoff: how anyone on the team can continue the frontend

Last updated: Nov 19, 2026 (after Shinjini's backend update of Nov 18). This page has no passwords, keys or private links on purpose. Where a secret is needed, it says **who holds it**.

**One sentence:** the frontend is built in Enter, one screen per prompt, from the files in this repo. Nothing needs coding. If Tyler is unavailable, any teammate can follow this page start to finish.

## 1. Where everything is

| Place | What is there | Owner |
|---|---|---|
| Branch `frontend`, folder `docs/` | `FRONTEND_SPEC.md` (screens and API contract), `ENTER_PROMPTS.md` (the prompts to paste), `wireframes/` (10 images), this page | Tyler |
| Branch `frontend`, folder `mocks/` | 21 sample responses (JSON) plus a README. One consistent story. | Tyler |
| Branch `backend` | Database tables and functions, the Python API (`workers/feng_workers/api.py`), tests, `README.md` (how to run it), `PENDING.md` (open questions). In `docs/`: `BACKEND_GUIDE.md` (how the app calls the API), `DEPLOY.md` (putting it online, about 45 minutes), `DEMO_SCRIPT.md` (the 3-minute demo), `SUBMISSION_DRAFT.md`, `openapi.json`. It also holds a merged copy of Tyler's `docs/` and `mocks/`, so merge `frontend` into it again after each push | Shinjini |
| Branch `main` | A placeholder README and `.gitignore` | Shared |
| Branch `enter-backend` | An early Enter commit (Nov 18, by `enter-pro`) with a few shared components and no screens, removed in the next commit. History only. **Do not build on it.** | n/a |
| Enter project | The running frontend, its chat history, the credits | Whoever opened it (write the name here: ________) |

The API and database follow `FRONTEND_SPEC.md` section 5, and the backend's tests check every response against `mocks/`. If the two ever disagree, the frontend follows what the running API returns, and someone fixes the spec the same day. Section 5.7 of the spec lists the known differences (for example, ids are long random strings, not `c_1`).

## 2. Who decides what

- **Tyler:** frontend, Enter, the spec and mocks.
- **Shinjini:** database, API, AI drafting, scoring, the weekly brief, sign-in setup.
- **Aolin:** product decisions, brand inputs (logo file, one or two hex colors, a font, three tone words), creator data.

Decided: D4 (cost means what the restaurant spends on a creator: comped meal plus any fee), D5 (one location per campaign), return codes (one per first-visit redemption, valid from the next local day for 30 days), voids, occasions in the database.

Still open (see `PENDING.md` on the `backend` branch for the full list):

- **D6:** Shinjini's Python API serves the endpoints. Aolin needs to confirm, because the original plan gave the redemption route to Tyler.
- **D1:** sign-in by email magic link. Until it is set up, the deployed API runs in a preview mode with a shared key (prompt 8A). Shinjini creates the accounts with one command (`DEPLOY.md`, Part 4) and switches the server to real sign-in (prompt 8B).
- Creator model: one row per account, or one person with several accounts.

## 3. If Tyler cannot do the Enter build: steps for the replacement

Everything below is also explained in detail in `docs/ENTER_PROMPTS.md`. Read its sections "Before you open Enter", "Rules for every prompt" and "What to look out for" first (10 minutes).

1. **Pick one driver.** Only one person sends prompts, so credits are not split. Write down the credit balance now.
2. **Get the files.** Clone the repo (or download it as a zip from GitHub), switch to branch `frontend`. You need `docs/ENTER_PROMPTS.md`, `docs/wireframes/`, and `mocks/`.
3. **Open a new Enter project.** Paste **Part 0** from `ENTER_PROMPTS.md` and nothing else. Enter should reply that it understands and builds nothing. If it starts building, tell it to stop and remove what it made.
4. **Send prompts 1 to 7 in order**, one at a time. For each: paste the prompt, paste or drag in the sample files named in it, and drag in the wireframe image(s) it lists. After each, click the new screen, then spend two minutes on the earlier screens. Check the prompt's **Done when** list. Write the credits used in a log.
5. **Run the Safety check** after prompt 7 (in Plan Mode, as the pack says).
6. **Export and commit.** Download the project from Enter, unzip into `app/` on branch `frontend`, run the secret search from Phase 5 of the pack, then commit and push. If Enter's plan does not allow downloads, copy the files from the Code tab, or ask a mentor.
7. **Visual customization (Phase 3) only after step 5.** Get the brand inputs from Aolin.
8. **Real data (Phase 4) only when Shinjini confirms** the API has a public `https://` address and the allowed-origins list includes your Enter address. Send **prompt 8A** (preview mode with the shared key). Ask Shinjini privately for the API address and the key, and put them in Enter's environment variables, never in the chat. When Shinjini has created the accounts and switched the server to real sign-in, send **prompt 8B** and ask for the two public Supabase settings. Never accept a service or secret key.
9. **Publish** in Enter and send the published address to Shinjini, who adds it to the allowed origins and to Supabase's redirect list.
10. **Rehearse the demo path** (section 5) twice, once on a laptop and once on a phone.

If two fixes in a row fail on the same problem, stop: take a screenshot, write what you see and what you expected, and ask in the team chat. Do not keep spending credits.

## 4. If something goes wrong

| Problem | What to do |
|---|---|
| Out of Enter credits | Keep the credits for fixes. Ship what works. The sample-data mode needs no backend. Ask the hackathon organizers (Converge) about more credits. |
| Enter cannot export code | Copy files from the Code tab one at a time, or keep Enter's published page as the demo and use the repo for the spec only. Tell a mentor early. |
| API is not ready for the demo | Run the frontend on sample data (`VITE_USE_MOCKS` is `true`). Say plainly to judges which parts are sample data. The spec labels simulated data in the app. |
| The first screen takes about a minute, or shows "Waking up the server" | Normal. The free server sleeps when idle. Open the app a few minutes before a demo. |
| "The preview key is missing or wrong" | The key in Enter's environment variables differs from the server's. Ask Shinjini to confirm it, and re-enter it in Enter's settings. |
| Browser error saying the request was blocked (CORS) | The server's allowed-origins list is missing your Enter address. Send the exact address to Shinjini. |
| A teammate sees a login or database Enter added by itself | Reply to Enter: "Remove <thing>. Build only what I described." |
| Wrong data shown | Use the "Wrong data" fix prompt in `ENTER_PROMPTS.md`. Compare against the matching file in `mocks/`. |
| Enter is already connected to this repo (the Nov 18 `enter-pro` commit shows it was) | The team decided not to use Enter's GitHub connector, because it is authorized at the account level and Enter does not document exactly what access it asks for. If you want it off, disconnect it in Enter's settings and in GitHub (Settings, Applications), then continue with export-and-commit as in step 6. |

## 5. Demo path (the order that matters most if time runs short)

1. Creators page: ranked list, filters, select creators.
2. Add to campaign: pick an occasion, create the campaign, drafts appear.
3. Outreach queue: review a draft, approve it, mark it sent and replied by hand (nothing is ever sent by the app).
4. Campaign detail: codes with Copy and QR download, post link.
5. Offer page on a phone (from the QR code): the diner view, then Show to staff.
6. Staff redeem on a phone: first visit, a return code is issued; then a return-code redemption.
7. Campaign detail again: **Fast-forward 2 weeks** (admin role, labeled Simulated).
8. Weekly Brief: the numbers, review signals and recommended actions.

This is the order of Shinjini's 3-minute script, `docs/DEMO_SCRIPT.md` on the `backend` branch. It also says how to reset the demo data before recording. Priority: the loop itself is P0 in the spec. Anything labeled P1 or P2 is optional.

## 6. Security rules that never change

- No secret or service-role key in the frontend, in a prompt, or in a chat. Only the public project URL and publishable key go into the app. One temporary exception: the shared preview key (prompt 8A) lives in an environment variable until real sign-in replaces it. It will be readable in the published page's code, so use it only with fictional data, never paste it into a chat or commit it, and move to prompt 8B before the published address is shared widely.
- Everything the app shows from the server or from creators is plain text. No raw HTML, no images from other sites, links only if they start with `https://`.
- The app never sends messages. Managers send outreach themselves and mark it by hand.
- The public offer page collects no personal data.
- The test headers `X-Dev-Key`, `X-Dev-Role` and `X-Dev-Locations` exist only for preview mode (prompt 8A). Prompt 8B removes them, and a published app with real sign-in must never send them.

## 7. Who to ask

Add names or handles here (no emails or phone numbers in a public repo):

- Enter project owner: ________
- API and database: Shinjini
- Product decisions and brand inputs: Aolin
- Frontend spec and prompts: Tyler
