# Demonstration script (target 2:50)

## Recorded video

**Public on YouTube: https://youtu.be/Y0bQyq9BvDA** (2 min 54 s, 1080p,
recorded and uploaded on 2026-10-27).

The recording follows the plan below in condensed form. The results come from
a card rather than the About page. What it contains, in order:

| Time | Content |
|---|---|
| 0:00–0:08 | Title card |
| 0:08–0:37 | Twin Challenge: falling-level pair at the standard site, match proof 0.95 mm, one system dealt at random, **Check connection** |
| 0:37–1:07 | LIVE run `65974e5e2ed8160b` (Nemotron 3 Super on Token Factory): historian, dip reading (+1 mm against LT-101), prediction P1, then FT-101 at 0.770 L/s. Real time, apart from one labelled 4.4 s cut while waiting for the model |
| 1:07–1:24 | Diagnosis (reduced pump delivery, high confidence) and budgets: 6 tool calls, 32.2 s, 31,214 / 2,422 tokens, estimated $0.0115 |
| 1:24–1:46 | Approved simulated maintenance, then the judge reveal: worn pump at 62.5 % of rated flow, correct diagnosis, independent remedy check passed |
| 1:46–2:21 | Night shift, flat-reading pair, LIVE run `5521ff9d8a7fc837`: the backend refuses the FT-101 and DIP-101 requests, the agent waits 7 simulated minutes, then reports inconclusive with three causes open. Reveal: appropriate inconclusive, not identifiable with the permitted tests |
| 2:21–2:43 | Held-out results card (numbers from EVALUATION.md) |
| 2:43–2:54 | End card: repository, MIT licence, limitations |

How it was made:

- **Footage:** the app ran on a separate local demo server with its own
  database and a $0.30 spending cap. A scripted headless Chrome captured it at
  1280×640 (1.5× scale). The script only clicks and scrolls.
- **Scrolling during the live run:** the script scrolled the timeline to the
  newest entry. The app does not follow new entries once the timeline column
  first overflows. This is a known UI gap.
- **Night-shift refusals:** the refused requests are shown by scrolling that
  run's timeline after it ended. The clip says so on screen.
- **Live runs:** three were made, $0.048 in total. The first main take
  (`dc982dbaf8ff6cab`) was also a correct pump diagnosis. It was not used
  because its timeline did not scroll to new entries.
- **Narration:** a synthetic voice (Microsoft Heera, Windows text-to-speech),
  written after the runs from their recorded evidence. Captions are burned in,
  and there is no music.
- **Upload:** a 9.2 MB two-pass encode, because the browser upload tool
  accepts at most 10 MB.
- **Scripts:** the recording and assembly scripts are not in this repository.

## Plan (written before recording)

The LIVE segment (0:30–1:45) needs a real Nemotron run. The rules ask the video
to show Token Factory and Nemotron in use, so do not substitute the reference
procedure for that segment. If it is shown at all, it must keep its
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
  when logged out. Done on 2026-10-27 (link above).
