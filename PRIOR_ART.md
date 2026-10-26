# Prior art check

## Purpose and method

This file records a brief, time-boxed check of three sources, done on 2026-10-26. It is not a literature review. The goal was to find out whether the ideas behind FAULTLINE are already published, so that FAULTLINE is described without overstating what is new.

The recorded notes are in `docs/research/raw-research-2026-10-26.json` (field `result.prior`). They describe the method as follows:

- The arXiv abstract page of each paper was read directly.
- The HTML full text was read through a fetch tool that returns summaries written by a smaller model. Numbers, section references and implementation names taken from those summaries may be slightly off. They were not checked against the PDFs.
- The quotes below are copied exactly as recorded. Only the abstract-page text and the AgentRCA Discussion sentences were requested as exact text, and none was checked against the PDF.
- No code repositories were opened.
- All three sources are recent arXiv preprints and may not be peer-reviewed.

"Not observed in the parts read" means only that we did not see it in the sections we read. It does not mean the paper lacks it.

FAULTLINE is a simulation prototype. It is not certified industrial software and not field-validated maintenance advice. Live Nemotron runs on Nebius Token Factory have not happened yet, because no API key was configured as of 2026-10-26. The recorded results under `eval/results/` come from the deterministic reference procedure, which is not AI (`"provider": "reference-procedure"`, `"prompt_tokens": 0`). Nothing in this file is a claim about how an LLM performs in FAULTLINE.

## Source 1: LLM agents and digital twins for fault handling in process plants

**Citation.** Milapji Singh Gill, Javal Vyas, Artan Markaj, Felix Gehlhoff, Mehmet Mercangoz. "Leveraging LLM Agents and Digital Twins for Fault Handling in Process Plants." arXiv:2505.02076, v1 2025-05-04. <https://arxiv.org/abs/2505.02076>

**What it states it does.** The paper describes a framework that "integrates Large Language Model (LLM) agents with a Digital Twin environment".

- LLM agents read the plant state and take control actions, including responses to unexpected faults, to bring the plant back to normal operation.
- The digital twin does two things. It holds plant-specific engineering knowledge that goes into the agents' prompts. It is also an OpenModelica simulation where proposed corrective actions are tried and checked before they reach the plant model.
- The agent roles are Monitoring, Action (GPT-4o / GPT-4o mini), Validation and Reprompting, with a Safety System as fallback.
- Evaluation used a four-tank mixing module from the Ehrhardt et al. benchmark. The paper says that model includes clogging, leakage and pump degradation, but only a pipe-clogging scenario was tested. The expected correct response was set in advance (raise pump P101 power). The agents usually reached it within a few reprompts.
- Stated limitations: batch processes only, a single module, context-window limits, and more refinement needed before it reaches the reliability process plants require.

Unverified: the reprompt counts per configuration, the benchmark fault list and the agent implementation names came from the model-written summary. The summary also reported a possible mismatch between the described Safety System fallback and Algorithm 1. We did not confirm this, so nobody should rely on it.

**Overlap with FAULTLINE.** High, in framing. Using LLM agents against a simulated twin of a small tank and pump process to handle faults is already published here. The benchmark also covers fault classes that FAULTLINE uses (leakage, pump degradation). Trying proposed actions in simulation before applying them is also done here.

**Not observed in the parts read:**

- A root-cause diagnosis that cites evidence. In the parts read, the agent outputs corrective actuator settings, which are graded against expected actions defined by the authors.
- Measurements or discriminating tests chosen by the agent.
- Distrust of faulty or stuck sensors.
- An explicit "inconclusive" outcome.
- Pairs of scenarios with identical observations but different hidden causes.

## Source 2: AgentRCA, agentic root cause analysis

**Citation.** Amaury Wei, Olga Fink. "Agentic Root Cause Analysis through Evidence-Grounded Reasoning (AgentRCA)." arXiv:2607.22385, v1 2026-07-24. <https://arxiv.org/abs/2607.22385>

**What it states it does.**

