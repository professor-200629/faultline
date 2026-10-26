# FAULTLINE user research plan

**Status (2026-10-26): no interviews or user tests have been conducted.** Whether FAULTLINE is useful to maintenance trainees or technicians, and whether they would use it, are unvalidated hypotheses.

FAULTLINE is a simulation prototype. It is not certified industrial software, and its output is not field-validated maintenance advice. Live runs with NVIDIA Nemotron on Nebius Token Factory have not happened yet: no API key was configured as of 2026-10-26. Until live runs exist, every session would show runs from the deterministic reference procedure, which the app labels "REFERENCE PROCEDURE" with the subtitle "deterministic, not AI".

This plan is for whoever moderates sessions with maintenance trainees and technicians who investigate small pumping systems (a pump filling a tank that serves a demand).

Contents:

1. What participants will see
2. Hypotheses to test
3. Recruiting and consent
4. Interview guide (25 minutes)
5. Usability test script (20 minutes)
6. Recording results and how they would change the product
7. Current results: none

---

## 1. What participants will see

This section is taken from the code so moderators know what is on screen. Paths are relative to the repository root.

| Item | What it is | Source |
|---|---|---|
| T-101 | Tank: vertical cylinder, 2.0 m² cross-section, 2.5 m tall, overflow weir at 2.40 m | `backend/faultline/sim/spec.py` |
| P-101 | Pump from a supply sump into T-101, rated 1.20 L/s, delivery time constant 5 s. Its run feedback reports the motor contactor, not delivered flow | `spec.py` |
| LT-101 | Level transmitter, logged every 10 s | `spec.py` |
| FT-102 | Demand (outlet) flow meter, logged | `spec.py` |
| FT-101 | Portable clamp-on inlet flow meter, only if the site has one. Fitting the clamp and letting the reading settle takes 30 s, then the reading is averaged over 30–300 s; both count against the site's time allowance | `spec.py`, `sim/case.py`, `instruments.py` |
| DIP-101 | Manual dip-tape level reading through the roof hatch; takes 120 s of simulated time | `spec.py` |
| P-101 stop test | Stop the pump for 60–300 s per test, on sites that permit it | `sim/case.py`, `instruments.py` |

Waiting times, FT-101 averaging times and stop-test holds must be multiples of 10 s, the historian interval, so every action starts and ends on a logged LT-101 sample (`instruments.py`, `agent/tools.py`). Each site limits the extra simulated time an investigation may use: 1800 s (30 minutes) unless the site profile sets less (`SiteConditions` in `sim/case.py`).

Candidate causes, one fault at a time: no fault, reduced pump delivery, tank leak, LT-101 stuck (`FAMILIES` in `sim/case.py`).

**Twin Challenge** (`sim/twins.py`, `frontend/src/pages/TwinChallenge.tsx`). Two simulated systems with different causes whose 15-minute alarm windows match (noise-free LT-101 difference within 2 mm, `TWIN_TOL_LT_M`, FT-102 difference within 0.005 L/s, and identical P-101 signals; `window_deviation()` in `judge/identifiability.py`). The page overlays both windows (previews with independent noise), names the two candidate causes, and lets the moderator pick System α, System β, or one at random. The pick creates a sealed run with a fresh noise seed and opens it on the workstation, ready to start; it does not start the investigation. Each challenge can be used once. Challenges are held in server memory (`runtime.py`), so a backend restart discards them.

- `falling-level`: P-101 delivering 62.5% of rated flow with no leak, or a healthy P-101 with a leak calibrated to the same trend. FT-101 or a P-101 stop test separates them. Waiting separates them only if it is long enough: the leak's outflow drops as the level drops, so its fall slows, while the worn pump's fall keeps the same rate. FAULTLINE's separability check (`separation()` in `judge/identifiability.py`) finds the change of rate separable after 900 s of waiting (0.50 mm/min against a threshold of 0.41 mm/min) but not after 600 s (0.42 against 0.61). These figures come from a one-off check on 2026-10-26 and are not stored in a results file. A dip reading does not separate them, because both level sensors are healthy.
- `flat-reading`: LT-101 stuck at 1.80 m while the true level rises, or P-101 delivering exactly the demand (83% of rated). A dip reading, FT-101 or a stop test separates them. Waiting does not, however long, because nothing observable changes.

