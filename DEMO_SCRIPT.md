# Demonstration script (target 2:50)

**Footage status: NOTHING HAS BEEN RECORDED.** The LIVE segment (0:30–1:45)
needs a real Nemotron run. Live runs now work: the key was configured on 2026-10-26, and
`replays/live-nemotron-twin-falling-level.json` is a recorded example. The rules ask
the video to show Token Factory and Nemotron in use, so do not substitute the
reference procedure for that segment. If it is shown at all, it must keep its
"REFERENCE PROCEDURE · not AI" badge on screen and be described as such.

Recording setup:

- Browser at 1280×720 on `http://127.0.0.1:8000` (`scripts\start.ps1`), dark
  theme, zoom 100%.
- Start with a fresh database (`data\faultline.db` removed) so the runs list is
  clean.
- No music. Voice-over only, or captions.
- Physical AI rule: at least 1 continuous minute of the application modules in
  action. Here that is 0:30–2:35.

| Time | Screen | Action | Narration (about 150 words per minute) |
|---|---|---|---|
| 0:00–0:12 | Twin Challenge (`#/twin`), falling-level pair, standard site, **Build the twin pair** | Cards α and β appear with the same BAL-101 warning; scroll to the overlay and the match proof | "These two tanks show the same warning. Same level trend, same demand, same pump signals: the noise-free difference is under one millimetre. Their faults are different." |
| 0:12–0:30 | Same page | Point at the *Candidate causes* box; click **Deal one at random — nobody knows** | "One has a worn pump, the other a leak. The server deals one at random and seals the answer. Not even we know. FAULTLINE has to earn the diagnosis." |
| 0:30–0:45 | Workstation; top-right chip shows *Nebius Token Factory · nvidia/nemotron-3-super-120b-a12b · key configured* | Click **Check connection**, then **Start LIVE investigation** | "The investigator is NVIDIA Nemotron 3 Super on Nebius Token Factory. It never sees the plant, only the readings it asks for." |
| 0:45–1:25 | Timeline + equipment + trends | Let the run play. Pause on: the agent's first `read_observations` (E1); any `predict_under_hypothesis` card (violet, *not evidence*); the chosen test (FT-101 or pump stop) with its purpose text; the evidence card; the hypothesis board updating | Narrate what *actually* happens in the recorded run, for example: "It asks what each hypothesis predicts, then fits the clamp-on meter: 1.2 litres a second, full pump delivery. So the pump is fine, and the missing water is a leak. Every number comes from the simulator, and every claim cites an evidence ID." (Replace with the real run's values.) |
| 1:25–1:45 | Diagnosis card + budget meters | Point at the supporting/contradicting evidence chips and the token/cost meter | "Its diagnosis lists what supports and what contradicts each cause. This run used N tool calls, M tokens, about $X." (Use real numbers from the run.) |
| 1:45–2:05 | Run controls → **Approve simulated maintenance**, then **Reveal ground truth (judge)** | Show post-maintenance readings, then the amber judge-only panel: true cause, grade, twin mapping, omniscient chart | "Diagnosis is separate from repair: only an approved simulated action changes the plant. Afterwards, the judge reveals the truth, which was kept on the server the whole time." |
| 2:05–2:35 | Twin Challenge again, flat-reading pair, **night shift** site → deal → start | Run ends **inconclusive**; zoom to *evidence needed* | "Now the limitation. On night shift there's no flow meter, no dip tape, and the pump can't stop. A stuck sensor and a pump that exactly matches demand look identical, so FAULTLINE says *inconclusive* and names the measurement that would decide, instead of guessing." |
| 2:35–2:50 | EVALUATION.md or About page | Show the results table | "On 26 frozen held-out scenarios, Nemotron got 22 of 22 solvable cases right with no confident wrong answers, and 3 of the 4 honest inconclusives. A hand-written reference procedure scored the same overall, so we report that too. It's a simulation prototype, not field-validated, and untested with users. Code is MIT on GitHub." |

## Fallbacks and rules

- If the live run fails (provider error, timeout, budget), **show the failure**.
  It is a real state of the product. Then re-record. Never edit a failure into a
  success.
- A REPLAY of an earlier live run may be used for 0:45–1:25 only if the
  on-screen **REPLAY** banner stays visible and the narration says "a recorded
  run".
- Every number spoken must be visible on screen or present in EVALUATION.md
  at recording time.
- Upload as **public** on YouTube, under 3 minutes, and check that it plays
  when logged out. This is a pending owner action.