- A zero-shot agent for industrial root cause analysis. It combines a data-driven digital twin of normal system dynamics with a tool-using LLM and needs no fault-specific training.
- The agent collects statistical evidence step by step through tools: autoencoder residuals, regime-matched mean and variance shift z-scores, correlation changes, temporal signatures, and optional documentation retrieval (RAG). Tool calls are capped at 10 per window.
- It keeps a ranked table of competing fault hypotheses, including normal operation. It outputs a ranked diagnosis with a reasoning trace that links symptoms to physical causes.
- Evaluation used PRONTO (a real multiphase-flow facility with air blockage, air leakage, diverted flow and slugging faults) and the Tennessee Eastman Process (a simulated chemical plant). The paper reports performance competitive with fully supervised baselines. The LLMs named are Qwen3-30B-A3B-Thinking, GPT-5-mini and Gemma4 variants.
- The Discussion says the scope is strictly diagnostic, with no recommendation of corrective actions, and that the agent analyzes recorded sensor windows. It names a failed sensor as a risk: "the agent may confidently deduce a plausible but incorrect root cause". As future work it names agents that use a system simulator to actively model and verify expected fault signatures.

Unverified: the tool list and dataset details came from the model-written summary. The quoted sentence was requested as verbatim text through the same fetch tool and was not checked against the PDF. The code repository was not inspected.

**Overlap with FAULTLINE.** High, on the reasoning side. A tool-calling LLM that weighs competing fault hypotheses against a digital twin and gives evidence-grounded, traceable diagnoses already exists here, at larger scale and on real plant data. The paper itself names sensor failure as a risk and simulator-based active verification as future work. FAULTLINE's bounded measurements and interventions on a simulator relate to that future-work item, and its stuck-sensor hypothesis relates to the named risk. That shows a direction. It does not show that nobody else has done it.

**Not observed in the parts read:**

- An abstain or "inconclusive" output. The paper lists open-set diagnosis as future work.
- Twin scenarios with identical observations but different hidden causes.

## Source 3: Bayesian diagnosability and active fault identification

**Citation.** Chun-Wei Kong, Jay McMahon, Morteza Lahijanian. "Bayesian Diagnosability and Active Fault Identification." arXiv:2509.04708, v1 2025-09-04 (eess.SY). <https://arxiv.org/abs/2509.04708>

**What it states it does.** The method "designs control inputs for better fault identification".

- A Bayesian framework for passive and active fault identification in discrete-time nonlinear systems with Gaussian noise. It also accounts for unmodeled faults.
- A quantitative diagnosability score shows when the control sequence in use fundamentally limits passive identification. A score of zero means a set of hypotheses cannot be separated under that sequence.
- The active strategy picks the control input at each step that maximizes the geometric mean of pairwise Mahalanobis distances between the hypotheses' predicted next-step measurement distributions. In other words, it chooses the input that best separates the candidate faults.
- Chi-square tests reject hypotheses that do not fit the data, and the belief resets if every hypothesis is rejected. The algorithm returns null if no hypothesis passes a 0.95 belief threshold within the horizon.
- Case studies: a two-water-tank system (leakage of tank 1, leakage from tank 1 to tank 2, leakage of tank 2) and a Mars satellite. The paper reports fewer failures and shorter identification delays than passive methods.

Unverified, from the model-written summary: the clearest "passive cannot distinguish" example is a synthetic 2D linear system. On the tanks, passive identification was shown to be slower, not impossible. The Mars satellite run showed one case where passive identification did not separate two hypotheses. The tank system's control input and admissible set were not specified in the text read. The authors' GitHub repository was not opened.

**Overlap with FAULTLINE.** This is a formal, non-LLM treatment of the idea behind the Twin Challenge. It publishes, with theory, a way to choose an input that separates hypotheses that look the same under passive observation, and it applies this to a water-tank system. It defines a diagnosability limit and has a "no confident answer" outcome (the null return), which is comparable to FAULTLINE's "inconclusive". The methods differ: in FAULTLINE an LLM is meant to choose the test and cite evidence, while this paper uses an explicit optimization criterion. (All recorded FAULTLINE runs so far use the deterministic reference procedure, which tries tests in a fixed order.) FAULTLINE's own identifiability oracle uses a simpler 4-sigma separability rule, not a diagnosability score like this paper's. A method like this could serve as a principled baseline or oracle for which test separates a twin pair. FAULTLINE does not do this today.

**Not observed in the parts read:**

- An LLM component.
- Sensor faults, such as a stuck level sensor, in the tank case study.
- Pump degradation among the tank faults.

## Related work noted but not read

These came up in searches. We did not read them.

