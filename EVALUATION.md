# Evaluation

Status on 2026-10-26 (23:10 IST): all three arms have run on the frozen
held-out set v2:

- A: the deterministic reference procedure;
- B: one-shot Nemotron;
- C: the Faultline agent on Nemotron via Nebius Token Factory.

A 3×3 variability set and a live smoke test have also run. Every number
below comes from the raw records in `eval/results/`.

## Question

On scenarios it was not developed on, does the Faultline agent reach correct
diagnoses, avoid confident wrong answers, and stop as *inconclusive* exactly
when the permitted instruments cannot separate the causes? How does it compare
with:

- a reasonable deterministic procedure that uses the same tools, and
- a one-shot model that sees only the alarm window?

## Arms

| Arm | What | Information | Fairness note |
|---|---|---|---|
| A | Reference procedure (`agent/baseline.py`), deterministic, not AI | same tools, observations (same seed per scenario), budgets and evaluator as C | written by the same author who designed the scenarios; it encodes the domain logic, so it is a strong comparator |
| B | One-shot Nemotron (`run_oneshot`) | alarm window (E1) only; any tool other than `submit_diagnosis` is refused unexecuted; up to two corrections if the backend rejects the submission | **ablation with less information**, not a fair comparison of investigators |
| C | Faultline agent (`run_investigation` + `NebiusProvider`) | same as A | the system under test |

Budgets for A and C:

- 12 tool calls, with one slot always reserved for `submit_diagnosis`;
- 16 model calls;
- 120 s wall clock;
- 60 s request timeout;
- 2 retries;
- the site's simulated-time allowance.

Retries and rejected calls are charged. B and C use
`nvidia/nemotron-3-super-120b-a12b`; A uses no model and is exempt from the
spending check.

## Scenario sets

* **Held-out, current:** `eval/scenarios/heldout-v2.json`, 26 scenarios,
  SHA-256 `db4e24a67d239cb2ca043ecfba9f6298397d3961258f7698c566e1287a8a5223`,
  frozen 2026-10-26 15:35 UTC.
  - **By true cause:** 3 healthy, 9 pump delivery, 8 leak, 6 stuck sensor.
  - **By condition:** 15 with a missing measurement; **4 not identifiable**
    (storm site: no FT-101, no dip, no stop test, 8 minutes); 2 noisier than the
    datasheet; 6 labelled **model-mismatch** (true tank area, sensor noise,
    LT-101 offset or FT-102 bias differ from the datasheet).
  - **Separation from dev:** it uses site profiles that no dev scenario uses, and
    it satisfies a stated minimum-distance rule against the dev set (see
    `eval/scenarios/FROZEN.md`).
* **Dev:** `eval/scenarios/dev-v2.json`, 16 scenarios (twin pairs at two sites
  and the Blind Challenge presets). Used while writing the prompt, tools and
  reference procedure.
* **Superseded:** `heldout-v1.json` (24) and `dev-v1.json`, kept unchanged.
  An adversarial review found these problems in v1:
  - its oracle under-counted what waiting reveals;
  - its minimum fault sizes were asymmetric;
  - its three non-identifiable cases were near-copies of dev twins.

  The review ran after arm A had been evaluated on v1, and before any model
  evaluation. Full disclosure is in `FROZEN.md`.

## Grading

`judge/evaluator.py` (evaluator-v3) is a pure function of:

- the sealed truth;
- the identifiability label and the oracle's viable alternatives;
- the run status;
- the submitted diagnosis.

| Category | Meaning | Counted correct |
|---|---|---|
| correct_diagnosis | identifiable case, diagnosed family = truth | yes |
| wrong_diagnosis | diagnosed family ≠ truth; *confident* if confidence is medium or high | no |
| appropriate_inconclusive | inconclusive on a case the oracle cannot separate, **keeping the true cause and every viable alternative open** | yes |
| wrong_inconclusive | inconclusive that marked the true cause, or an alternative the instruments could not exclude, as weakened/ruled out | no |
| unnecessary_inconclusive | inconclusive on an identifiable case | no |
| unsupported_diagnosis | any diagnosis on a non-identifiable case (a lucky match is flagged, never counted correct) | no |
| no_result | failed or cancelled run | no |

**Identifiability oracle** (`judge/identifiability.py`, oracle `identifiability-v2`):

1. For every other fault family, it calibrates one hidden parameter on the
   noise-free simulator to match the alarm window.
2. An alternative is viable if both hold:
   - a noisy investigator could not tell its window apart (max LT-101
     difference ≤ 4·√2·σ ≈ 17 mm);
   - its fault is at least 0.05 L/s of missing water, the same for pump and
     leak.
