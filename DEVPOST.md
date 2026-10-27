# Devpost submission text (draft)

> Draft for the owner to paste. Results sections must match EVALUATION.md at
> the time of submission. Do not paste a number that EVALUATION.md does not
> contain.

**Track:** Physical AI (simulation; no physical hardware)

**Video:** https://youtu.be/Y0bQyq9BvDA (public, 2 min 54 s)

**Repository:** https://github.com/professor-200629/faultline (MIT)

**Tagline:** Two tanks raise the same warning. Their faults are different. Faultline has to earn the diagnosis.

## Inspiration

When a tank level falls while the pump shows RUNNING, the first reading cannot
tell a worn pump from a leak. A flat level reading cannot tell a stuck sensor
from a pump that happens to match demand. Trainees are taught to choose the
measurement that separates the explanations. We wanted an AI investigator that
works the same way, and a challenge where it cannot cheat.

## What it does

Faultline investigates a simulated water tank (T-101) and pump (P-101). An
NVIDIA Nemotron agent running on Nebius Token Factory chooses what to do next:
read the historian, fit a clamp-on inlet flow meter, ask for an independent dip
reading, briefly stop the pump, or wait. It also asks a public model what each
test *would* show under each hypothesis. Every measurement is computed by a
deterministic simulator and gets an evidence ID. The agent ends with one of:

- a diagnosis, citing supporting and contradicting evidence for every hypothesis;
- *inconclusive*, naming the measurement that would decide.

A recommended repair changes the simulated plant only after a person approves
it. The public then sees post-maintenance readings, while an independent
evaluator checks the true plant; that check stays sealed until the reveal.

**Twin Challenge.** Two physically valid plants show the same warning and the
same alarm-window observations, but have different hidden causes. A judge
secretly picks one, or lets the server deal one at random. The truth stays on
the server and is revealed only after the investigation ends. With the
night-shift site profile (no flow meter, no dip, pump must keep running, 10
minutes) the twins cannot be separated, and the honest answer is
*inconclusive*. Given 15 minutes or more, the leak's slowing fall would give it
away.

## How we built it

- **Simulator:** Python, time-stepped RK4 with exact water bookkeeping
  (overflow and unmet demand included). Sensor models cover lag, noise,
  quantisation, a stuck element and calibration offset. Noise is seeded, and
  simulation time is logical. It is validated against analytic solutions
  (linear fill, first-order pump start, Torricelli drain).
- **Twins:** one hidden parameter is calibrated on the noise-free simulator so
  the alarm windows match (≤ 0.95 mm difference). Tests prove which instruments
  separate them.
- **Agent:** one bounded loop over OpenAI-style tool calls to
  `nvidia/nemotron-3-super-120b-a12b` on Token Factory. Budgets are 12 tool
  calls and 120 s, with retries charged. The final turn forces
  `submit_diagnosis`. Backend validation covers schemas, ranges, site
  permissions and evidence-ID citation rules.
- **Hidden-state boundary:** the truth lives in a sealed table. The agent gets
  only whitelisted observation objects. Judge endpoints need a loopback cookie
  and header. Leakage tests scan model requests, API responses, logs and exports.
- **Evaluation:** 26 held-out scenarios frozen by hash before any model run,
  including model-mismatch cases and a distance rule against the dev set (one
  revision, disclosed). Grading is by an independent evaluator plus an
  identifiability oracle. The comparators are a deterministic procedure (same
  tools and budgets) and a one-shot ablation.
- **Interface:** React + TypeScript, SVG equipment view and trends. The tank
  graphic shows only the *indicated* level.

## Results

On 26 frozen held-out scenarios (live Nemotron 3 Super on Token Factory, 2026-10-26):

| | Faultline agent | Reference procedure (not AI) | One-shot model (ablation) |
|---|---|---|---|
| Correct diagnoses (22 solvable) | 22 | 21 | 4 |
| Honest inconclusive (4 unsolvable) | 3 | 4 | 4 |
| Confident wrong diagnoses | 0 | 1 | 2 |
| Cost per investigation | about $0.015 | $0 | about $0.002 |

The agent does **not** beat the hand-written procedure overall: both get 25 of
26. Each fails differently.

- The agent once read noise as a trend and ruled out a cause it could not
  exclude.
- In 3 repeats of one ambiguous case, it guessed once instead of staying
  inconclusive.
- Its one "win" over the procedure came partly from a less precise test.

All of this is documented in EVALUATION.md.

## Challenges

- Making twins that truly match without hand-authoring telemetry.
- Defining "could anyone have known?" precisely enough to grade an
  *inconclusive*.
- Keeping every path that could leak the hidden fault (prompts, logs, exports,
  IDs, the UI's tank drawing) closed, and testing that it is.

## What's next

- Run the user-research plan with maintenance trainees (USER_RESEARCH.md). No
  users have been tested yet.
- Add pump-curve physics and combined faults.
- Broaden the model comparison (for example Nemotron 3 Ultra or Lightning), and teach the agent to respect declared instrument availability (24 wasted calls in 36 runs).

## Built with

Python, FastAPI, SQLite, React, TypeScript, Vite, SVG, NVIDIA Nemotron 3 Super,
Nebius Token Factory.

## Pre-existing work

None. The repository was created on 2026-10-26, during the submission period.
