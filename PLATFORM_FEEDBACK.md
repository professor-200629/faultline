# Platform feedback: Nebius Token Factory and NVIDIA Nemotron

Feedback requested by the hackathon rules. It is split by the kind of
experience behind it, so nothing reads as more tested than it was.

## A. From building against the documentation (2026-10-26)

These are observations made while integrating, before any live API call.
Sources are listed in `docs/research/raw-research-2026-10-26.json`.

1. **No reasoning page for Nemotron.** The Token Factory docs do not explain
   how to turn Nemotron's reasoning on or off, or whether
   `chat_template_kwargs` / `reasoning_effort` are forwarded. NVIDIA's model
   cards document `enable_thinking`, but they describe self-hosted vLLM/SGLang.
   For an agent that makes many short tool calls, this matters for both
   latency and cost. FAULTLINE exposes `FAULTLINE_REASONING=off`, which is
   untested until verified live.
2. **Which models support function calling is hard to find.** The
   function-calling guide's only example model is a Llama model. The per-model
   signal (`use_cases: function_calling`) exists only in the public catalogue
   JSON. A "supports tools" column in the model list, or a Nemotron example in
   the function-calling guide, would save time.
3. **Model ID casing is inconsistent across official pages.**
   For example, the catalogue has `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` while
   a cookbook page has `nvidia/nvidia-nemotron-3-nano-30b-a3b`; Lightning uses
   `3_5` while Super-VL uses `3.5`. We copy IDs from `/v1/models` rather than
   from prose.
4. **Base URL guidance conflicts.** The Nemotron product page and cookbook use
   the `us-central1` regional URL. The public-serverless docs warn that
   regional URLs can stop working for public endpoints. We default to the
   global `https://api.tokenfactory.nebius.com/v1` and make it configurable.
5. **`tool_choice` values.** The guide lists only `auto` and the named-function
   form under "Limitations". The OpenAPI spec also accepts `none` and
   `required`. We use only `auto` and the named-function form, which the guide
   documents.
6. **Helpful:** an OpenAI-compatible API, a machine-readable public catalogue
   with prices, a documented error table (402 for exhausted credit, 429 with
   rate-limit headers), and an OpenAPI document. Each removed a guess.
7. **Deprecation notice.** The August 2026 notice (Nano-Omni and
   Llama-3_1-Nemotron-Ultra-253B removed from Serverless, with replacements
   named) is clear. However, the nebius.com Nemotron page still lists Nano Omni.

## B. From live use

From 2026-10-26: 62 evaluated investigations with 275 chat-completion
requests (raw records in `eval/results/`), plus one in-app run with 6
requests (`replays/`). All requests used tools and went to
`nvidia/nemotron-3-super-120b-a12b` on the global base URL
`https://api.tokenfactory.nebius.com/v1`. The figures below come from the 275
evaluated requests.

1. **Onboarding.** A billing form with a card is required before any key works,
   although it states a $0 authorisation. For participants without spare
   funds, it is not obvious from that page that the hackathon promo credits
   cover usage. A line on the API-keys page saying "a $0 check; promo credits
   cover usage" would help.
2. **`/v1/models`** listed 30 models, including all 5 NVIDIA models, with
   exact IDs. Copying the ID from there avoided the casing problems described
   in A.3. The global base URL served Super; no regional URL was needed.
3. **Tool calling was reliable.**
   - All 275 responses returned `finish_reason: tool_calls` with parseable
     JSON arguments.
   - No reply was text-only, and none contained more than one tool call.
   - A named `tool_choice` (forcing `submit_diagnosis`) was honoured on all 26
     one-shot runs.
4. **Latency:** median 5.1 s per call, p90 9.6 s, max 14.9 s. A full
   investigation took 25–60 s, inside our 120 s budget. We saw no 429 and no
   5xx errors at this volume.
5. **Reasoning:** about 70% of completion tokens were reported as reasoning
   tokens (`completion_tokens_details.reasoning_tokens`). Non-streaming
   messages carried reasoning content (249 of 275 responses). This answers our
   documentation question A.1 for the default setting. We did **not** test the
   `enable_thinking: false` switch, so we still cannot say whether Token
   Factory forwards it.
6. **Cost** matched the catalogue arithmetic: about $0.015 per investigation
   (about 37k prompt and 4k completion tokens). We could not see live credit
   balance from the API; a balance endpoint would let tools stop before a 402.
7. **Model behaviour, not platform:** Nemotron Super often asked for
   instruments the brief said were unavailable (24 of 28 rejected calls).
   Twice it overstated what noisy data showed. These are prompt and model
   issues for us to address, not Token Factory defects.

## C. NVIDIA tools beyond Nemotron

Not used. The project uses Nemotron only, through Token Factory. No NIM
self-hosting, GR00T, Cosmos or other NVIDIA tools were used, so we offer no
feedback on them.