3. A case is identifiable if every viable alternative is separated by at least
   one permitted single test by more than 4σ. For waiting and the pump-stop
   test, this includes the OLS level rate an investigator would fit.

A consequence worth knowing: a worn pump and a calibrated leak can be separated
just by **waiting 15 minutes or more**, because a leak's fall slows as the
level drops. With 10 minutes (night shift) or 8 minutes (storm) they cannot.
The simulator itself is checked against analytic solutions
(`tests/test_physics.py`), so grading does not just inherit an integration
error.

**Remedy check** (`verify_remedy`): the approved maintenance is applied to the
true plant, and a forward copy is then checked over 600 s. A pass needs three
things:

1. delivery − demand − leak within 0.03 L/s of the healthy nominal balance
   (overflow excluded);
2. the LT-101 element within 5 mm of the true level;
3. the applied maintenance is the one the true fault needed, so unnecessary
   maintenance fails.

In the app, this check is sealed until the judge reveals the run. The public
only sees post-maintenance readings.

## Results: arm A, held-out v2 (`eval/results/heldout-v2-A`)

| Metric | Count |
|---|---|
| Correct diagnoses, identifiable cases | **21 / 22** |
| Appropriate inconclusive, non-identifiable cases | **4 / 4** |
| Wrong diagnoses (all confident) | 1 / 26 (V11) |
| Wrong inconclusive | 0 / 26 |
| Unnecessary inconclusive | 0 / 22 |
| Unsupported diagnoses | 0 / 4 |
| No result | 0 / 26 |
| Remedies verified / attempted | 21 / 22 (the failure is V11's wrong remedy) |
| Measurements per run (excluding the alarm-window read), mean | 0.96 |
| Tool calls per run, mean | 2.96 |
| Runtime per run | < 0.02 s |
| Tokens / cost | 0 / $0 (no model) |

Correct or appropriate, by tag:

| Tag | Result |
|---|---|
| healthy | 3/3 |
| pump | 8/9 |
| leak | 8/8 |
| stuck | 6/6 |
| flat reading | 5/5 |
| missing measurement | 14/15 |
| model mismatch | 5/6 |
| ambiguous | 4/4 |
| noisy | 2/2 |

**The one error, V11:** a pump at 71 % of rated flow, with a true tank area of
1.85 m² against 2.0 m² on the datasheet and no FT-101. The procedure stopped
the pump. The level then fell at −31.1 mm/min, faster than the −28.5 mm/min the
datasheet area predicts from the demand. It concluded "leak" with medium
confidence. The same failure mode appeared in v1 (H24). It is the
model-mismatch weakness the held-out set was built to expose: the procedure
trusts the datasheet area.

**Inconclusive cases:** in all four, the procedure read only the alarm window
and named the measurements that would decide. It never used the 8 minutes of
waiting that was allowed. Under the oracle, waiting that long cannot separate
these cases either.

**Dev v2 (`eval/results/dev-v2-A`):** 12/12 correct and 4/4 appropriate
inconclusive. This is expected, since the procedure was written against these
scenarios.

**Superseded v1 records** (kept, not comparable to v2):

- `heldout-A-v1` (evaluator-v1) and `heldout-A-v2` (evaluator-v2): 20/21
  correct, 3/3 inconclusive, 1 wrong (H24).
- The v1 remedy check wrongly failed one correct remedy (H18): it counted
  overflow during the check as missing water. This was fixed in v2.

## Results: arms C and B, held-out v2 (live Nemotron, 2026-10-26)

All runs used `nvidia/nemotron-3-super-120b-a12b` on Nebius Token Factory
(global base URL, reasoning left at the served default). Each scenario ran once
with the same seed as arm A. Raw records:

- `eval/results/heldout-v2-C`
- `eval/results/heldout-v2-B`
- `eval/results/variability-C`
- `eval/results/smoke-C1` (one dev scenario, run first as the smoke test)

### Comparison on the same 26 scenarios

| Metric | A: reference procedure | C: Faultline agent | B: one-shot (ablation) |
|---|---|---|---|
| Correct diagnoses, identifiable (22) | 21 | **22** | 4 |
| Appropriate inconclusive, non-identifiable (4) | **4** | 3 | 4 |
| Correct or appropriate, all 26 | 25 | 25 | 8 |
| Wrong diagnoses (confident) | 1 (1) | **0** (0) | 2 (2) |
| Wrong inconclusive | 0 | 1 (V25) | 0 |
| Unnecessary inconclusive | 0 | 0 | 16 |
| Unsupported diagnoses | 0 | 0 | 0 |
| No result (failed runs) | 0 | 0 | 0 |
| Remedies verified / attempted | 21 / 22 | 22 / 22 | 4 / 6 |
| Measurements per run (excl. E1), mean | 0.96 | 2.35 | 0 |
| Tool calls per run, mean | 2.96 | 6.73 | 1.00 |
| Wall time per run, mean | < 0.02 s | 38.9 s (25.3–59.9) | 5.8 s |
| Prompt / completion tokens (total) | 0 / 0 | 958,348 / 111,326 | 81,544 / 19,592 |
| of which reasoning tokens | – | 82,049 | 9,211 |
| Estimated cost, total (per run) | $0 | $0.388 ($0.0149) | $0.042 ($0.0016) |
| Provider failures | – | 0 | 0 |

**Reading this honestly**

- **C does not outperform A overall.** Both are correct or appropriate on 25
  of 26 scenarios, with different failure modes:
  - A made one confident wrong diagnosis (V11);
  - C made one wrong inconclusive (V25);
  - C made no confident wrong diagnosis.

  C costs about $0.015 and 39 s per investigation, and takes 2.35 measurements
  per run against A's 0.96.
- **V11 is not evidence that C handles model mismatch better.** The true tank
  area there is 1.85 m², against 2.0 on the datasheet.
  - A ran a 240 s pump-stop test. It measured −31.1 ± 0.45 mm/min, precise
    enough to expose the area mismatch, and misread it as a leak.
  - C ran a 60 s stop test. It measured −28.1 ± 2.8 mm/min, which was
    consistent with demand alone, and reached the right answer.

  C was right partly because its test was less precise.
- **C's failure, V25** (pump exactly balancing demand at the storm site, flat
  reading): C waited three times and read slopes of +0.58 ± 0.72,
  +0.47 ± 0.57 and +1.29 ± 7.28 mm/min as "a rising trend". On that basis it
  ruled out a stuck sensor, which the instruments could not exclude. It
  treated noise as signal. The grader counts this as wrong even though the
  final answer was inconclusive.
