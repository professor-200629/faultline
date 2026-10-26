# FAULTLINE

**A simulation-based AI fault investigator for a small water-tank and pump system.**
An NVIDIA Nemotron agent on Nebius Token Factory chooses measurements and
bounded tests on a deterministic simulator, distrusts sensors that may be
wrong, and ends with an evidence-cited diagnosis or an honest *inconclusive*.
A judge holds the hidden fault on the server; the agent never receives it.

> These systems show the same warning. Their faults are different.
> Choose one secretly and let Faultline earn its diagnosis.

Built for the Nebius x NVIDIA Global AI Hackathon (Physical AI track,
simulation; see [HACKATHON.md](HACKATHON.md)). This is a **simulation
prototype for maintenance trainees**, not certified control software and not
field-validated maintenance advice.

| | |
|---|---|
| Model | `nvidia/nemotron-3-super-120b-a12b` via Nebius Token Factory (`https://api.tokenfactory.nebius.com/v1`, OpenAI-compatible tool calling) |
| Live model status | **Verified live on 2026-10-26.** 62 evaluated investigations (26 held-out, 9 repeats, 1 smoke test, 26 one-shot): 275 tool-calling requests, all returning well-formed tool calls, 0 provider failures. Plus 1 live in-app Twin Challenge (6 requests), recorded in `replays/`. See [EVALUATION.md](EVALUATION.md) |
| Stack | Python 3.11 + FastAPI + SQLite backend; React + TypeScript + Vite interface; SVG equipment view |
| Tests | 106 in `backend/tests`: physics vs analytic solutions, twins, tools, loop, hidden-state leakage, persistence, evaluator |
| Held-out result (26 scenarios) | Faultline agent: 22/22 correct, 3/4 appropriate inconclusive, 0 confident wrong; reference procedure: 21/22, 4/4, 1 confident wrong ([details](EVALUATION.md)) |
| License | MIT ([LICENSE](LICENSE)); third-party notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) |

## What it does

1. **A warning appears** on tank T-101 (public alarm rules on logged data:
   low level, or a mass-balance deviation).
2. **The agent investigates** with eight typed tools: read the historian,
   measure inlet flow with a clamp-on meter (FT-101), ask for a dip-tape level
   reading (DIP-101), stop the pump for a bounded test, wait, ask the public
   model what a test *would* show under a hypothesis, record its hypothesis
   board, and submit. Every argument is validated in backend code; the site may
   forbid some tests or lack some instruments.
3. **Every number comes from the simulator.** Observations get evidence IDs
   (E1, E2, ...). Model-based expectations get prediction IDs (P1, ...) and
   cannot be cited as evidence.
4. **The outcome** is a diagnosis with supporting and contradicting evidence for
   each hypothesis, or *inconclusive* with the measurement that would decide.
5. **Diagnosis is separate from repair.** A recommended remedy is applied to the
   simulated plant only after a human approves it. The screen then shows
   post-maintenance *measurements*. An independent evaluator also checks the true
   plant, and its result stays sealed until the reveal.
6. **The judge reveals the truth** only after the run is terminal, with the
   grade and an identifiability analysis.

### The Twin Challenge

Two physically valid plants whose alarm-window observations match, but whose
causes differ:

| Pair | Member | Hidden cause | What separates them |
|---|---|---|---|
| Level falling while P-101 runs | α/β (shuffled per challenge) | pump delivering 62.5 % of rated flow, or a healthy pump with an orifice leak calibrated on the simulator to the same level trend (noise-free LT-101 difference ≤ 0.95 mm over 15 min) | FT-101 inlet flow; P-101 stop test. *Not* a dip reading |
| Level reading flat while P-101 runs | α/β | LT-101 sensing element stuck (true level rising) or pump delivering exactly the demand | dip reading, FT-101, or stop test |

The judge picks α, β, or "deal at random", and the server builds the sealed
run with a fresh noise seed. With the night-shift site profile (no FT-101, no
dip, pump must keep running, at most 10 more minutes) neither pair can be
separated, and the correct outcome is *inconclusive*. The flat-reading pair can
never be separated by waiting. The falling-level pair could be, with 15 minutes
or more, because an orifice leak's fall slows as the level drops. These claims
are tested in `tests/test_twins.py`.

## Install and run (Windows)

Requires Python 3.11+, Node.js 18+, about 500 MB of disk space. No GPU.

```powershell
git clone <this repository> faultline
cd faultline
powershell -ExecutionPolicy Bypass -File scripts\setup.ps1        # venv + hash-locked deps + UI build
powershell -ExecutionPolicy Bypass -File scripts\start.ps1        # http://127.0.0.1:8000
```

