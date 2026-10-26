# Progress log

Concise, append-only. Times are IST (UTC+5:30) unless marked.

## 2026-10-26

- 19:45 Spec received; deadline re-checked on Devpost (30 Oct 2026 10:00 PT = 22:30 IST). FAQ confirms Physical AI may use simulation; promo credits are Token Factory credits (code NEBIUS-DEVPOST-GLOBAL26 + Builders Program).
- 19:50 Research (prior art x3; Token Factory facts) saved to `docs/research/raw-research-2026-10-26.json`. Model chosen: `nvidia/nemotron-3-super-120b-a12b` ($0.30 / $0.90 per 1M tokens, official catalog JSON).
- 20:05 Simulator (`backend/faultline/sim`) + physics tests vs analytic solutions (linear, first-order pump, Torricelli, overflow, empty tank, conservation, seeded noise): 18 pass.
- 20:15 Twin pairs calibrated on the noise-free simulator; identifiability oracle; tools with backend validation; bounded loop; Nebius provider; SQLite store; run manager with sealed truth; evaluator; reference procedure; API.
- 20:30 Thin slice verified end to end with the reference procedure (blind twin run, FT-101 measurement, saved run, remedy verified, reveal after terminal). LIVE refused honestly without `NEBIUS_API_KEY` (409, no substitute).
- 20:40 Tests: twins, tools, loop (ScriptedProvider fixture), leakage (model requests, every public endpoint, logs, exports), persistence/rebuild, export integrity, grading, remedy verification, replay import. 85 pass.
- 20:28 UTC 14:58 Held-out set (24) and dev set (16) frozen; hashes in `eval/scenarios/FROZEN.md`.
- Arm A (reference procedure) on held-out: `eval/results/heldout-A-v1` (evaluator-v1) and `heldout-A-v2` (evaluator-v2, overflow bug fix in remedy check). Diagnostic grades identical in both.
- UI build and docs drafts running in parallel.

## Blocked

- Live Nemotron verification (smoke test, arms B and C, variability repeats, platform feedback from real use): needs `NEBIUS_API_KEY` set via `scripts/set-nebius-key.ps1`.
- Public repo, YouTube upload, Devpost submission: need the owner's authorization.
- User interviews/tests: none conducted.

## Resume here

1. `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Dev` then `.venv\Scripts\python -m pytest backend`.
2. If the key is set: smoke test `eval/run_eval.py --set dev-v2 --arm C --ids D-falling-level-0-standard --tag smoke-C1`, then `--set heldout-v2` B and C runs with new tags (see EVALUATION.md).

## 2026-10-26 (evening)

- 21:15 UI built (React + TS + Vite, hand-written SVG); checked in a real browser at 1280x720: Twin Challenge, blind run, reference investigation, approval, reveal, night-shift inconclusive. No console errors.
- 21:30 Adversarial backend review (4 lenses, 2 skeptics per finding): 22 confirmed, 4 refuted. All 22 fixed:
  - off-grid dip crash; tool exceptions are now contained;
  - FT-101 spin-up (30 s fit/settle);
  - oracle wait rule now uses fitted rates (v2);
  - symmetric minimum fault size;
  - remedy endpoint no longer leaks true-plant numbers before reveal (now sealed);
  - DNS rebinding (trusted hosts + origin check);
  - final-turn forcing with parallel calls;
  - one-shot arm could measure, and skipped the spend check;
  - reference arm was blocked by the spend ceiling;
  - unknown prices failed open (now fail closed);
  - cancelled runs lost their counters;
  - lenient inconclusive grading (now `wrong_inconclusive`);
  - unnecessary remedies counted as verified;
  - held-out near-copies of dev (now heldout-v2 with a distance rule);
  - spend-ledger race (append-only, locked).
- 21:05 IST (15:35 UTC) heldout-v2 (26) and dev-v2 frozen; arm A: 21/22 correct, 4/4 appropriate inconclusive, 1 wrong (V11, tank-area mismatch).
- Night-shift allowance is now 10 min. With 15+ min, the falling-level twins are separable by the leak's slowing fall (oracle v2).
- 22:00 Independent UI review (2 lenses + skeptics): 15 confirmed and all fixed. The backend one was a Markdown export crash on approved remedies. The UI ones:
  - replay runs labelled as not started, and replayed reference steps shown as model calls;
  - FT-101 averaging window drawn from the clamp-fit start;
  - double-click duplicate POSTs;
  - a retry banner shown when nothing retried;
  - a bad URL could crash the app;
  - coach-mark keyboard handling, and focus lost after main actions;
  - a timeline entry focused with no visible ring;
  - twin pick buttons below the fold;
  - small diagram text and low pipe contrast;
  - live-region semantics;
  - a misleading key message when the backend is down;
  - no h1 on the workstation.
- 22:20 `replays/example-reference-twin-falling-level.json` added (reference procedure, labelled not AI). Clean-copy check: `scripts/setup.ps1 -Dev` exit 0 (100 s), 106 tests pass in the copy, `scripts/start.ps1 -Port 8011` serves the UI and API, and a foreign Host header gets 400.

## 2026-10-26 (night): live verification

- 22:40 Key set by the owner. `/v1/models`: 30 models, 5 NVIDIA; `nvidia/nemotron-3-super-120b-a12b` listed.
- 22:45 Smoke test (dev, D-falling-level-0-standard): correct, 7 tool calls, 35 s, $0.0152.
- 23:05 heldout-v2:
  - C: 22/22 correct, 3/4 appropriate inconclusive, 1 wrong inconclusive (V25), 0 confident wrong, $0.388.
  - B: 4/22 correct, 4/4 appropriate, 16 unnecessary inconclusive, 2 confident wrong, $0.042.
  - Variability: V04 3/3, V19 3/3, V15 2/3 (1 unsupported diagnosis).
  - Ledger total $0.5966 against a $1.50 ceiling. 275 calls, 0 provider failures.
- 23:08 LIVE in-app Twin Challenge recorded: correct leak diagnosis, $0.013, exported to `replays/live-nemotron-twin-falling-level.json`.
- 23:30 Owner authorised publishing. Final secret scan of staged content was clean (patterns + actual key). Commit 9900ab5. Public repo https://github.com/professor-200629/faultline created and pushed; GitHub detects the MIT license; fresh clone verified.
