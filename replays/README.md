# Recorded runs for REPLAY

The server imports every `*.json` evidence bundle in this folder at start-up,
as a **REPLAY** run. A replay can be watched step by step, but it can never be
started, resumed or re-revealed. Its badge and banner name the mode it was
recorded in.

| File | Recorded mode | What it shows |
|---|---|---|
| `live-nemotron-twin-falling-level.json` | **LIVE: NVIDIA Nemotron 3 Super on Nebius Token Factory** | A falling-level Twin Challenge dealt at random and run live in the app on 2026-10-26. FT-101 showed normal delivery, the dip reading matched LT-101, and a pump-stop test fell faster than demand alone. Diagnosis: tank leak (correct, revealed). 6 tool calls, 38 s, about $0.013. |
| `example-reference-twin-falling-level.json` | **REFERENCE PROCEDURE (deterministic, not AI)** | A falling-level Twin Challenge, dealt at random, investigated with an FT-101 measurement, the maintenance approved, and the ground truth revealed. It exists so the replay feature can be seen without a Nebius key. It is **not** a Nemotron run. |

Recordings of LIVE Nemotron runs are added here only from real runs, exported
with `/api/runs/<id>/export.json`.
