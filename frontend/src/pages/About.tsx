// About (#/about): scope, limitations and the meaning of each mode.

// Copied from backend/faultline/export.py LIMITATIONS (the same text ships in every export).
const LIMITATIONS = [
  "Simulation prototype: one documented tank-and-pump topology with a single-fault catalogue. " +
    "It is not certified control software and not field-validated maintenance advice.",
  "Diagnoses are relative to four hypotheses (no fault, reduced pump delivery, tank leak, stuck level sensor); " +
    "combined or unmodelled faults may be misdiagnosed or reported inconclusive.",
  "Confidence labels are the agent's qualitative judgement, not calibrated probabilities.",
  "Identifiability labels come from a noise-free 4-sigma separability rule applied to single tests, " +
    "not a formal statistical guarantee.",
  "Usefulness to maintenance trainees and technicians has not been validated with real users.",
];

export function AboutPage() {
  return (
    <div className="page narrow prose">
      <h1>About Faultline</h1>
      <p className="notice">
        <strong>Simulation prototype.</strong> Faultline is not certified software and not field-validated maintenance advice. Its
        real-world usefulness has not been validated.
      </p>
      <p>
        Faultline investigates a malfunctioning water-tank system: tank T-101 filled by pump P-101, with level transmitter LT-101, demand
        flow meter FT-102, a portable inlet flow meter FT-101 and a manual dip reading DIP-101. An investigator chooses measurements and
        bounded tests through validated tools; a simulator computes every measurement; a judge holds the hidden fault on the server.
      </p>

      <h2>Modes</h2>
      <dl className="modes">
        <div>
          <dt>
            <span className="mode-badge mode-live mode-sm">
              <span className="mode-main">LIVE</span>
            </span>
          </dt>
          <dd>
            An AI agent, NVIDIA Nemotron on Nebius Token Factory, picks each step. Provider failures are shown in the timeline. If no API key
            is configured, LIVE does not start; there is no scripted substitute.
          </dd>
        </div>
        <div>
          <dt>
            <span className="mode-badge mode-reference mode-sm">
              <span className="mode-main">REFERENCE PROCEDURE</span>
            </span>
          </dt>
          <dd>
            A deterministic rule-based baseline, not AI. It uses the same tools, validation and budgets as the agent, so the two can be
            compared on equal terms.
          </dd>
        </div>
        <div>
          <dt>
            <span className="mode-badge mode-replay mode-sm">
              <span className="mode-main">REPLAY</span>
            </span>
          </dt>
          <dd>
            Plays back a recorded run from its stored event log, in the browser. Nothing is re-run and no model is called; the banner names
            the original mode and model.
          </dd>
        </div>
      </dl>

      <h2>The hidden-state boundary</h2>
      <p>
        The investigator and this screen see only logged readings and measurement results; the true fault, its parameters and the true
        tank level stay in a sealed server-side table that neither can query. Ground truth is shown only after a judge reveals a run that
        has ended, in a separate judge-only panel.
      </p>

      <h2>Predictions and evidence</h2>
      <p>
        Evidence (E1, E2, …) is an observation computed by the simulator. A prediction (P1, P2, …) is a model-based expectation from the
        public datasheet; it is always labelled as such and cannot be cited as evidence.
      </p>

      <h2>Diagnosis and repair</h2>
      <p>
        Submitting a diagnosis changes nothing. A technician approves or declines the recommended simulated maintenance, and an independent
        evaluator checks the resulting simulated plant.
      </p>

      <h2>Limitations</h2>
      <ul>
        {LIMITATIONS.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </div>
  );
}
