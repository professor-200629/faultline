# Hidden-state threat model

FAULTLINE's claims only mean something if the agent cannot learn the answer
from anything but measurements. This document states what is protected, from
whom, how, and what is not protected.

## Assets

| Asset | Where it lives | Who may see it |
|---|---|---|
| Fault configuration (family, coefficients, stuck value, model-mismatch knobs), initial true level, noise seed | `sealed_cases` table; in-memory `Plant` inside `InstrumentPanel` | evaluator; judge after a terminal reveal |
| Twin slot mapping (which card is which fault) | in-memory challenge record; sealed truth of the picked run | judge after reveal |
| Grades and identifiability analysis | `grades` table; computed at reveal | judge after reveal |
| True-state trace | private `Plant.truth_log` | judge after reveal (omniscient chart) |
| `NEBIUS_API_KEY` | process / `.env` / Windows per-user environment | server process only |

## Adversaries considered

1. **The runtime agent** (Nemotron, or any model behind the provider). It can
   only emit tool calls. It has no shell, filesystem, network, database or
   evaluator access.
2. **A viewer of the investigation screen or its exports** (audience, video
   viewers, the trainee). They see public data only until a judge reveals.
3. **A web page in another origin** trying to call judge endpoints through
   the user's browser.

Not considered: anyone with administrator access to the machine running the
server. They can read the SQLite file, memory or source and see everything.
This is a local prototype, not a hardened service.

## Controls

**Capability separation (code structure).**
- Agent-facing code (`agent/`, `analysis.py`) receives a `ToolExecutor` that
  wraps an `InstrumentPanel`. The panel keeps the `Plant` in a name-mangled
  private attribute and exposes only measurement and bounded-intervention
  methods that return dictionaries built from explicit whitelists
  (`public_sample`, the measurement result dicts).
- `predict_under_hypothesis` (`agent/public_model.py`) is computed from the
  agent's own evidence ledger and the public datasheet; a test asserts the
  module does not reference plant, case or judge code.
- The tool registry contains exactly eight tools; none reveals, grades or
  touches storage. Arguments are validated by Pydantic models with
  `extra="forbid"` and range limits before anything reaches the simulator;
  site permissions and the simulated-time allowance are enforced again inside
  the panel.
- `Plant`, `InstrumentPanel`, `NoiseSource`, `ToolExecutor`, `RunManager`,
  `SealedStore` and `NebiusProvider` override `__repr__` so logs and
  tracebacks do not print hidden values or the key.

**Storage separation.** Public run records (`runs`, `events`,
`model_calls`) never receive the case configuration. Hidden configuration is
written only to `sealed_cases` through `SealedStore`, which agent-facing code
is never given.

**API separation.**
- `/api/*` returns public data. Ground truth appears only in `reveal`, which
  is populated after a judge reveal of a terminal run.
- `/api/judge/*` requires an HttpOnly, SameSite=Strict cookie issued only to
  loopback clients, plus a custom `x-faultline-judge: 1` header (a cross-origin
  page cannot add it without a CORS preflight, and no CORS is enabled).
- Only loopback host names are served (`TrustedHostMiddleware`), and any
  state-changing request that carries a non-loopback `Origin` is refused. This
  defeats DNS rebinding, where a hostile site re-points its own name at
  127.0.0.1 to become same-origin with itself.
- Approving a simulated maintenance returns only public post-maintenance
  readings. The evaluator's true-plant check (true net inflow, sensor error)
  is stored in the sealed table and shown only in the reveal.
- Reveal is refused unless the run is terminal. Terminal runs cannot be
  restarted, so a revealed or cancelled run can never continue as a blind run.
  A twin challenge can be picked once.
- Run IDs and challenge IDs are 64-bit random hex with no encoded meaning.
  Export filenames use the run ID only.
- Unhandled exceptions return `{"error": "internal error", "error_id": ...}`
  without detail.

**UI.** The investigation screen renders the LT-101 *indicated* level, never a
true level. Truth appears only in a separately styled, judge-only panel after
reveal.

**Honest modes.** LIVE needs a configured key; without one the start request
fails with HTTP 409 and the run stays `ready`. No scripted or reference run is
ever substituted. Reference-procedure and replay runs are labelled as such in
the API, exports and UI.

## Evidence

`backend/tests/test_leakage.py` runs blind and twin cases for every fault
family with a recording provider and asserts that no hidden key, private label,
seed or exact hidden coefficient appears in: every model request, the run
view before and after the investigation, telemetry, the runs list, the JSON
and Markdown exports, status, catalog, and captured logs. It also checks that
twin briefs differ only in measured digits, judge endpoints need cookie and
header, reveal requires a terminal run, twin challenges are single-use, and
LIVE without a key is refused.

## Known gaps

- Anyone at the server machine can read everything (by design, see above).
- The twin *preview* cards show alarm windows for both slots; the investigated
  run uses a fresh seed, so the run's numbers do not identify the slot, but a
  person comparing physical trends could still guess when twins are not exact
  (they match to within 1 mm noise-free).
- The loopback check trusts the socket peer address; running the server behind
  a reverse proxy would make every client look local. Do not expose the server
  beyond localhost.
- The model sees the public hypothesis catalogue for every case, so its
  answer space is known; the defence is that every case shares it.