- **B (one-shot)** sees only the alarm window, so it mostly, and correctly,
  declined to guess: 16 unnecessary inconclusives. It still made 2 confident
  wrong diagnoses (V21, V26). It is an ablation with less information, not a
  fair comparison.
- **Tool use:**
  - C called `predict_under_hypothesis` in 6 of 26 runs.
  - The backend rejected 28 of C's calls across the 36 C-type runs (heldout,
    variability, smoke). 24 of those asked for an instrument or test the site
    had declared unavailable, despite the site conditions in the brief. Four
    were validation errors, for example an inconclusive submission with fewer
    than two open hypotheses, which the agent then corrected.
  - All 275 live model replies were well-formed tool calls. There were no
    text-only replies and no malformed arguments.

### Variability (`variability-C`, same seed, 3 repeats each)

| Scenario | Truth | Identifiable | Outcomes |
|---|---|---|---|
| V04 | pump 72 % | yes | correct ×3 (5, 10 and 6 tool calls) |
| V15 | leak, storm site | no | appropriate inconclusive ×2; **unsupported diagnosis ×1** |
| V19 | stuck sensor | yes | correct ×3 |

The V15 failure: after 4 minutes of waiting, the agent claimed that "steady
decline over 240 s" showed a pump fault rather than a leak. It diagnosed with
medium confidence. Four minutes cannot show the slowing that would separate
them (see the oracle note above). So the honest-inconclusive behaviour is not
stable across repeats on ambiguous cases. The variability set cost $0.152 in
total.

### Cost record

Spend is tracked in `eval/results/spend-ledger.jsonl`, at $0.30 / $0.90 per 1M
tokens from the official catalogue (read 2026-10-26), using the usage that
Nebius reported. It is an estimate, not a Nebius invoice.

| Item | Spend |
|---|---|
| Smoke test | $0.0152 |
| Arm C | $0.3877 |
| Arm B | $0.0421 |
| Variability | $0.1516 |
| **Ledger total** | **$0.5966** |

The run ceiling was $1.50.

The pre-run estimate was "about $0.020 per investigation". The measured value
is $0.0149: about 36.9k prompt tokens and 4.3k completion tokens per C run.

## How to reproduce

```powershell
sha256sum eval\scenarios\heldout-v2.json      # must match the value above
.venv\Scripts\python eval\run_eval.py --set heldout-v2 --arm A --tag my-A
```

Raw per-run records (evidence, events, model calls, grades, remedy checks) are
written to `eval/results/<tag>/<scenario>-r<rep>.json`, with a `summary.json`.
Re-running arm A reproduces the stored evidence exactly; this was checked for
all 24 v1 runs after a simulator refactor.
