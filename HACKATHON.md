# Hackathon requirements and how FAULTLINE maps to them

This file records the official requirements of the **Nebius x NVIDIA Global AI
Hackathon** as checked on **2026-10-26**, and where FAULTLINE stands against
each one. The Devpost pages are authoritative. Re-read them before submitting,
because they can change.

**Status on 2026-10-26: nothing has been submitted.** The repository is not
public and no video has been recorded. Live Nemotron calls were verified on 2026-10-26.
No `NEBIUS_API_KEY` was configured, so nothing below about live behaviour
has been observed.

FAULTLINE is a simulation prototype. It is not certified industrial software
and not field-validated maintenance advice.

## Sources

These official Devpost pages were read in a browser on 2026-10-26. Dated,
paraphrased notes are in `docs/research/devpost-notes-2026-10-26.md`:

- Rules: https://nebiusglobalaihackathon.devpost.com/rules
- FAQ: https://nebiusglobalaihackathon.devpost.com/details/faqs
- Main page: https://nebiusglobalaihackathon.devpost.com/
- Resources: https://nebiusglobalaihackathon.devpost.com/resources (recorded
  by the research agent in `docs/research/raw-research-2026-10-26.json`, not
  opened directly)

Token Factory facts (model catalogue, prices, deprecations, trial credit) come
from the Nebius sources recorded in `docs/research/raw-research-2026-10-26.json`.

## 1. Dates and organisers

| Item | Value |
|---|---|
| Submission period | Aug 26, 2026 9:00 am PT to **Friday Oct 30, 2026 10:00 am PT** |
| Deadline in other zones | 17:00 UTC, 22:30 IST (Oct 30, 2026); the Devpost sidebar shows "Oct 30, 2026 @ 10:30pm GMT+5:30" |
| Judging period | Dec 1 to Dec 15, 2026 |
| Winners announced | around Jan 11, 2027 |
| Sponsor | Nebius B.V. |
| Administrator | Devpost, Inc. |

## 2. Platform and model requirement

- The project must **run on Nebius Token Factory or Nebius AI Cloud** and use
  **at least one NVIDIA open source model**.
- "Runs on" means a runtime call to the Token Factory inference API, or
  deployment on Nebius AI Cloud compute (Serverless Jobs, Serverless Endpoints
  or DevPods).
- FAQ clarifications:
  - Calling an NVIDIA model through Token Factory satisfies the requirement.
  - The rest of the app does not have to be hosted on Nebius.
  - Calling NVIDIA models through other providers (for example HuggingFace or
    OpenRouter) does **not** satisfy it.

## 3. Tracks

1. Coding and Agentic Engineering
2. Best Apps and Agents
3. Personal AI
4. **Physical AI**: embodied and edge agents (robotics, IoT, on-device
   intelligence), powered by Nemotron, GR00T, Cosmos and Sonic models and
   coordinated through an agent runtime. Nebius Serverless Jobs and Endpoints
   are suggested.

FAQ and rules notes for Physical AI:

- A simulation may be used instead of a physical robot. There is no required
  hardware list.
- NVIDIA open models beyond Nemotron, GR00T, Cosmos and Sonic are allowed.
- **Video:** at least one minute of the hardware operating or, with no
  hardware, of the key application modules in action.
- **No demo URL needed:** Physical AI submissions are evaluated under the
  rules' hardware-access provision instead.

## 4. What a submission must include

1. A working project.
2. The chosen track.
3. A text description.
4. A public repository on GitHub, GitLab or Bitbucket. It must contain all
   source code, assets and instructions. The open-source license must be
   detectable and visible at the top of the repository page (in the About
   section).
5. A README that covers:
   - setup instructions,
   - how Nemotron or other NVIDIA models are used,
   - where Token Factory accelerated the workflow,
   - any other Nebius services used.
6. A demo video with these properties:
   - under 3 minutes (judges are not required to watch beyond three minutes),
   - public on YouTube,
   - shows the project functioning, including Token Factory and Nemotron in use,
   - contains no third-party trademarks or copyrighted music without permission.