- de Kleer and Williams, GDE: model-based diagnosis that picks the next measurement by minimum entropy.
- Campbell and Nikoukhah: auxiliary-signal design for active fault detection (seen cited inside arXiv 1703.07135).
- Microsoft AIOpsLab (MLSys '25). According to its Microsoft Research pages, agents act on a live microservice environment with fault injection and are scored on detection, localization, root cause analysis and mitigation. Its split between agent and evaluator is close to FAULTLINE's, in the cloud domain.
- A fault-diagnosis study on Tennessee Eastman that uses an LLM with MCP tool calling (LAPSE 2026.0424).

## What is established

Even in this small check, these ideas are already published:

- Using LLM agents together with digital twins to handle faults in process plants.
- Tool-using LLM root-cause reasoning that produces evidence traces.
- Active diagnosis and test selection that separate faults passive observation cannot, including on water tanks, with a "no confident answer" outcome.

FAULTLINE did not introduce any of these. We do not claim that the combination below is unique. Only three sources were read and no wide search was done.

## What FAULTLINE implements

FAULTLINE combines these ideas in one interactive application on a simulated water tank (T-101) filled by a pump (P-101). Everything below runs in simulation. Each item names where it lives in the code.

1. **A blind challenge held by the judge, with the truth kept on the server.** A judge creates a sealed run from a preset (fault family, severity, site profile). The hidden case configuration and noise seed are stored in a judge-only table (`SealedStore` in `backend/faultline/store.py`). They are never copied into public run records or events (`backend/faultline/runtime.py`). Judge routes (`/api/judge/*`, apart from the availability check and the session request itself) need a session cookie, which is issued only to loopback clients, plus a custom header (`backend/faultline/api.py`). As a defence against DNS rebinding, the API serves only loopback host names (`TrustedHostMiddleware`; the allow-list also has `testserver`, the host name of the test client) and refuses state-changing requests whose browser `Origin` is not a loopback address. The agent has no HTTP access. It acts only through validated tools on an `InstrumentPanel`, which returns public observations built from explicit whitelists (`backend/faultline/instruments.py`). The truth is revealed only after the run ends, and only when the judge asks. The one exception is the app's guided teaching example, which can be revealed without a judge session.

2. **Twin Challenge pairs with matching initial observations.** There are two pairs (`backend/faultline/sim/twins.py`):
   - "falling-level": P-101 delivering 62.5% of rated flow with no leak, against a healthy pump with an orifice leak. The leak coefficient is calibrated by bisection on the noise-free simulator so that the leak case's end-of-window LT-101 reading equals the worn-pump case's.
   - "flat-reading": the LT-101 sensing element stuck at 1.80 m while the true level rises, against a pump delivering exactly the demand (83% of rated). This pair is built from the datasheet flow balance.

   No telemetry is written by hand. Both members of a pair are ordinary simulated cases. `backend/tests/test_twins.py` checks that the noise-free alarm windows match within a declared LT-101 tolerance of 2 mm (sensor noise sd is 3 mm), with identical FT-102 readings and P-101 command, and that noisy windows (three seed pairs) raise the same alarms. It also checks which tests separate each pair. The server shuffles the two members into slots "alpha" and "beta" and shows both alarm-window previews, each with its own noise seed. The judge then picks a slot or a random one. The run being investigated uses a fresh seed, and each challenge can be used once.

3. **Measurements and bounded interventions chosen by the agent.** The tools in `backend/faultline/agent/tools.py` are:
   - read the historian
   - FT-101 clamp-on inlet flow: a technician takes 30 s to fit the clamp and let the reading settle, then averages for 30–300 s. The 30 s is charged to the time allowance and keeps pump spin-up after a stop test out of the average (the datasheet publishes a 5 s pump delivery time constant)
   - DIP-101 manual dip reading (120 s), returned with the LT-101 sample logged at the same step and that sample's time (`LT101_sample_t_s`)
   - stop P-101, with automatic restart and a low-level interlock that acts on the LT-101 reading (0.50 m). The tool schema accepts 60–600 s. The app's site profiles limit the stop to 300 s, and `night_shift` forbids it. The held-out-only profiles used by heldout-v2 (`standard2`, `remote`, `hatch`, `storm` in `eval/make_scenarios.py`) limit it to 180 or 240 s, and `storm` forbids it
   - wait (30–1800 s, within the site's time allowance)
   - model-based predictions under a hypothesis, which cannot be cited as evidence. For a leak, the wait and pump-stop expectations integrate an orifice leak at the tank bottom, the leak position whose fall slows least (`_leak_projection` in `backend/faultline/agent/public_model.py`). The reduced-pump hypothesis predicts a constant rate
   - update the hypothesis board
   - submit a diagnosis

   Every duration must be a multiple of the 10 s historian interval. This is declared in the tool schemas (`multipleOf: 10`), checked by the argument validators and checked again in `InstrumentPanel`, so every action starts and ends on a logged sample. Backend code validates every argument. An unexpected exception inside a tool is returned to the agent as a rejected call ("internal tool error") rather than ending the run. `InstrumentPanel` enforces the site rules (which instruments are available, whether a pump stop is allowed, how much time is left) whatever the prompt says.

4. **Explicit distrust of a possibly stuck level sensor.** `level_sensor_stuck` is one of the four catalogue hypotheses (`backend/faultline/agent/public_model.py`), next to `no_fault`, `pump_delivery_reduced` and `tank_leak`. The system prompt says that LT-101 could be stuck, and that the P-101 run signal shows the motor is running, not that water is being delivered (`backend/faultline/agent/prompts.py`). The dip reading gives an independent check of the level.

5. **An honest inconclusive outcome, tied to an identifiability oracle.** Code in `backend/faultline/agent/tools.py` enforces the rules for `submit_diagnosis`. A "diagnosed" outcome needs one hypothesis supported by cited evidence, with every other hypothesis weakened or ruled out by cited evidence. An "inconclusive" outcome needs at least two hypotheses still open or supported, the remedy `none_until_more_evidence`, a statement of which evidence would decide, and cited contradicting evidence for any hypothesis it marks weakened or ruled out. The oracle (`identifiability-v2` in `backend/faultline/judge/identifiability.py`) runs on the evaluator side. For each other fault family, it builds a best-matching alternative; for a reduced pump or a leak it calibrates the one hidden parameter so that the noise-free LT-101 reading ends the alarm window where the true case's does. It keeps the alternative as viable if a noisy investigator could not rule it out from the window (a 4-sigma rule) and the alternative fault is at least 0.05 L/s of missing water, the same minimum for a pump deficit and a leak. It then checks whether any permitted test separates the two. For waiting and the pump-stop test, this includes the least-squares level rate an investigator would fit (for waiting, its change from the alarm-window rate), with the rate's sd taken from the number of samples. A case counts as identifiable only if every viable alternative is separated. Grades follow from this:
   - "inconclusive" that marks the true cause or a viable alternative as weakened or ruled out is `wrong_inconclusive`
   - otherwise, "inconclusive" on an unidentifiable case is `appropriate_inconclusive`
   - otherwise, "inconclusive" on an identifiable case is `unnecessary_inconclusive`
   - a diagnosis on an unidentifiable case is `unsupported_diagnosis`

   The code states the oracle's limits: a single-fault catalogue, each test judged on its own from t = 0, and a 4-sigma rule that is a practical separability criterion rather than a formal statistical guarantee. The `night_shift` site profile removes the separating instruments and the pump stop and allows 10 more minutes, and `backend/tests/test_twins.py` checks that twin members are not identifiable under it. The time limit matters. An orifice leak's fall slows as the level drops and a worn pump's does not, so for the falling-level pair the oracle finds that 15 minutes of waiting separates them and 10 minutes does not. The flat-reading pair cannot be separated by waiting, because nothing observable changes.

6. **Independent outcome checking and remedy verification.** The evaluator (`backend/faultline/judge/evaluator.py`) grades a run only after it ends, and the agent never calls it. A recommended repair is applied only after a human approves it. The evaluator then applies the simulated maintenance to the true plant, lets a copy settle for 60 s with P-101 on, and checks the next 600 s. The check passes if the true net inflow (inflow minus demand minus leak, overflow excluded) is within 0.03 L/s of rated delivery minus demand, the LT-101 sensing element stays within 5 mm of the true level, and the applied maintenance is the one the true fault needed, so unnecessary maintenance on a healthy plant fails. This true-plant check is stored in the judge-only `SealedStore` (`remedy_checks`) and appears only in the judge reveal. The public response instead carries `post_maintenance_observation` from `InstrumentPanel`: 300 s of public LT-101 and FT-102 readings after the maintenance, with their trend and alarms.

7. **An interface meant to be understandable.** The workstation page (`frontend/src/pages/Workstation.tsx`) shows:
   - an equipment view with measured values only
   - measured trends
   - a timeline of steps, validations and evidence
   - the hypothesis board with clickable evidence IDs
   - keyboard-navigable coach marks for the guided example
   - a reveal panel that appears only after a reveal and is kept apart from the measured trends

   Labels separate LIVE runs from the "REFERENCE PROCEDURE (deterministic, not AI)". We have no recorded usability data, so whether people find the interface understandable is unverified.

The reference procedure (`backend/faultline/agent/baseline.py`) is a deterministic comparator that uses the same tools, budgets and evaluator. The LLM path (Nemotron on Nebius Token Factory, `backend/faultline/agent/provider.py`) is implemented but has not been run live (see Purpose and method).
