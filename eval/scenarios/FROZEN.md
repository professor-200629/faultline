# Frozen evaluation sets

| file | scenarios | sha256 | frozen at (UTC) | status |
|---|---|---|---|---|
| **heldout-v2.json** | 26 | db4e24a67d239cb2ca043ecfba9f6298397d3961258f7698c566e1287a8a5223 | 2026-10-26T15:35Z | **current held-out set** |
| dev-v2.json | 16 | 1c20d9c87e856d1af7c4b79b2045c1ec9af840a658f50ad6c254d15b0c71b553 | 2026-10-26T15:35Z | current dev set |
| heldout-v1.json | 24 | 4e4983ec4c37b86f92083063fc8b7c39c30ebd466115e5f1a0815edd3d567fcd | 2026-10-26T14:58Z | superseded (kept unchanged) |
| dev-v1.json | 16 | 392cb1067df2e6aa0f47506cd2a9101284d473e6c40e85bbd7a692961d910748 | 2026-10-26T14:58Z | superseded (kept unchanged) |

Verify with `sha256sum eval/scenarios/<file>`.

## Why v2 exists (disclosure)

An adversarial review on 2026-10-26, after arm A (the deterministic
reference procedure) had run on heldout-v1 and before any Nemotron
evaluation, found:

1. **The v1 oracle under-counted what waiting can reveal.** It compared only two
   end-point readings. Over 20 minutes an orifice leak's fall measurably
   slows, while a worn pump's fall does not. Oracle v2 also compares the
   OLS rate an investigator would fit. With v1's 20-minute night-shift
   allowance, v1's "non-identifiable" pump-vs-leak cases (H08, H13) are
   separable in principle. The app's night-shift profile is now 10 minutes,
   where they are not.
2. **Asymmetric minimum fault sizes** (pump 0.12 L/s vs leak 0.05 L/s) could
   label observational twins differently. v2 uses 0.05 L/s for both.
3. **v1 held-out cases were near-copies of dev cases**, including all three
   non-identifiable ones, which reused dev's night-shift site object. v2 uses
   held-out-only site profiles (standard2, remote, hatch, storm) and a stated
   minimum-distance rule checked by `eval/make_scenarios.py`:
   *"A held-out scenario is too close to a dev scenario when both have the same
   fault family AND the same instrument availability (FT-101, DIP-101, stop
   test) AND every one of these differs by less than its margin: alarm-window
   LT-101 deviation from the nominal balance (1.5 mm/min), FT-102 demand
   (0.10 L/s), first logged LT-101 level (0.15 m)."*
   Four first-draft v2 scenarios violated the rule (V01, V07, V16, V25). Their
   parameters were moved before the file was written. No results existed for
   any v2 scenario at that point.
4. **FT-101 timing changed** (the clamp now takes 30 s to fit and settle) and all
   actions now stay on the 10 s historian grid. Measurements in v2 runs are
   therefore not comparable to v1 runs.

v1 files and their arm A results (`eval/results/heldout-A-v1`, `heldout-A-v2`)
are kept unchanged for the record. Earlier v1 history: the v1 files were
regenerated twice before any evaluation, to change the window-viability rule
and to write LF line endings.

v2 was written by `eval/make_scenarios.py` at 15:35 UTC. Arm A ran on it at
15:36 UTC (`eval/results/heldout-v2-A`). No Nemotron run had happened on any
set when v2 was frozen.