7. Feedback on Token Factory, AI Cloud and NVIDIA tools.
8. If the project existed before the submission period, a written explanation
   of what was significantly updated during it.
9. All materials in English, or with English translations.

## 5. Testing and judging

- **Access:** the working project must be available to judges free of charge
  and without restriction until the Judging Period ends. It can be offered as
  a website, a functioning demo or a test build.
- **Judges may not run it:** they may judge on the description, images and
  video alone.
- **Stage One** is pass/fail. It checks whether the project fits the theme ("a
  genuine attempt at the track's stated goal") and reasonably applies the
  required APIs.
- **Stage Two** has four equally weighted criteria. Paraphrasing the main
  page's questions:
  - **Technological Implementation:** how well the project is built and how
    effectively it uses Token Factory or AI Cloud models and Nemotron.
  - **Design:** whether it delivers a complete, coherent product experience,
    not just a technical proof of concept.
  - **Potential Impact:** whether it makes a credible, specific case for a real
    problem and a real audience, and whether what is demonstrated addresses it.
  - **Quality of the Idea:** whether it is a creative, non-obvious use of the
    platform and the models, and shows genuine understanding of the problem
    space.

## 6. Credits and eligibility

**Credits**

- The Devpost resources page offers **$25 of Token Factory credits** through a
  form with activation code `NEBIUS-DEVPOST-GLOBAL26`, and **another $25** for
  joining the Nebius Builders Program.
- The FAQ says the official promotional credits are Token Factory credits and
  that missing credits are handled case by case on the Nebius Discord.
- The Token Factory docs say new sign-ups get **$1 of trial credit, valid for
  30 days**, and that onboarding requires a billing account with a bank card.
  (Source: https://docs.tokenfactory.nebius.com/other-capabilities/billing-new,
  as recorded in the research file.)
- This repository does not record whether any of these credits have been
  claimed.

**Eligibility**

- Residents of these places are excluded: Brazil, Quebec, Russia, Crimea, Cuba,
  Iran, North Korea and other comprehensively sanctioned regions.
- Separately, the FAQ notes that some countries are not yet supported for Token
  Factory billing onboarding. This gap is about provisioning an account, not
  about eligibility to enter.

## 7. FAULTLINE choices

**Track: Physical AI, simulation, no hardware.** FAULTLINE investigates faults
on a simulated tank-and-pump system (`backend/faultline/sim/`). An agent picks
measurements and bounded tests through eight validated tools
(`backend/faultline/agent/tools.py`).

FAULTLINE does **not** use GR00T, Cosmos, Sonic or any Nebius AI Cloud service.
Its "agent runtime" is its own bounded tool loop
(`backend/faultline/agent/loop.py`). Whether this fits the Physical AI theme
is the judges' Stage One call.

**Model: `nvidia/nemotron-3-super-120b-a12b`.** It is called through
`https://api.tokenfactory.nebius.com/v1` with OpenAI-compatible chat
completions and `tools`. Both values are the defaults in
`backend/faultline/config.py`, and the HTTP call is in
`backend/faultline/agent/provider.py`. Reasons for the choice:

- The official public catalogue lists `function_calling` among its use cases.
- The Token Factory August 2026 deprecation notice names it as the replacement
  for `nvidia/Llama-3_1-Nemotron-Ultra-253B-v1`, which was removed from
  Serverless on Aug 31, 2026.
- Price: **$0.30 per 1M input tokens and $0.90 per 1M output tokens**, from the
  official public catalogue JSON
  https://tokenfactory.nebius.com/api/public/models_info, read 2026-10-26.

Other models can be selected with `FAULTLINE_MODEL`. `config.py` holds
catalogue prices for three of them (Ultra 550B, Lightning, Nano 30B). Any
other model needs `FAULTLINE_PRICE_IN_PER_M` and `FAULTLINE_PRICE_OUT_PER_M`;
without them its spend cannot be estimated and the ceiling check is skipped
(`agent/loop.py`).

Spend is estimated from reported token usage. A ceiling on total recorded
spend, `FAULTLINE_MAX_SPEND_USD`, defaults to $3.00 (`config.py`,
`runtime.py`).

**New project.** FAULTLINE was started on 2026-10-26, inside the submission
period (`PROGRESS.md`). When this file was written, the git repository had
**no commits** (`git rev-list --all --count` returned 0), so git holds no
history before that date to show either way.

## 8. FAULTLINE mapping

Status meanings:

- **DONE**: exists in the repository now.
- **PENDING**: an external step not yet taken (public repo, YouTube video,
  Devpost submission, live Nemotron verification, feedback from live use).
- **OPEN**: a gap or decision that is not resolved yet.

| Requirement | How FAULTLINE meets it | Status |
|---|---|---|
| Submit before Oct 30, 2026 10:00 am PT | Nothing submitted yet | PENDING (Devpost submission) |
| Runtime call to the Token Factory inference API (code) | `NebiusProvider.complete` POSTs to `{base_url}/chat/completions`. The default `base_url` is `https://api.tokenfactory.nebius.com/v1` (`agent/provider.py`, `config.py`) | DONE |
| Runtime call to the Token Factory inference API (verified live) | Verified on 2026-10-26: 275 chat completions with tools to `nvidia/nemotron-3-super-120b-a12b` at `https://api.tokenfactory.nebius.com/v1`, all successful (EVALUATION.md, `eval/results/`) | DONE |
| At least one NVIDIA open source model | `nvidia/nemotron-3-super-120b-a12b`, used live | DONE |
| Not called through another provider (HuggingFace, OpenRouter, ...) | The only model provider is `NebiusProvider`. The other two are a non-AI reference procedure (`agent/baseline.py`) and a test fixture (`ScriptedProvider`), and both are labelled as such | DONE |
| Track | Physical AI, simulation, no hardware (section 7) | Choice made; selecting it on Devpost PENDING |
| Working project | Local app: FastAPI backend and React UI, started with `scripts/setup.ps1` and `scripts/start.ps1` (Windows). REFERENCE mode runs without a key. On 2026-10-26, `pytest` in `backend/` gave 106 passed, and `scripts/setup.ps1 -Dev` succeeded from a clean copy (100 s). LIVE mode is unverified | DONE locally (Windows); LIVE PENDING |
| Text description | Draft text in `DEVPOST.md` and `README.md` | Drafts DONE; entry on Devpost PENDING |
| Public repo on GitHub/GitLab/Bitbucket | Local git repository only, with no remote and no commits | PENDING (public repository creation) |
| All source, assets and instructions in the repo | `backend/`, `frontend/`, `eval/`, `scripts/` and `docs/` are present locally. `.gitignore` excludes `.env`, `data/`, `.venv/`, `node_modules/` and `frontend/dist/` | DONE locally; publishing PENDING |
| Open-source license file visible in About | `LICENSE` (MIT) exists. Whether GitHub shows it in About can only be checked after publishing | LICENSE DONE; About check PENDING |
| README: setup instructions | `README.md` has Windows install and run steps. There are no macOS or Linux steps or scripts | DONE (Windows); non-Windows OPEN |
| README: how Nemotron/NVIDIA models are used | Section "How Nemotron and Token Factory are used" in `README.md` | DONE (draft) |
| README: where Token Factory accelerated the workflow | README section on Nemotron/Token Factory use and EVALUATION.md cost and latency figures (median 5.1 s per call, about $0.015 per investigation) | DONE |
| README: other Nebius services used | README states that none are used (no AI Cloud, Serverless Jobs, Serverless Endpoints or DevPods) | DONE |
| Demo video under 3 min, public on YouTube, no unlicensed trademarks or music | Not recorded | PENDING (YouTube video recording/upload) |
| Physical AI video: at least 1 min of key modules in action | Planned modules: simulator and equipment view, agent tool calls, hypothesis board, inconclusive outcome, remedy approval, judge reveal. A LIVE segment needs a key | PENDING (YouTube video recording/upload) |
| Feedback on Token Factory, AI Cloud, NVIDIA tools | `PLATFORM_FEEDBACK.md`, sections A (documentation) and B (live use). AI Cloud and other NVIDIA tools were not used | DONE |
| Explanation if the project existed before the period | Not applicable. The project was created on 2026-10-26 and the repository had no commits (section 7) | DONE (statement) |
| English materials | All documents and UI text are in English | DONE |
| Free access for judges until Dec 15, 2026 | A test build is available once the repo is public. REFERENCE mode and REPLAY need no key. `replays/` holds one recorded LIVE Nemotron run and one reference-procedure run. New LIVE runs need the judge's own Token Factory key | OPEN (judge LIVE access); public repo PENDING |
| Working demo URL | Not required for Physical AI. FAULTLINE has no hosted URL | Not required |
| Stage One: applies the required APIs | Live Token Factory calls are recorded; the video must also show one | Calls DONE; video PENDING |
| Eligibility (country of residence) | Not checked in this file. The entrant must confirm | OPEN |
| Token Factory account in the entrant's country | Onboarding needs a billing account with a bank card. Whether provisioning works in the entrant's country is unverified, and it is part of the `NEBIUS_API_KEY` blocker | OPEN |

## 9. Re-check before submitting

- [ ] Re-read the rules, FAQ, main and resources pages on Devpost. Check for
      changes to the deadline, requirements or judging criteria.
- [ ] Confirm the deadline in local time: Oct 30, 2026, 10:00 am PT = 17:00
      UTC = 22:30 IST.
- [ ] Confirm eligibility for the entrant's country of residence.
- [ ] Confirm the Token Factory account works in that country.
- [ ] Set the key in your own PowerShell window with
      `powershell -ExecutionPolicy Bypass -File scripts\set-nebius-key.ps1`.
- [ ] Use **Check connection** in the UI to confirm
      `nvidia/nemotron-3-super-120b-a12b` is listed for the account on the
      global base URL.
- [ ] Re-check the model price in the Token Factory console before quoting any
      cost.
- [ ] Run a live smoke test:
      `.venv\Scripts\python eval\run_eval.py --set heldout --arm C --ids H04 --tag smoke-C1`.
- [ ] Record only real results in `EVALUATION.md`.
- [ ] Fill in section B of `PLATFORM_FEEDBACK.md`.
- [ ] Update the README with where Token Factory helped and with "no other
      Nebius services used".
- [ ] Update the "verified live" rows of this file.
- [ ] Decide how judges get LIVE access until Dec 15, 2026: their own key,
      recorded runs in `replays/`, or another free route. Then document it in
      the README.
- [ ] Before the first commit, run `git status` and search the tree for secrets.
      Confirm `.env`, `data/` and `.venv/` are not staged.
- [ ] Create the public repository and push.
- [ ] Confirm the MIT license shows in the About section.
- [ ] Confirm the README setup steps work from a fresh clone.
- [ ] Re-run `pytest` in `backend/`.
- [ ] Record the video:
  - [ ] under 3 minutes,
  - [ ] at least 1 minute of the key modules in action,
  - [ ] mode labels (LIVE, REFERENCE PROCEDURE, REPLAY) visible,
  - [ ] no third-party music or trademarks,
  - [ ] uploaded as public on YouTube,
  - [ ] plays when logged out.
- [ ] Fill in the Devpost form:
  - [ ] Physical AI track,
  - [ ] description,
  - [ ] repository URL,
  - [ ] YouTube URL,
  - [ ] platform feedback,
  - [ ] new-project statement.
- [ ] Check that no material calls FAULTLINE validated, certified or suitable
      for real maintenance decisions.
- [ ] Keep the repository and video public until judging ends (Dec 15, 2026).
