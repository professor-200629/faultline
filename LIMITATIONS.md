# Known limitations

Measured or structural limits of this prototype. Where a number is quoted, its
source is named.

## Scope

- **One topology.** One tank (vertical cylinder, flat bottom), one pump, one
  demand outlet, one overflow weir. No piping network, valves, controllers in
  automatic mode, or multiple tanks.
- **Single-fault catalogue.** Four hypotheses: no fault, reduced or failed pump
  delivery, tank leak, stuck LT-101 sensing element. Combined faults, sensor
  drift, valve faults, cavitation, electrical faults and anything else outside
  the catalogue are not modelled. The agent may misdiagnose them or report
  them as inconclusive.
- **Simulated equipment only.** Nothing controls real hardware. Interventions
  change only the simulated plant, within ranges enforced in backend code.
- **Not certified, not field-validated.** Remedies are recommendations for a
  technician. They are verified only against the simulator.

## Physics simplifications (see SIMULATOR.md)

- Pump delivery is independent of tank level (no pump curve or system head).
- Leak follows an ideal orifice law, C·√(h − h_leak), at the tank bottom.
- Demand is constant within a run unless a step change is configured. It stops
  abruptly below the outlet level.
- No temperature, density, evaporation or sloshing effects. Sensor noise is
  Gaussian and independent between samples.

## Evaluation

- **Synthetic data.** All scenarios come from the same simulator that runs the
  investigations. Model-mismatch cases (6 of 26 held-out v2 scenarios) vary true
  plant parameters away from the datasheet; they do not test real-world
  generalisation.
- **Identifiability labels** come from a noise-free, single-test 4-sigma rule
  (judge/identifiability.py, oracle v2, which includes fitted level rates).
  It is a practical rule, not a statistical guarantee. Sequential test
  combinations are not analysed. Whether a worn pump and a leak can be
  separated by waiting depends on how long the site allows: about 15 minutes
  or more separates them; 10 minutes or less does not.
- **The reference procedure was written by the same author** who designed the
  scenarios and the twin pairs. Its high score on held-out v2 (21/22
  identifiable cases correct, 4/4 appropriate inconclusive; see EVALUATION.md)
  reflects that it encodes the same domain logic. It is a strong comparator,
  not an independent expert.
- **Arm A's one error** (V11, and H24 in the superseded v1 set) is a
  model-mismatch case: the true tank area is smaller than the datasheet
  says. With no FT-101 available, the level fell faster during the pump-stop
  test than the datasheet predicts, and the procedure read that as a leak.
- **The held-out set was revised once** (v1 to v2) after an adversarial
  review. That was after arm A had run on v1 and before any model run. The
  revision is disclosed in `eval/scenarios/FROZEN.md`.
- **Live Nemotron results** (arms B and C) depend on a provider key and are
  reported only if actually run. See EVALUATION.md for the current status.
- Confidence labels are qualitative and uncalibrated.

## Interface and product

- Usefulness to maintenance trainees and technicians is **unvalidated**. No
  interviews or user tests have been conducted (USER_RESEARCH.md has the plan).
- Local single-user application. Judge controls trust the loopback address,
  with host-name and origin checks against DNS rebinding. Do not expose the
  server beyond localhost (THREAT_MODEL.md).
- Twin challenges live in server memory. A server restart invalidates any
  unpicked challenge; create a new one.
- English only.

## Model and platform

- Tool-calling quality depends on the model and on Token Factory's parsing.
  It has not been characterised beyond the runs reported in EVALUATION.md.
- **Observed agent failure modes** (EVALUATION.md):
  - it reads noisy slopes as trends (V25 was a wrong inconclusive);
  - on an ambiguous case it sometimes diagnoses instead of staying
    inconclusive (1 of 3 repeats of V15);
  - it asks for instruments the site has declared unavailable (24 rejected
    calls in 36 runs);
  - it rarely uses `predict_under_hypothesis` (6 of 26 runs).
- **C ties A overall** (25/26 each). The measured differences are 0 vs 1
  confident wrong diagnosis, and more measurements, time and cost per run.
  This is not evidence of better reasoning in general.
- The 120 s wall-clock budget per investigation is a configurable default.
  Slower provider responses end a run as *failed (wall-clock budget)*; they are
  not hidden.
- Prices are taken from the official public catalogue on 2026-10-26 and may
  change. Cost figures are estimates from reported token usage.