**Blind Challenge** (`sim/presets.py`, `frontend/src/pages/BlindChallenge.tsx`). The moderator, in a judge session, picks a cause, a severity and a site profile. The server builds the case and the browser receives only an opaque run ID. Site profiles: `standard`, `no_inlet_meter`, `no_independent_level`, `night_shift`.

**Night shift** (`AMBIGUOUS_SITE` in `sim/twins.py`): no FT-101, no dip reading, P-101 must keep running, and at most 600 s (10 minutes) more simulated time. Waiting is the only test left. For the `falling-level` pair, ten minutes is too short to separate the worn pump from the leak by the slowing of the fall (see `falling-level` above). This does not hold for every case: for larger faults (the `tank_leak` / `large`, `pump_delivery_reduced` / `severe` and `pump_delivery_reduced` / `failed` presets) the identifiability check finds that 600 s of waiting does separate pump from leak (one-off check on 2026-10-26, not stored in a results file; see step 5 of "Before each session").

**Workstation** (`frontend/src/pages/Workstation.tsx`, `frontend/src/components/`):

- Equipment view: the tank fill is the LT-101 *indicated* level (hatched, labelled "indicated"). The pump always shows "delivered flow: unknown unless measured"; once FT-101 is measured, its value appears beside the clamp (`Equipment.tsx`).
- Timeline: evidence items E1, E2, ... Model-based expectations appear as P1, P2, ... labelled "model-based expectation — not evidence".
- Hypothesis board: the four causes, each open, supported, weakened or ruled out, with evidence chips that jump to the timeline.
- Outcome: `diagnosed` or `inconclusive`. An inconclusive outcome must name the measurement that would decide, must recommend no remedy until more evidence, must leave at least two causes open or supported, and must cite contradicting evidence for any cause it marks weakened or ruled out (`agent/tools.py`). The timeline shows the request as "evidence needed".
- After a diagnosis that recommends maintenance (not `no_action`), the run waits at "awaiting approval" and the user approves or declines the simulated maintenance. If approved, the maintenance is applied to the simulated plant and the timeline shows what the public instruments logged over the next 300 s: the LT-101 trend against the nominal balance, the FT-102 mean, and any alarm still active, labelled "Public measurements, not ground truth" (`post_maintenance_observation` in `instruments.py`, `frontend/src/components/Timeline.tsx`). The independent evaluator's check of the true simulated plant is stored sealed and is not shown at this point (`runtime.py`). It appears only in the reveal panel. The check fails if the plant is not healthy afterwards, and also if the maintenance applied was not the one the true fault needed, for example maintenance on a plant that had no fault (`verify_remedy` in `judge/evaluator.py`).
- A reveal panel shows the true cause, the grade and, for an approved run, the sealed maintenance check, once a terminal run is revealed (`frontend/src/components/RevealPanel.tsx`). Revealing needs a judge session, except for the guided example.

Limits that affect the sessions:

- In reference mode the procedure never calls `predict_under_hypothesis` or `update_hypotheses` (`agent/baseline.py`). No P# cards appear, and the hypothesis board shows only what the submitted diagnosis says.
- The reference procedure never waits to watch the trend; it uses FT-101, then a dip reading (only while a stuck LT-101 is still possible), then a stop test, as the site allows (`agent/baseline.py`).
- Reference runs finish almost at once (`mean_wall_s` 0.0, rounded to 0.01 s, in `eval/results/heldout-v2-A/summary.json`, the arm A run on the current held-out set `heldout-v2`). "Watching the investigation" therefore means walking through the finished timeline, or the replay view (`#/run/<id>/replay`) if it works in the build used. Replay and reveal are available only for terminal runs (`diagnosed`, `inconclusive`, `failed`, `cancelled`); a run at "awaiting approval" is not terminal until the user approves or declines.
- The frontend was still being written when this plan was drafted. Check every page used below in a pilot session.

---

## 2. Hypotheses to test

Each hypothesis states what would falsify it. The thresholds are decision rules set in this plan before any data exists, written for a group of n participants (the example uses n = 6). They are not estimates, and with groups this small the results are qualitative signals, not statistics.

