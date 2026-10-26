# Third-party notices

FAULTLINE's own code is MIT-licensed (see LICENSE). It depends on the
open-source packages below, which are installed from their registries and
not vendored in this repository. Licenses were read from installed package
metadata on 2026-10-26. Each package's own license file is authoritative.

## Backend (Python, `backend/requirements.lock`)

| Package | Version | License |
|---|---|---|
| fastapi | 0.162.0 | MIT |
| starlette | 1.10.0 | BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx | 0.28.1 | BSD (metadata classifier "BSD License") |
| httpcore | 1.0.9 | BSD-3-Clause |
| h11 | 0.16.0 | MIT |
| anyio | 4.15.1 | MIT |
| pydantic | 2.14.1 | MIT |
| pydantic-core | 2.50.1 | MIT |
| annotated-types | 0.8.0 | MIT |
| annotated-doc | 0.0.5 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| idna | 3.20 | BSD-3-Clause |
| certifi | 2026.10.23 | MPL-2.0 |
| click | 8.5.0 | BSD-3-Clause |
| opentelemetry-api | 1.45.1 | Apache-2.0 |

Development only (`backend/requirements-dev.lock`): pytest (MIT) and its
dependencies (iniconfig MIT, pluggy MIT, packaging Apache-2.0 OR BSD-2-Clause,
pygments BSD-2-Clause, colorama BSD (classifier)).

## Interface (npm, `frontend/package-lock.json`)

Shipped in the built bundle: react 18.3.1, react-dom 18.3.1, scheduler 0.23.2,
loose-envify 1.4.0 and js-tokens 4.0.0. All are MIT.

Build tools only (not shipped): vite 7.3.7, typescript 5.9.3 (Apache-2.0),
@vitejs/plugin-react 5.2.0, @types/react, @types/react-dom, and their 116
transitive development packages. These are mostly MIT, with some ISC,
Apache-2.0, BSD-3-Clause and one CC-BY-4.0 data package. For 50 packages the
license is not recorded in package.json in the way we read it; check
`frontend/node_modules/<package>/LICENSE` for each.

## Services and models

- **NVIDIA Nemotron 3 Super** (`nvidia/nemotron-3-super-120b-a12b`) is used
  through the Nebius Token Factory API under that service's terms. No model
  weights are included in this repository.
- **Nebius Token Factory** is accessed through its OpenAI-compatible HTTP API.
  No Nebius SDK code is included.