Developer extras: `scripts\setup.ps1 -Dev`, then
`cd backend; ..\.venv\Scripts\python -m pytest`. For interface work, run
`npm run dev` in `frontend/` (proxies `/api` to port 8000).

### Live credentials (Nebius Token Factory)

1. Create a Token Factory account and an API key at tokenfactory.nebius.com.
   Hackathon credits: $25 via the Devpost form (code `NEBIUS-DEVPOST-GLOBAL26`)
   plus $25 for joining the Nebius Builders Program (see HACKATHON.md).
2. In your own PowerShell window run
   `powershell -ExecutionPolicy Bypass -File scripts\set-nebius-key.ps1`.
   It reads the key with hidden input, stores it as the per-user variable
   `NEBIUS_API_KEY`, and checks it against the free `/v1/models` endpoint.
   Alternatively copy `.env.example` to `.env` (gitignored).
3. The server reads the key at request time, so no restart is needed. The top
   bar's **Check connection** button calls `/v1/models` and shows whether the
   configured model is listed.

The key is used only server-side and never logged, returned or sent to the
browser. Spending is estimated from reported token usage at the prices in
`backend/faultline/config.py`. A hard ceiling (`FAULTLINE_MAX_SPEND_USD`,
default $3.00) stops new model calls before they would exceed it.

## Modes (always labelled)

| Mode | What runs | Needs key |
|---|---|---|
| **LIVE** | Nemotron on Nebius selects every tool call | yes |
| **REFERENCE PROCEDURE** | a deterministic diagnostic procedure written by hand, *not AI*, using the same tools and budgets (the evaluation's comparator A) | no |
| **REPLAY** | playback of a recorded run (bundles in `replays/` are imported at start-up) | no |

If the key is missing or the provider fails, LIVE fails visibly. A scripted
or reference run is never substituted.

## Architecture

```
browser (React)                     FastAPI (127.0.0.1)
 Workstation / Twin / Blind  --->  /api/*        public views, events, telemetry, exports
 Judge panel                 --->  /api/judge/*  loopback cookie + header: create sealed runs, reveal
                                       |
             RunManager ---------------+-- SealedStore (case config, seed, grades)   [judge only]
               |  creates                                                       
               v                                                                
   InstrumentPanel (private Plant) <--- ToolExecutor (8 validated tools) <--- agent loop <---> Nebius Token Factory
               |                                 |                                         (Nemotron, tools)
               |                                 +-- evidence ledger E#, predictions P#, hypothesis board
               v
   Evaluator (after terminal): grade vs truth + identifiability oracle; remedy verification on a copy of the true plant
```

* Simulator: [SIMULATOR.md](SIMULATOR.md) (equations, units, assumptions, verification table).
* Hidden-state boundary: [THREAT_MODEL.md](THREAT_MODEL.md).
* Evaluation method and results: [EVALUATION.md](EVALUATION.md).
* Prior art and what is (and is not) new here: [PRIOR_ART.md](PRIOR_ART.md).
* Known limitations: [LIMITATIONS.md](LIMITATIONS.md).
* User research plan (no sessions run yet): [USER_RESEARCH.md](USER_RESEARCH.md).
* Platform feedback: [PLATFORM_FEEDBACK.md](PLATFORM_FEEDBACK.md).
* Progress log: [PROGRESS.md](PROGRESS.md).

## How Nemotron and Token Factory are used

* Every LIVE investigation step is a Nemotron chat completion with OpenAI-style
  `tools`. The model chooses the next tool and its arguments, and writes the
  purpose of each test. The backend validates and executes the call and returns
  the simulator's result.
* On the final allowed call the backend offers only `submit_diagnosis`
  (`tool_choice` names it), so the run ends with a structured outcome or fails
  visibly.
* Token usage per call is recorded from the API response and costed at the
  catalogue price recorded in `backend/faultline/config.py`.
* The same harness runs the one-shot ablation (B) and the full agent (C) on
  the frozen held-out set: `eval/run_eval.py`.
* No other Nebius services are used: no AI Cloud, Serverless Jobs, Serverless
  Endpoints or DevPods. The app runs locally and calls only the Token Factory
  inference API.

## Evidence export

Every run exports as JSON (`/api/runs/<id>/export.json`) and Markdown
(`/api/runs/<id>/report.md`). An export contains the context, every evidence
item with its raw rows, the public telemetry, predictions, the timeline, model
calls (usage, latency, tool names), the diagnosis, any remedy decision and its
verification, the limitations, and SHA-256 digests. A judge reveal adds a
separately marked ground-truth section. A test checks that exported evidence
rows equal the recorded historian samples.