| ID | Hypothesis | Tested in | Falsified if |
|---|---|---|---|
| H1 | After the Twin Challenge, trainees can explain in their own words why the alarm-window readings alone cannot separate the twins and why a second measurement is needed. | Task 1, criterion 1c | Fewer than two thirds of trainees (fewer than 4 of 6) meet 1c without a prompt. |
| H2 | Before seeing the investigation, some trainees pick a test that does not separate the `falling-level` twins (for example a dip reading) or cannot say what each cause would show. This is the learning gap the Twin Challenge assumes. | Task 1, criterion 1b | All trainees, or all but one, meet 1b unaided. The challenge would then have little to teach this group. |
| H3 | Technicians trust a diagnosis more, and can check it, when its claims cite evidence IDs that point to measurements. | Task 2, variant A vs B, item T2.1, criterion 2b | Fewer than half of variant A participants use an evidence ID to check a claim, or trust ratings and comments show no difference between variants. |
| H4 | Participants read an inconclusive outcome as a request for a specific measurement, not as a software failure. | Task 3, criteria 3a and 3b, item T3.2 | A third or more of a group (2 or more of 6) describe it as an error or failure, or fewer than two thirds (fewer than 4 of 6) can name the requested measurement. |
| H5 | The equipment view does not lead users to think the true tank level is known. | Task 3, criterion 3c, item T3.3 | A third or more of a group (2 or more of 6) state the LT-101 reading as the actual level without qualifying it. The threshold is lower because this misreading leads to wrong conclusions. |
| H6 | Participants can tell model-based expectations (P#) from measurements (E#). | Task 2, question 4 | Fewer than two thirds can say which items are measurements. **Not testable in reference mode** (no P# items); test only after live runs exist. |
| H7 | Most incidents technicians describe on small pumping systems fit one of the four modelled causes. | Interview part B | Fewer than half of the described incidents fit one of the four (for example they involve valves, air locks, blocked strainers, controls, or more than one fault at once). |
| H8 | Technicians look at the evidence before approving the simulated maintenance, rather than approving by default. | Task 2, observation 2d | More than half approve without opening or pointing to any evidence item. |
| H9 | Trainees and instructors would use the Twin Challenge in training. | Final items F1 and F5 | Fewer than half of a group answer 4 or 5 on F1 and name a concrete place in their training where they would use it. |

---

## 3. Recruiting and consent

### Who

| Group | Description | Planned per round |
|---|---|---|
| G1 Trainees | Maintenance apprentices or vocational students who have started work on pumps, tanks or instrumentation | 5–6 |
| G2 Technicians | People who currently investigate faults on small pumping systems (for example water supply, building services, small process skids) | 5–6 |
| G3 Instructors (optional) | People who teach fault-finding to G1 | 2–3 |

About five participants per round is a common rule of thumb for finding usability problems (Jakob Nielsen, "Why You Only Need to Test with 5 Users", Nielsen Norman Group, 18 March 2000, https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/, read 2026-10-26). It does not support rates, percentages or statistical claims.

### Screener

1. Role: trainee or apprentice / technician / instructor / other.
2. Time working with or training on pumps and tanks: none / under 1 year / 1–5 years / over 5 years.
3. Kinds of systems worked on (open answer, no employer or site names).
4. Are you 18 or over? (Required: yes.)
5. Have you worked on or helped build FAULTLINE? (Exclude if yes.)
6. Are you comfortable reading English on a screen? (The interface is in English.)

### How to recruit

- Reach people through training providers, apprenticeship programmes or maintenance contacts who agree to pass on an invitation. Do not collect contact details from websites or social media.
- If sessions run through a college or employer, follow its research ethics process first. None has been sought as of 2026-10-26.
- If any incentive is offered, decide it before recruiting, state it in the information sheet, give the same to everyone, and never make it depend on what the participant says.

### Consent

Before the session, give a plain-language information sheet that covers: the purpose; what the participant will do; how long it takes (about 50 minutes); that FAULTLINE is a simulation and nothing in the session is maintenance advice for real equipment; that taking part is voluntary and they can stop at any time without giving a reason; what is recorded, where it is stored, who sees it and how long it is kept; and how to withdraw their data, with the date after which withdrawal is no longer possible.

Ask for consent separately for each item and record each answer:

| Item | Default |
|---|---|
| a. Take part, with written notes | Required to take part |
| b. Audio recording | No |
| c. Screen recording (screen only, no faces) | No |
| d. Use of anonymised quotes in write-ups | No |

Rules:

- **No recording of any kind without a recorded "yes" to b or c, obtained before recording starts.** If the participant says no, run the session with notes only.
- Ask participants not to name employers, sites, colleagues or confidential incidents. If they do, the note-taker leaves it out.
- **No personal data goes in the repository**: no names, emails, phone numbers, employers, site names, signatures, consent forms, recordings, or the key that links participant codes to people. Keep these outside the repository, with access limited to the research team, and delete recordings once the notes have been checked or as the consent form says.
- Use participant codes only (P01, P02, ...). Keep the code-to-person key in a separate place from the notes.
- Tell participants: "We are testing the software, not you. There are no wrong answers."

---

## 4. Interview guide (25 minutes)

Run the interview **before** the usability test, so the software does not shape how participants describe their own practice. Do not describe FAULTLINE before or during the interview.

Moderator rules: ask open questions; follow up with "Tell me more", "What happened next?", "Why?"; do not suggest answers; do not agree or disagree; ask about real past events rather than hypothetical ones.

| Time | Part | Questions |
|---|---|---|
| 0:00–2:00 | Start | Confirm consent answers. "I'll ask about how you deal with problems on pumps and tanks. Please don't name employers, sites or people." |
| 2:00–6:00 | A. Warm-up: how they troubleshoot today | A1. Tell me about the pumping systems you work on or have trained on. A2. When a tank level warning comes in, what happens? Walk me through the last time. A3. Who else is involved, and who decides what to do? |
| 6:00–13:00 | B. Recent incidents | B1. Think of the last time a tank level looked wrong. What happened? Follow-ups: What did you check, and in what order? What turned out to be the cause? How long did it take? B2. Ask each in the same form: Has there been a case where the reading turned out to be the problem? A case where the pump ran but the cause was the pump? A case where water was being lost? A case where the cause was something else? What happened in each? B3. Was there a time you were sure of the cause and it turned out to be something else? What misled you? |
| 13:00–18:00 | C. Deciding what to measure | C1. When more than one cause fits what you see, how do you decide what to check next? C2. What stops you taking a measurement you would like to take? C3. How do you decide you know enough to act? C4. What do you do when you cannot tell? What do you write down, and who do you tell? |
| 18:00–21:00 | D. Tools | D1. What instruments and tools do you use for this? Which do you carry, and which are on site? D2. What software, if any, is involved, for example for trends or work orders? D3. How do you record what you found? |
| 21:00–24:00 | E. Trust in software suggestions | E1. Has a system or piece of software ever suggested a cause or an action to you? What happened? E2. What made you follow it or ignore it? E3. If software told you the likely cause, what would you want to see before acting on it? |
| 24:00–25:00 | Close | "Is there anything about finding these faults that I should have asked?" |

For H7, the note-taker classifies each incident from part B as: sensor, pump delivery, leak, no fault, or other (name it). Record "unclear" rather than guessing.

Questions to avoid, and why:

| Avoid | Problem | Ask instead |
|---|---|---|
| "Would it help if software showed the evidence behind its diagnosis?" | Suggests the answer; it is the thing H3 tests | E3 |
| "Sensors are often the cause, aren't they?" | Leading | B2, asked the same way for each cause |
| "How useful would a tool like FAULTLINE be?" | They have not seen it; invites politeness | F1–F5 after the test |
| "Do you ever get it wrong?" | Feels like a judgement of the person | B3 |

---

## 5. Usability test script (20 minutes)

This is a template. Pilot it with one person outside the target groups first, and adjust timings and wording before the first real session.

### Before each session (not counted in the 20 minutes)

1. Start the backend and frontend. Confirm that LIVE is shown as unavailable (no `NEBIUS_API_KEY` configured) and that runs are started with "Start reference procedure"; a started run shows the "REFERENCE PROCEDURE" badge. Record the build: the commit hash if one exists (the repository had no commits on 2026-10-26), otherwise the date and a note of what was running.
2. Use the computer that runs the backend, and open the app by a loopback address (`127.0.0.1` or `localhost`; the frontend dev server listens on `127.0.0.1:5173`, `frontend/vite.config.ts`). The backend answers only requests addressed to a loopback host name and refuses state-changing requests from a page on any other origin (`api.py`), so the app cannot be opened from a second device. Judge controls (creating Twin and Blind runs, reveal) also work only from that computer (loopback clients only, `api.py`); the page requests the judge session itself.
3. **Task 1:** create a Twin Challenge for `falling-level` with site profile `standard`. Leave the page showing both alarm windows. Do not pick yet. A challenge can be used once and does not survive a backend restart, so create a new one for each participant, shortly before the session. Use the same pair for everyone in a round.
4. **Task 2:** create a Blind run with an identifiable preset, for example `tank_leak` / `large` / `standard`. Start it in reference mode and let it reach "awaiting approval". Do not reveal it. Create one run per participant, because approval can be given only once per run. Export its report (`/api/runs/<id>/report.md`) and print it as variant A. For variant B (H3), print the same report with every evidence ID and citation blacked out, keeping the measured values. Alternate A and B across participants and record which one each person saw.
5. **Task 3:** create a Blind run with site profile `night_shift` and a preset that the identifiability check marks as not identifiable. On 2026-10-26, `identifiability()` in `backend/faultline/judge/identifiability.py` (oracle version `identifiability-v2`, which also judges what waiting reveals, with the 600 s night-shift allowance) returned `identifiable: False` for these three night-shift presets: `level_sensor_stuck` / `true_level_rising`, `tank_leak` / `small`, `pump_delivery_reduced` / `mild`. The other five night-shift presets returned `True`. This was a one-off check and is not stored in a results file. Re-check it before use, from `backend/`:

   ```
   python -c "from faultline.sim.presets import build_preset; from faultline.judge.identifiability import identifiability; print(identifiability(build_preset('level_sensor_stuck', 'true_level_rising', 'night_shift'))['identifiable'])"
   ```

   Then run the case in reference mode before the session and confirm it ended `inconclusive`. If it did not, try another of the three. `level_sensor_stuck` / `true_level_rising` is preferred because it also tests H5: LT-101 reads flat while the simulated true level rises.
6. Do not show the Guided page or its coach marks. They explain points that H3, H4, H5, H6 and H8 test (evidence IDs, inconclusive outcomes, the indicated level, predictions, approval).

### Introduction (0:00–2:00)

"Today you'll look at a simulated tank and pump. Nothing here is advice for real equipment. Please think aloud: tell me what you're looking at, what you expect and what confuses you. The investigations you'll see were produced by a fixed rule-based procedure, not by an AI model." (If a later round uses live mode, say so instead, and record the mode on the sheet. Trust results from reference-mode sessions do not tell us how people would respond to Nemotron's output.)

### Think-aloud prompts (use only these, neutrally)

- "What are you looking at now?"
- "What are you thinking?"
- "What do you expect to happen?"
- "Please keep talking."
- After a silence of about 10 seconds: "What's on your mind?"

Do not confirm or correct answers during tasks. Reply to questions with "What do you think?" Answer only questions about operating the interface.

### Task 1: Twin Challenge (2:00–9:00)

Say: "This screen shows two simulated tank systems, System α and System β. Both raised the same warning. Each has a different fault."

1. "What do you notice about the two systems?"
2. "The candidate causes are listed here. If you could take one more measurement or test, which would you choose to tell the two systems apart?"
3. "What result would you expect for each cause?" Write the prediction on the sheet before continuing.
4. Click "Deal one at random — nobody knows". The run opens on the workstation, not yet started. Click "Start reference procedure". The run finishes almost at once and stops at "awaiting approval"; leave it there. "The investigation has finished. Please walk me through what it did."
5. "Why did it take that measurement?"
6. "Could it have decided from the first 15 minutes of readings alone? Why or why not?"
7. "Would the test you picked have told them apart?"

Success criteria (score each as met unaided / met after a prompt / not met):

- **1a** States that the two alarm windows look the same or cannot be told apart by eye.
- **1b** Predicts a separating test and the expected result for each cause. For `falling-level`: FT-101 would read about 0.75 L/s (62.5% of 1.20 L/s) for the worn pump and about 1.20 L/s for the healthy pump with a leak; or, with P-101 stopped, the level would fall at the rate FT-102 demand explains for the worn pump and faster than that for the leak; or, after waiting at least 15 minutes (the `standard` site allows 30 minutes), the fall would keep the same rate for the worn pump and slow slightly for the leak (see `falling-level` in section 1). Choosing a dip reading does not meet 1b.
- **1c** After the run, explains in their own words that the first readings fit both causes, so a second measurement was needed.

Post-task items (1 = strongly disagree, 5 = strongly agree):

- T1.1 I could tell what each test would show before the investigation ran.
- T1.2 The first 15 minutes of readings were enough to tell the two systems apart. *(Comprehension item: the expected answer is 1 or 2.)*
- T1.3 I could follow why the investigation chose its measurement.

### Task 2: Blind Challenge report (9:00–14:00)

Say: "This is the report from a finished investigation of another simulated system. I chose the fault. It is hidden from you and was hidden from the investigation." Hand over the printed report (variant A or B).

1. "In your own words, what does it say is wrong?"
2. "How sure is it, and how can you tell?"
3. "Show me what was measured that supports that."
4. (Only if the report contains P# items; skip in reference mode.) "Is anything here not a measurement?"
5. Open the run on screen, with its status at "awaiting approval". "The report recommends a simulated maintenance action. What would you do here?" Let them approve or decline. If they approve, the timeline then shows 300 s of LT-101 and FT-102 readings logged after the simulated maintenance. The evaluator's pass or fail check of the true plant is not shown until the run is revealed.
6. "What does approving do?"

Success criteria:

- **2a** States the outcome and the primary cause as the report gives them.
- **2b** Points to at least one evidence item that supports the main claim (by ID in variant A, by description in variant B) and says what was measured.
- **2c** States that approval acts on the simulation only, and that nothing happens to real equipment.
- **2d** Observation, not pass or fail: did they open or point to any evidence item before approving or declining?

Post-task items:

- T2.1 I trust this diagnosis enough to act on it in a training exercise.
- T2.2 I could find the measurement behind each claim in the report.
- T2.3 The report sounds more certain than its evidence supports.

If time allows, reveal the ground truth and ask: "Does this change how you see the report?" If they approved, the reveal panel also shows the evaluator's check of the maintenance. Record that the reveal happened.

### Task 3: Night-shift inconclusive case (14:00–18:00)

Open the prepared night-shift run on the workstation. Say: "This is a third investigation. Please read the site note first."

1. With the equipment view visible, before they read the outcome: "What is the water level in T-101 right now?" Then: "How do you know?"
2. "What did the investigation conclude?"
3. "What is it asking for?"
4. "What would you do next on this shift?"
5. "Is this result useful to you? Why or why not?"

Success criteria:

- **3a** Describes the outcome as undecided and names the requested measurement, or an equivalent, without help. In reference mode the request lists alternatives (an FT-101 inlet-flow reading, an independent dip reading when a stuck LT-101 is still possible, or permission for a short P-101 stop test, `agent/baseline.py`); naming any one counts.
- **3b** Does not describe the outcome as a crash, an error or the software failing.
- **3c** Gives the level as the LT-101 reading and qualifies it (for example "the sensor says", "indicated"), or says the true level is not known.
- **3d** Observation, not pass or fail: does the proposed next step respect the site note (P-101 must keep running; no clamp meter or dip reading available; at most 10 more minutes)? Waiting out the 10 minutes respects the note, but for the three presets in step 5 of "Before each session" the identifiability check found that it does not decide the case.

Post-task items:

- T3.1 The result told me what to do next.
- T3.2 The result felt like the software had failed.
- T3.3 I knew the actual water level in the tank. *(Comprehension item: the expected answer is 1 or 2.)*

### Final questions (18:00–20:00)

- F1 I would use the Twin Challenge in training. (1–5)
- F2 I would use a tool like this when investigating a real pumping system. (1–5)
- F3 At work, I would ignore suggestions like the ones I saw today. (1–5)
- F4 What one thing would you change?
- F5 Where, if anywhere, would this fit in your training or work?

Thank the participant and confirm how to withdraw their data.

### Observation sheet (one per task)

| Field | Content |
|---|---|
| Participant code | P01, P02, ... |
| Group | G1 / G2 / G3 |
| Session | S1, S2, ... |
| Moderator / note-taker | Role codes only (M1, N1) |
| Build and mode | Commit or date; reference or live |
| Task and variant | T1 (pair), T2 (A or B), T3 (preset) |
| Start and end time | mm:ss |
| Prediction (Task 1) | Test chosen; expected result per cause |
| Success criteria | Each: met unaided / met after a prompt / not met |
| Prompts given | Count and wording |
| Where they looked or clicked | For example timeline, evidence chip, equipment view, site note |
| Misreadings | What they believed and what the screen showed |
| Issues | Description and severity (1 = cosmetic; 2 = slows or confuses, recovers; 3 = leads to a wrong conclusion) |
| Comments | Paraphrased. Verbatim only with consent item d. |
| Post-task ratings | T-items |

---

## 6. Recording results and how they would change the product

### Notes file template

One file per session, named `<participant code>-<session>.md` (for example `P03-S1.md`). Raw notes stay outside the repository. An anonymised copy may be added to the repository (proposed folder: `research/notes/`, not yet created) only after a second team member has checked it for names, employers, sites, colleagues and identifying incident details.

```markdown
# P03-S1

- Group: G2
- Date: YYYY-MM-DD
- Build: <commit or date>; mode: reference
- Consent: notes yes; audio no; screen no; quotes no
- Checked for identifying details by: N1 on YYYY-MM-DD

## Interview
- Incidents (H7), one line each: <classification> - <short anonymised description>
- How they decide what to measure:
- Tools:
- Trust and ignore reasons:

## Task 1 (pair: falling-level)
- Prediction: <test>; expected: <result per cause>
- 1a / 1b / 1c: <met unaided | met after prompt | not met>
- Issues (severity):
- T1.1 / T1.2 / T1.3:

## Task 2 (variant: A or B)
- 2a / 2b / 2c:
- 2d (looked at evidence before approving): yes/no
- Approved or declined:
- T2.1 / T2.2 / T2.3:

## Task 3 (preset: ...)
- Level answer (3c), paraphrased:
- 3a / 3b / 3c:
- 3d next step:
- T3.1 / T3.2 / T3.3:

## Final
- F1 / F2 / F3:
- F4:
- F5:
```

### Analysis

- For each hypothesis, report "k of n" per group against the rule in section 2. Do not convert groups smaller than 10 into percentages.
- List usability issues with severity and the number of participants who hit each one.
- Group interview notes by theme. Report the H7 incident classification as counts per category.
- Keep sessions run in reference mode separate from any later live-mode sessions.

### How results would change the product

These are candidate changes, decided only after a full round, and re-tested in the next round.

| If | Then |
|---|---|
| H5 falsified (users read the indicated level as the true level) | Fix the equipment view before other work. Options: drop the tank fill and show only a labelled LT-101 reading, or show the reading as a marker labelled "LT-101 says". |
| H4 falsified | Reword the inconclusive outcome so the requested measurement comes first. |
| H1 falsified | Add a prediction step to the Twin Challenge page before the pick, and show the expected result for each cause after the run. |
| H2 falsified (no learning gap) | Do not aim the Twin Challenge at that group. Try harder pairs or less experienced trainees. |
| H3 falsified | Evidence IDs are not helping. Try putting the measured value next to each claim instead of an ID. |
| H8 falsified (approval by default) | Show the cited evidence inside the approval step. |
| H7 falsified (most real incidents fall outside the four causes) | State the four-cause, single-fault limit prominently in the app and documents. Rank the missing causes by how often they were reported before adding any. |
| H9 falsified | Reconsider who FAULTLINE is for before building more for that group. |
| H6 | Test only after live runs exist. |

---

## 7. Current results: none

As of 2026-10-26, no participant has been recruited, no session has been run, and no notes exist. Nothing in the README, slides, video, demo script or submission may say or imply that trainees or technicians have used, tested, validated, liked or asked for FAULTLINE until sessions have happened and their anonymised notes exist.

Wording that may be used until then: "User research is planned (see USER_RESEARCH.md). No sessions have been run."
