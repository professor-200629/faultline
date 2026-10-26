# FAULTLINE simulator

This document covers the plant model in `backend/faultline/sim/`, the instrument layer, the public alarm rules, the public prediction model, how twin cases are built, the identifiability oracle and remedy verification. It gives the equations, units, assumptions and the tests that check them.

Status:

- FAULTLINE is a simulation prototype. It is not certified industrial software, and nothing in it has been validated against a real plant or field data. Do not use its outputs as maintenance advice.
- The simulator, the oracle and the evaluator do not call a language model. No live Nemotron/Nebius run has happened yet: as of 2026-10-26 no API key is configured.
- The numbers in `spec.py` form the prototype's own fictional datasheet. They were not taken from real equipment.

Source files:

| File | Contents |
|---|---|
| `backend/faultline/sim/spec.py` | Public nominal datasheet (`NominalSpec`, `NOMINAL`) |
| `backend/faultline/sim/case.py` | Public site conditions; private fault, mismatch and case configuration |
| `backend/faultline/sim/plant.py` | Physics, integration, sensor models, historian, noise, maintenance |
| `backend/faultline/sim/twins.py` | Calibration by bisection, the two twin pairs and the night-shift site |
| `backend/faultline/instruments.py` | `InstrumentPanel`: the only interface between the plant and agent-facing code; the 10 s grid rule |
| `backend/faultline/agent/tools.py` | Agent tool schemas, backend argument validation and `ToolExecutor` |
| `backend/faultline/agent/public_model.py` | `predict_under_hypothesis`: expectations from public data only |
| `backend/faultline/analysis.py` | Public statistics and alarm rules |
| `backend/faultline/judge/identifiability.py` | Identifiability oracle (`identifiability-v2`) |
| `backend/faultline/judge/evaluator.py` | Grading and `verify_remedy` (`evaluator-v3`) |
| `backend/faultline/runtime.py`, `backend/faultline/store.py` | Remedy approval (`RunManager.decide_remedy`) and the sealed remedy check (`SealedStore.remedy_checks`) |

---

## 1. Topology

```
   supply sump (not modelled, never runs dry)
         |
       P-101  delivered flow Q_in = first-order response to u * k * Q_rated
         |    [FT-101 portable clamp-on meter, fitted on request]
         v
   +-------------------------+ -- overflow weir crest 2.40 m --> overflow drain (Q_over)
   |          T-101          |
   |  vertical cylinder,     |    LT-101 level transmitter (logged every 10 s)
   |  flat bottom            |    DIP-101 dip tape through roof hatch (on request)
   |  A = 2.0 m^2, H = 2.5 m |
   |                         |--> leak orifice at h_leak (tank_leak fault only):
   |                         |    Q_leak = C * sqrt(h - h_leak)
   +-----------+-------------+
               | demand nozzle at 0.05 m
             FT-102 (logged every 10 s)
               v
          demand user (Q_d)
```

Pump P-101 delivers water from the supply sump into tank T-101. Water leaves T-101 in three ways:

- through the demand nozzle at 0.05 m, metered by FT-102;
- over the weir at 2.40 m into the overflow drain;
- through a leak orifice, which exists only in the `tank_leak` fault. Every current preset, twin and scenario (including `dev-v2` and `heldout-v2`) puts the orifice at `h_leak = 0`.

---

## 2. Units and nominal values

Inside the simulator all quantities are SI (m, m², m³, m³/s, s). Public views use m or mm for level, L/s for flow and mm/min for level rate. The leak coefficient C is in m^2.5/s, so `C * sqrt(m)` gives m³/s.

In the nominal 2.0 m² tank, a net flow of 1 L/s changes the level by 30 mm/min. `analysis.rate_mm_min_from_flow` does this conversion. `test_units_rate_conversion` checks that 0.2 L/s gives 6 mm/min.

| Quantity | Symbol | Value | Source |
|---|---|---|---|
| Tank cross-section | A | 2.0 m² | `tank_area_m2` |
| Tank height | H | 2.5 m | `tank_height_m` |
| Overflow weir crest | h_over | 2.40 m | `overflow_level_m` |
| Demand outlet level | h_out | 0.05 m | `outlet_level_m` |
| Pump rated delivery | Q_rated | 1.2e-3 m³/s (1.20 L/s) | `pump_rated_flow_m3s` |
| Pump time constant | τ_p | 5.0 s | `pump_time_constant_s` |
| LT-101 range | | 0 to 2.5 m | `level_sensor_range_m` |
| LT-101 noise (1 sd) | σ_LT | 3 mm | `level_sensor_noise_sd_m` |
| LT-101 resolution | | 1 mm | `level_sensor_resolution_m` |
| LT-101 time constant | τ_s | 2.0 s | `level_sensor_time_constant_s` |
| FT-102 noise (1 sd) / resolution | σ_FT102 | 0.01 L/s / 0.01 L/s | `demand_meter_noise_sd_m3s`, `demand_meter_resolution_m3s` |
| FT-101 noise (1 sd) | | 2 % of reading + 0.01 L/s | `inlet_meter_noise_rel`, `inlet_meter_noise_abs_m3s` |
| FT-101 resolution | | 0.01 L/s | `inlet_meter_resolution_m3s` |
| FT-101 fit and settle time | | 30 s | `instruments.FT101_FIT_S` (not a `NominalSpec` field) |
| DIP-101 noise (1 sd) / resolution / duration | σ_dip | 5 mm / 5 mm / 120 s | `dip_noise_sd_m`, `dip_resolution_m`, `dip_duration_s` |
| Historian interval | | 10 s | `historian_interval_s` |
| Integration step | dt | 1 s | `sim_dt_s` |
| Alarm window | | 900 s | `alarm_window_s` |
| LAL-101 threshold | | 1.00 m | `low_level_alarm_m` |
| BAL-101 threshold | | 2.5 mm/min | `balance_alarm_mm_per_min` |

The agent receives `NOMINAL.public_dict()`. It includes the pump delivery time constant (5 s, as `delivery_time_constant_s`) and states that fitting FT-101 takes 30 s before averaging starts. It does not include the LT-101 time constant or the integration step.

---

## 3. State variables and case configuration

`Plant` holds the true state. The class is private to the simulator side: agent-facing code reaches it only through `InstrumentPanel`.

| Variable | Code | Unit | Meaning |
|---|---|---|---|
| t | `t_s` | s | Logical time. It starts at −900 s. |
| V | `volume_m3` | m³ | True water volume |
| h | `true_level()` = V / A | m | True level, derived from V |
| Q_in | `pump_flow_m3s` | m³/s | Delivered pump flow at the end of the last step |
| s | `sensed_level_m` | m | LT-101 sensing element, before bias and noise |
| u | `pump_command` | 0 or 1 | P-101 command |
| Q_d,last | `last_demand_flow_m3s` | m³/s | Demand flow served in the last step (what FT-102 reads) |
| totals | `Totals` | m³ | Cumulative inflow, demand out, leak out, overflow out, unmet demand |
| k, C, stuck_at, bias | `pump_capacity_factor`, `leak_coeff`, `stuck_at_m`, `level_bias_m` | –, m^2.5/s, m, m | Fault parameters. Simulated maintenance can change them. |

Case configuration (`sim/case.py`):

- **`FaultConfig`** (private) has these fields:
  - `family`: one of `no_fault`, `pump_delivery_reduced`, `tank_leak`, `level_sensor_stuck`
  - `pump_capacity_factor` k, in [0, 1]
  - `leak_coeff_m25_s` C, which must be ≥ 0
  - `leak_height_m` h_leak
  - `stuck_at_m`
- **`CaseConfig`** (private) holds the fault, the true `initial_level_m` at t = −900 s, `demand_m3s`, optional `demand_steps`, `pump_command_on`, the site conditions and the mismatch configuration. Building a `Plant` from a case whose initial level is outside [0, h_over] raises `ValueError`.
- **`MismatchConfig`** (private) is used only in labelled model-mismatch evaluation cases. It can set:
  - a true tank area or true pump rating that differs from the datasheet;
  - a scale factor on LT-101 noise;
  - an LT-101 bias;
  - an FT-102 bias.

  The agent always gets the nominal datasheet.
- **`SiteConditions`** (public) say whether FT-101 is available, whether DIP-101 is available, whether a pump stop test is permitted, the maximum stop hold (default 300 s) and the extra logical time allowed (default 1800 s).

---

## 4. Plant equations

```
dV/dt = Q_in(t) - Q_d,served(t) - Q_leak(h) - Q_over
h     = V / A
```

### 4.1 Pump P-101 (first-order response)

```
target   T = u * k * Q_rated            u in {0, 1} (command), k in [0, 1]
dQ_in/dt   = (T - Q_in) / tau_p         tau_p = 5 s
```

T stays constant within a step, so the step has an exact solution:

```
Q_in(t0 + dt) = T + (Q_in(t0) - T) * exp(-dt / tau_p)
Q_in_avg      = (1/dt) * integral of Q_in over the step
              = T + (Q_in(t0) - T) * (tau_p / dt) * (1 - exp(-dt / tau_p))
```

The volume update uses the step average `Q_in_avg`. The plant starts in steady state (`Q_in = T`). Delivered flow does not depend on tank level. P-101 run feedback always equals the command, so a pump with reduced delivery still reads RUNNING.

### 4.2 Demand outlet

- **Demand value.** Q_d(t) is `demand_m3s`. Each entry `(t_change, q)` in `demand_steps` replaces it once t ≥ t_change. The value is read at the start of each step.
- **Cut-off at the outlet level.** Demand is served for the whole step only if the true level at the start of the step is above h_out = 0.05 m. Otherwise served demand is 0 for that step.
- **What FT-102 sees.** Any demand that is not served is booked as unmet demand (Section 6). FT-102 measures served demand, not requested demand.

### 4.3 Leak orifice (Torricelli)

```
Q_leak(h) = C * sqrt(h - h_leak)   if C > 0 and h > h_leak
          = 0                      otherwise
```

With h_leak = 0, the pump off and no demand, the analytic solution is `sqrt(h(t)) = sqrt(h0) - C t / (2A)`. `test_torricelli_drain_matches_analytic_solution` checks the simulator against it.

Because the leak flow falls as the level falls, a leak's level fall slows over time. A reduced pump gives a constant net flow, so its fall does not slow. Waiting long enough can therefore separate the two (Sections 14 and 15).

### 4.4 Overflow weir

Overflow is not a flow rate inside the integrator. At the end of each step, any volume above `A * h_over` is removed and booked as overflow. The true level therefore never exceeds 2.40 m.

---

## 5. Integration step (`Plant.step`, dt = 1 s)

1. **Pump.** Compute T, then `Q_in(t0 + dt)` and `Q_in_avg` exactly, as in Section 4.1.
2. **Demand.** Set `h_start = V0 / A`. Q_d,served is Q_d(t0) if `h_start > h_out`, otherwise 0.
3. **RK4.** Integrate `f(V) = Q_in_avg - Q_d,served - Q_leak(V)` from V0 with classical fourth-order Runge-Kutta, giving `V_rk4`.
4. **Close the balance exactly.** Compute:
   - `in_vol = Q_in_avg * dt`
   - `demand_vol = Q_d,served * dt`
   - `leak_vol = max(0, V0 + in_vol - demand_vol - V_rk4)` if C > 0, otherwise 0

   Then set `V1 = V0 + in_vol - demand_vol - leak_vol`. The leak volume is defined as the residual of the RK4 step. V1 therefore equals `V_rk4` up to floating-point rounding, and the cumulative totals add up exactly.
5. **Lower bound.** If V1 < 0, first reduce `leak_vol` so that V1 = 0, because the tank cannot leak more water than it holds. If that is not enough, reduce `demand_vol` and set V1 = 0.
6. **Upper bound.** If V1 > A · h_over, then `overflow_vol = V1 - A * h_over` and V1 = A · h_over.
7. **Bookkeeping.** Add the step's volumes to `Totals`. Unmet demand increases by `Q_d * dt - demand_vol`.
8. **Advance.** Set t ← t + dt and update the LT-101 element (Section 8).
9. **Historian.** If t is on a 10 s historian tick, record a historian sample and a private truth record.

The pump average and served demand are constant inside a step. RK4 therefore only approximates the leak term. With no leak the update is exact: `test_constant_net_flow_matches_analytic_linear_solution` checks it to a relative tolerance of 1e-12.

---

## 6. Volume bounds and the conservation identity

The volume always satisfies `0 <= V <= A * h_over`. The cumulative volumes obey:

```
V(t) = V(-900 s) + inflow - demand_out - leak_out - overflow_out
```

`Totals.balance_error(V)` returns the left side minus the right side. The tests require |error| < 1e-12 m³ in single scenarios and < 1e-11 m³ with repeated pump cycling and every fault family.

Unmet demand is tracked separately and is not part of the identity, because unserved water never left the tank.

---

## 7. Faults and simulated maintenance

| Family | Hidden parameter | Effect |
|---|---|---|
| `no_fault` | none | Healthy plant |
| `pump_delivery_reduced` | k < 1 | Delivered flow is `k * Q_rated`. Command and run feedback are unchanged. |
| `tank_leak` | C > 0 (h_leak) | Adds the Torricelli outflow, which depends on level |
| `level_sensor_stuck` | stuck_at | The LT-101 sensing element is frozen. The true level keeps changing. |

`Plant.apply_maintenance` accepts only these actions. Any other action raises `ValueError`.

| Action | Effect |
|---|---|
| `repair_pump` | k = 1 |
| `repair_tank_leak` | C = 0 |
| `replace_level_sensor` | Clears the stuck value, sets bias = 0 and sets the element to the true level |
| `no_action` | Nothing |

---

## 8. Sensor models

Each reading draws its noise at read time from its own channel (Section 10).

**LT-101 level transmitter (logged)**

```
element, healthy: s(t+dt) = h(t+dt) + (s(t) - h(t+dt)) * exp(-dt / tau_s)    tau_s = 2 s
element, stuck:   s = stuck_at
reading = quantise( clamp(s + bias + sigma_LT * m * N(0,1), 0, 2.5 m), 1 mm )
```

- **Lag.** The healthy element lags the true level with a first-order lag toward the true level at the end of the step. At t = −900 s the element starts at the true level, or at `stuck_at` if the sensor is stuck.
- **Bias and noise scale.** `m` is the mismatch noise scale and `bias` is the mismatch LT-101 bias. Both are 1 and 0 unless a mismatch case sets them.
- **Stuck sensor.** A stuck fault freezes only the sensing element. Transmitter noise, bias, clamping and quantisation still apply, so in noisy runs a stuck LT-101 still scatters by about 3 mm around the frozen value. In noise-free analysis runs it is exactly constant.

**FT-102 demand flow meter (logged)**

```
reading = quantise( max(Q_d,last + b_FT102 + sigma_FT102 * N(0,1), 0), 0.01 L/s )
```

`Q_d,last` is the demand flow actually served in the last step. When the outlet is uncovered, FT-102 reads about 0.

**FT-101 portable clamp-on inlet meter (on request, if available)**

```
fit and settle: 30 s (FT101_FIT_S); the plant runs and the historian logs, nothing is averaged
Q_true_avg = (change in cumulative inflow over the averaging period) / (averaging time)
             averaging time 30-300 s, a multiple of 10 s, starting after the fit
sd         = 0.02 * Q_true_avg + 0.01 L/s
raw        = Q_true_avg + sd * N(0,1)
reading    = quantise( max(raw, 0), 0.01 L/s )
stated sd  = 0.02 * max(raw, 0) + 0.01 L/s
```

- **What it measures.** FT-101 measures the true delivered flow over the averaging period, including any pump transient still present then.
- **Fit and settle.** A technician first fits the clamp and waits 30 s for a steady reading. 30 s is six pump time constants (τ_p = 5 s), so pump spin-up after a stop test falls inside the fitting period and is not averaged. `test_inlet_flow_after_a_stop_test_is_measured_at_steady_state` checks that a reading taken right after a stop test is within 4 stated sd of 1.20 L/s.
- **Averaging.** Each measurement uses one Gaussian draw. Averaging is represented by the stated sd, not by simulating many samples.
- **Reported uncertainty.** The stated sd is computed from the noisy value before quantisation, not from the true value.
- **Time cost.** The measurement uses 30 s plus the averaging time, charged to the time allowance. The result reports the fit start (`t_fit_start_s`), the fit time (`fit_and_settle_s`) and the averaging interval (`t_start_s` to `t_end_s`). The evidence record spans the fit and the averaging.

**DIP-101 independent manual level (on request, if available)**

```
reading = quantise( clamp(h + sigma_dip * N(0,1), 0, 2.5 m), 5 mm )     sigma_dip = 5 mm
```

- **Timing.** A dip takes 120 s of logical time. The reading is taken at the end of that time.
- **Independence.** It reads the true level directly, so the LT-101 lag, stuck element and bias do not affect it.
- **Returned values.** The result includes the LT-101 historian sample logged at the same simulation step, for a like-for-like comparison, and that sample's time (`LT101_sample_t_s`). Every action stays on the 10 s grid (Section 9), so a dip always ends on a historian tick and the same-step sample exists. The code would fall back to the latest earlier sample and report its time, but the grid rule means no action sequence reaches that fallback. The stated sd is always the datasheet value of 5 mm. The agent tool also reports a comparison sd of sqrt(5² + 3²) ≈ 5.8 mm.

**P-101 run feedback.** Equals the command. It reports the motor contactor, not delivered flow.

---

## 9. Historian and logical time

**Historian**

- **Cadence.** The plant is created at t = −900 s. A historian sample is logged at t = −900 s and then whenever `(t + 900) / 10` is an integer. `InstrumentPanel` pre-runs the plant to t = 0, so the alarm window contains 91 samples at 10 s spacing from −900 s to 0 s.
- **Public sample fields:** `t_s`, `LT101_m`, `FT102_L_s`, `P101_command`, `P101_run_feedback`.
- **Private truth log.** At the same ticks a private `truth_log` records the true level, true inflow, true leak flow, the element value and cumulative overflow.

**Logical time.** Simulation time is logical only and is not tied to wall-clock time. It moves only when an action consumes it. The plant advances in whole 1 s steps.

**Grid rule.** Every action lasts a multiple of the 10 s historian interval.

- `InstrumentPanel._on_grid` refuses a waiting time, FT-101 averaging time or stop-test hold that is not a multiple of 10 s (`GRID_S`). The fixed durations (30 s FT-101 fit, 120 s dip) are multiples of 10 s.
- The agent tool schemas declare `"multipleOf": 10` for these durations and for the `predict_under_hypothesis` duration. `tools.py` validators check it again in backend code before the plant is touched. `test_off_grid_durations_are_rejected_before_touching_the_plant` checks that off-grid requests use no time and create no evidence.
- Because t = 0 is a historian tick, every action starts and ends on a tick. A stop test aborted by the interlock also ends on a tick, because the interlock is checked only on logged samples.

| Action (panel method / agent tool) | Logical time used | Backend limits |
|---|---|---|
| `historian` / `read_observations` | 0 s | none |
| `advance` / `advance_simulation` | the requested duration | multiple of 10 s; the tool accepts 30–1800 s |
| `measure_inlet_flow` / `measure_inlet_flow` | 30 s fit + 30–300 s averaging | FT-101 must be available at the site; averaging time a multiple of 10 s |
| `independent_level` / `request_independent_level_measurement` | 120 s | DIP-101 must be available at the site |
| `pump_stop_test` / `set_simulated_pump` (off) | 60 s to `max_pump_stop_s`, a multiple of 10 s, or the actual elapsed time if aborted | stop test must be permitted and P-101 must be running; the tool accepts at most 600 s |
| `post_maintenance_observation` (not an agent tool) | 300 s | runs only after an approved maintenance (Section 16); not charged to the allowance |

- **Allowance.** Every timed agent action must fit within the remaining allowance `max_extra_sim_s`: 1800 s by default and 600 s (10 minutes) at the night-shift site (`AMBIGUOUS_SITE`, also the `night_shift` preset profile). A stop test is refused unless its full requested hold fits. Refused requests use no time.
- **Low-level interlock.** During a stop test, the test is aborted (P-101 restarts) if an LT-101 historian reading falls below 0.50 m (`PUMP_TEST_LOW_TRIP_M`). The interlock acts on the reading, so a stuck-high reading cannot trip it.
- **Restart after a stop test.** The command returns to ON at the end of the test, and delivered flow recovers with τ_p = 5 s.
- **Unexpected tool errors.** Refusals (`InstrumentError`, `PredictionError`, `ValueError`) are returned to the agent as rejected calls with their message. Any other exception inside a tool is also returned as a rejected call, with the fixed error "internal tool error; the call was not completed", and only the tool name and the exception type are logged. `test_unexpected_tool_failure_is_contained` checks the fixed error message; the logging is not tested.

---

## 10. Seeded per-channel noise

`NoiseSource(seed)` keeps one `random.Random` per channel. Each one is seeded with the string `"faultline:{seed}:{channel}"`, and the channels are `LT-101`, `FT-102`, `FT-101` and `DIP-101`.

- **Independent channels.** A channel draws only when it is read, so taking a dip reading does not shift the LT-101 noise sequence.
- **Stable string seeds.** Python's `random.seed` converts a str seed deterministically (version-2 seeding). It does not use the per-process salted `hash()`. The code comment states that SHA-512 is used.
- **What is tested.** The tests show that one install gives identical readings for the same seed and action sequence, and different readings for a different seed.
- **Not verified across Python versions.** The Python documentation ("Notes on Reproducibility" in the `random` module) guarantees only the `random()` sequence across versions, not `gauss()`.
- **Seeds stay hidden.** `NoiseSource`, `Plant` and `InstrumentPanel` redact their `repr`, so seeds and hidden state do not appear in logs or tracebacks.

---

## 11. Public alarm rules

`analysis.evaluate_alarms` applies these rules to the 91-sample alarm window.

- **LAL-101.** Raised if the median of the last 6 LT-101 samples (t = −50 to 0 s) is below 1.00 m.
- **BAL-101.** Raised if `|r_obs - r_nom| > 2.5 mm/min`, where:
  - `r_obs` is the ordinary-least-squares slope of LT-101 in mm/min;
  - `r_nom = (1.20 L/s * fraction of samples with P-101 commanded ON - mean FT-102) * 30 mm/min per L/s`.

  In the nominal tank, 2.5 mm/min corresponds to about 0.083 L/s.
- **No alarm.** The public context shows an `OPS` "operator asked for a check" message instead.

The standard error of the slope assumes independent residuals (`analysis.ols_slope`). It does not model the sensor lag or quantisation.

The same function, with the same thresholds, is applied to the 300 s of readings logged after an approved maintenance (Section 16).

---

## 12. What the agent sees and what stays private

| Agent sees (public) | Stays private (simulator, judge vault, evaluator) |
|---|---|
| Warning or alarm texts, the situation text, site conditions, the nominal datasheet (`NOMINAL.public_dict()`) and the current logical time (`runtime.public_context`) | Fault family and parameters (k, C, h_leak, stuck_at) |
| Historian samples with the five public fields. Tool results thin them to one row per 60 s (30 s for stop tests), always keep the last sample, and add a summary computed from all samples. | Model mismatch (true area, true pump rating, noise scale, biases) |
| FT-101 result: mean flow, stated sd, fit start, fit time, averaging start and end, command during the measurement | True initial level and the noise seed |
| DIP-101 result: dip level, stated sd, LT-101 reading at the same step and that reading's time | True state: V, h, Q_in, Q_leak, element value s, `Totals`, `truth_log` |
| Pump stop test samples and the interlock abort flag | Twin member labels and which twin slot was picked |
| `predict_under_hypothesis` outputs. These are labelled model-based expectations from public data and cannot be cited as evidence. | Identifiability report and grade, until the run is terminal and revealed |
| After an approved maintenance: `post_maintenance_observation` (the trend summary and alarm evaluation of the 300 s of LT-101 and FT-102 readings logged after maintenance) | The evaluator's remedy check on the true plant, stored in `SealedStore.remedy_checks` and shown only in the judge reveal |

How the boundary is kept:

- `InstrumentPanel` holds the `Plant` in a name-mangled attribute and returns whitelisted dictionaries only.
- `_private_plant()` is for the judge and evaluator only.
- `agent/public_model.py` imports no plant, case, instrument or judge code.

Name mangling is a coding convention, not a security boundary. The leakage tests in Section 17 are the actual check, and they cover only the listed hidden keys, label words and values.

### 12.1 Model-based predictions (`predict_under_hypothesis`)

`agent/public_model.predict` uses only the alarm-window summary the agent has read, the nominal datasheet, the hypothesis, the test, the current logical time and an optional duration. The agent must read the alarm window first.

From the window it takes the OLS rate r_obs and its standard error, the mean FT-102 flow q_d and the last LT-101 reading h_last. It converts r_obs to a net flow q_net with the nominal area. The implied flows are:

| Hypothesis | Pump delivery q_in | Leak q_leak | LT-101 follows the true level |
|---|---|---|---|
| `no_fault` | 1.20 L/s | 0 | yes |
| `pump_delivery_reduced` | max(0, q_net + q_d) | 0 | yes |
| `tank_leak` | 1.20 L/s | max(0, 1.20 − q_d − q_net) | yes |
| `level_sensor_stuck` | 1.20 L/s | 0 | no |

For `tank_leak`, the wait and stop-test expectations come from `_leak_projection`. It fits an orifice at the tank bottom, C = q_leak / sqrt(h_last), and integrates `dh/dt = (q_in − q_d − C·sqrt(h)) / A` forward from h_last in 1 s explicit-Euler steps. The docstring's argument is that a bottom orifice gives the least slowing for a given leak flow (dQ/dh = Q / (2(h − h_leak)) ≥ Q / (2h)), so the projected slowing is a lower bound.

| Test | Expectation |
|---|---|
| `wait` (default 600 s) | `tank_leak`: level change, end rate and rate change from the alarm window, from the projection with q_in = 1.20 L/s. Other hypotheses: rate stays at r_obs (0 for a stuck sensor), level change = rate × duration, rate change 0. Stated sd = sqrt((√2 · 3 mm)² + (se × duration in min)²). |
| `pump_stop_test` (default 300 s hold) | Rate = −(q_d + q_leak) × 30 mm/min per L/s. Level change = rate × hold (for `tank_leak`, the projection with q_in = 0) plus the pump run-down volume q_in · τ_p / A. A stuck sensor gives 0. Stated sd = √2 · 3 mm ≈ 4.2 mm. |
| `inlet_flow` | q_in, with sd = FT-101 datasheet sd at q_in, combined with the window-fit sd for `pump_delivery_reduced` |
| `independent_level` | Dip minus LT-101 = 0 if LT-101 follows the true level. For a stuck sensor: at least the nominal balance rate × the time from the window start to the end of the dip, as text. Stated sd ≈ 5.8 mm. |

`test_leak_wait_prediction_models_orifice_slowing_unlike_the_pump_hypothesis` checks, for the falling-level leak member and a 1200 s wait, that the leak prediction expects the fall to slow by more than 0.3 mm/min, that the pump prediction expects no change of rate, and that the leak prediction's level change is within 3 stated sd of the noise-free simulator and closer to it than the pump prediction's.

---

## 13. Noise-free analysis plant

`plant.QUIET` is `NOMINAL` with every noise sd and every quantiser resolution set to 0. Physics, timing and the LT-101 lag are unchanged. `noise_free_plant(case)` builds `Plant(case, seed=0, nominal=QUIET)`.

The twin calibration, the identifiability oracle and several physics tests use this plant. Mismatch biases still apply in it, because a bias is not noise.

---

## 14. Twin construction

The code does not hand-write any telemetry. Each twin member is an ordinary `CaseConfig`. For a twin of a target case, one hidden parameter is calibrated on the noise-free simulator:

1. **Base case.** Take the target case with its fault removed. Initial level, demand, site and mismatch are kept.
2. **Bisection.** Run 60 iterations of bisection on `f(p) = LT-101(t=0; p) - LT-101(t=0; target)`. The brackets are:
   - pump: k in [0, 1];
   - leak: C in `[0, 2 * Q_rated / sqrt(max(h0, 0.05))]`. At the upper end, the leak at h0 is twice the rated pump flow.
3. **Match check.** Bisection matches only the end of the window. The construction code does not check the rest; `test_noise_free_alarm_windows_match_within_declared_tolerance` compares the whole window with `judge.identifiability.window_deviation`, whose `match` flag requires all of these:
   - max |ΔLT-101| ≤ 2 mm (`TWIN_TOL_LT_M`, chosen below the 3 mm sensor sd);
   - max |ΔFT-102| ≤ 0.005 L/s;
   - the pump command and run-feedback series are identical.

| Pair | Member | Fault and parameters | Initial true level | Demand |
|---|---|---|---|---|
| `falling-level` | 1 | `pump_delivery_reduced`, k = 0.625 | 1.55 m | 1.0 L/s |
| | 2 | `tank_leak`, healthy pump, C calibrated to match member 1 | 1.55 m | 1.0 L/s |
| `flat-reading` | 1 | `level_sensor_stuck`, stuck_at = 1.80 m. The element froze 600 s before the window while the healthy pump kept filling at (1.2 − 1.0) L/s / 2.0 m² = 6 mm/min. | 1.86 m | 1.0 L/s |
| | 2 | `pump_delivery_reduced`, k = 1.0/1.2 ≈ 0.833 (pump delivers exactly the demand) | 1.80 m | 1.0 L/s |

**Values computed by running the code on 2026-10-26.** No test asserts these exact values. Reproduce them with `falling_level_pair()`, `flat_reading_pair()`, `window_deviation()` and `separation()`.

- **Falling-level pair.** The calibrated leak coefficient is C ≈ 3.68e-4 m^2.5/s, which is a leak of about 0.44 L/s at t = 0. The maximum noise-free LT-101 difference across the window is 0.95 mm. Both members fall at about 7.5 mm/min while the nominal balance predicts +6 mm/min.
- **Flat-reading pair.** The maximum noise-free LT-101 difference is 0.
- **Alarms.** With seed 11, all four members raise BAL-101 only.
- **Waiting at the standard site.** With the default 1800 s allowance, the oracle's wait test also separates the falling-level pair: the rate change differs by 0.75 mm/min against a 0.31 mm/min threshold, and the level change by 22 mm against 17 mm. It does not separate the flat-reading pair.

**Site for the ambiguity test.** `AMBIGUOUS_SITE` (night shift) has no FT-101, no DIP-101, no pump stop test and a 600 s (10 minute) allowance. Tests show that the members of both pairs are not identifiable under it.

The allowance matters for the falling-level pair, because the leak member's fall slows while the worn pump's does not (Section 4.3). These values were computed on 2026-10-26 by running `separation()` on the falling-level pair at `AMBIGUOUS_SITE` with only `max_extra_sim_s` changed. No test asserts them.

| Allowance | Difference in rate change, leak vs worn pump | Threshold | Separable by waiting |
|---|---|---|---|
| 600 s (current night shift) | 0.42 mm/min | 0.61 mm/min | no |
| 900 s | 0.50 mm/min | 0.41 mm/min | yes |
| 1200 s | 0.59 mm/min | 0.34 mm/min | yes |

At 600 s the level-change difference is 4 mm against a 17 mm threshold. The flat-reading pair stays inseparable by waiting at every allowance, because the noise-free readings of both members stay constant: the stuck element does not move and the balanced pump keeps the true level steady.

---

## 15. Identifiability oracle (`identifiability-v2`)

The oracle asks: given the instruments and permissions of this case, could any investigator separate the true cause from every other single-fault explanation that fits the alarm window?

**Step 1: build one alternative for each other family.**

- **Base.** The truth case with no fault. Its initial level is the first noise-free LT-101 reading of the window minus any bias. Demand, site and mismatch are kept from the truth.
- **`no_fault`.** The base itself.
- **`pump_delivery_reduced`.** Calibrate k so that the end-of-window reading matches. The alternative is not viable if the deficit (1 − k) · Q_rated is below 0.05 L/s (`MIN_MISSING_FLOW_L_S`), that is k > 0.958, because then it is just a healthy pump.
- **`tank_leak`.** Calibrate C, with the orifice at h_leak = 0. The leak at t = 0 is estimated as `C * sqrt(end reading - bias)`. The alternative is not viable if this is below 0.05 L/s, the same `MIN_MISSING_FLOW_L_S`.
- **`level_sensor_stuck`.** Considered only if the noise-free window moves by no more than 4 mm (`FLAT_TOL_M`). The element is stuck at the window mean minus bias, and the onset is at the window start. This is the worst case, closest to the reading.

Both hydraulic families need the same minimum fault size, 0.05 L/s of missing water. `test_minimum_fault_size_is_symmetric_for_pump_and_leak` checks that a 0.10 L/s leak and a 0.10 L/s pump deficit admit each other as viable alternatives and are both not identifiable at `AMBIGUOUS_SITE`.

**Step 2: keep alternatives the alarm window cannot rule out.** An alternative stays viable only if a noisy investigator could not tell its window from the truth's. All of these must hold:

- max |ΔLT-101| ≤ 4·√2·3 mm ≈ 17.0 mm;
- max |ΔFT-102| ≤ 4 × 0.01 = 0.04 L/s;
- identical pump command and run-feedback series.

**Step 3: run each permitted test.** For each viable alternative, every permitted test runs once from t = 0 on fresh noise-free panels of both the truth and the alternative. A test separates them if any of its quantities differs by more than a 4-sigma threshold based on datasheet noise.

Rate thresholds use σ_r, the sd that an OLS slope fitted to the logged sample times would have with independent 3 mm LT-101 noise:

```
sigma_r = 3 mm / sqrt( sum over samples of (t_i - t_mean)^2 ),   t in minutes
```

A noise-free rate is the OLS slope of the noise-free readings (0 if they are constant).

| Test | Probe | Quantity | Threshold |
|---|---|---|---|
| `inlet_flow` | FT-101: 30 s fit, then 60 s averaging | Mean inlet flow | 4 × (0.02 × max(q_a, q_b) + 0.01 L/s) |
| `independent_level` | DIP-101 (120 s) | Dip level | 4 × 5 mm = 20 mm |
| | | Dip minus same-step LT-101 | 4 × sqrt(5² + 3²) mm ≈ 23.3 mm |
| `pump_stop_test` | Hold = min(`max_pump_stop_s`, `max_extra_sim_s`), run only if ≥ 60 s and on the 10 s grid | LT-101 change over the test | 4 × √2 × 3 mm ≈ 17.0 mm |
| | | OLS LT-101 rate over the test's samples (t = 0 to the end of the hold) | 4 × σ_r of the truth's samples |
| `wait` | Advance by the full allowance, run only if ≥ 30 s | LT-101 change since t = 0 | 4 × √2 × 3 mm ≈ 17.0 mm |
| | | Rate change: OLS rate over the wait's samples minus OLS rate over the alarm window | 4 × sqrt(σ_r,wait² + σ_r,window²), from the truth's samples |

Resulting values: σ_r is about 0.072 mm/min for the 91-sample alarm window. A 300 s stop test (31 samples) gives σ_r ≈ 0.36 mm/min and a rate threshold of about 1.45 mm/min. The wait rate-change threshold is about 0.61, 0.41, 0.34 and 0.31 mm/min for waits of 600, 900, 1200 and 1800 s.

**Step 4: decide.** The case is identifiable if and only if each viable alternative is separated by at least one permitted test. Different alternatives may be separated by different tests. With no viable alternative, the case is identifiable.

**History** (from `eval/scenarios/FROZEN.md`).

- The v1 scenario files were regenerated before any evaluation to change the window-viability rule. The code uses the 4-sigma rule (about 17 mm) for viability and the 2 mm tolerance only to certify twin pairs.
- v2 followed an adversarial review on 2026-10-26, after the deterministic reference procedure (arm A) had run on `heldout-v1` and before any Nemotron evaluation. v1 judged waiting and the stop test only on end-point readings; v2 also compares the fitted OLS rate. v1 used different minimum fault sizes (0.12 L/s for a pump deficit and 0.05 L/s for a leak); v2 uses 0.05 L/s for both.
- With v1's 20-minute night-shift allowance, v1's non-identifiable pump-vs-leak cases (H08, H13) are separable in principle under the v2 rule. The night-shift allowance is now 10 minutes, where the falling-level pair is not separable by waiting (Section 14).
- In the same change FT-101 gained the 30 s fit and all actions moved to the 10 s grid, so measurements from v2 runs are not comparable with v1 runs.

**Limitations.** The docstring states the first three; the rest follow from the code.

- **Single faults only.** The oracle considers single faults, not combinations of faults.
- **One test at a time.** Each test is judged on its own from t = 0. Sequences of tests, combined evidence and the shared time allowance are not considered.
- **Practical rule, not a guarantee.** The noise-free 4-sigma criterion is a working separability rule, not a formal statistical guarantee.
- **One best-fit point per family.** Each family gets a single parameter value fitted to the end point. Other parameter values that might also fit the window are not explored.
- **Leak at the tank bottom.** Leak alternatives use h_leak = 0. Per the argument in Section 12.1, for a given leak flow that is the leak whose fall slows least, so it is the hardest leak to separate by waiting.
- **Fixed probe settings.** FT-101 averages for 60 s after its 30 s fit, the stop test uses the maximum permitted hold, and the wait uses the full allowance.
- **Datasheet thresholds.** Thresholds use datasheet noise, and σ_r assumes independent noise at each logged sample. They ignore the LT-101 lag, quantisation and the mismatch noise scale. (Mismatch biases are not part of the thresholds; each alternative keeps the truth's mismatch configuration.)
- **Stuck onset.** The stuck-sensor alternative uses only an onset at the window start.

---

## 16. Remedy verification (`verify_remedy`, `evaluator-v3`)

Versions, from the code comment: v2 excluded overflow from the hydraulic check; v3 added the necessity check below and, in grading, the `wrong_inconclusive` category. Grading is described in `EVALUATION.md`.

| Recommended remedy | Maintenance action |
|---|---|
| `replace_or_repair_pump` | `repair_pump` |
| `repair_tank_leak` | `repair_tank_leak` |
| `replace_level_sensor` | `replace_level_sensor` |
| `no_action` | `no_action` |

**When it runs**

- **In the app.** A diagnosis that recommends one of the three repairs waits for approval. A `no_action` diagnosis or an inconclusive submission ends without a remedy check. If the technician declines, nothing is applied.
- **In the evaluation harness.** `eval/run_eval.py` runs `verify_remedy` for every diagnosed run whose remedy is in the table above, `no_action` included.
- Both callers pass the true fault family, so all three checks below apply.

**Procedure**

1. Apply the maintenance action to the run's private plant.
2. Run the checks on a deep copy, so the check itself does not advance the run's plant.
3. On the copy, command P-101 ON, let it settle for 60 s, then simulate a 600 s horizon.

**Pass criteria.** All three checks must pass.

- **Hydraulics.** The true net flow over the horizon must be within 0.03 L/s of the healthy nominal balance:
  - net flow = (Δinflow − Δdemand_out − Δleak_out) / Δt;
  - healthy nominal balance = 1.20 L/s − mean served demand.

  Overflow is not counted (the v2 change). Per the code comment, spilling over the weir is not a fault and must not hide or fake one. Overflow volume during the check is reported separately as `overflow_during_check_L`.
- **Instrumentation.** The maximum |sensing element − true level| over the 10 s truth-log ticks in the horizon must be ≤ 5 mm.
- **Necessity** (the v3 change). The applied remedy must be the one the true fault needed (`CORRECT_REMEDY`: `no_fault` needs `no_action`). Unnecessary or wrong maintenance fails even when the plant ends up healthy. If no true family is passed, this check is left out.

**What the agent and the judge see (app)**

- `RunManager.decide_remedy` stores the check result in `SealedStore.remedy_checks`. It appears only in the judge reveal, as `remedy_check`.
- It then calls `InstrumentPanel.post_maintenance_observation(300)` on the run's panel. This commands P-101 ON, advances the run's plant by 300 s and returns the 30 newly logged public samples' summary (`window_summary`) and alarm evaluation (`evaluate_alarms`). The 300 s is not charged to the investigation's allowance.
- The public response carries the approval, the remedy, the maintenance action, `post_maintenance_observation` and a note that the independent check is sealed until reveal. `test_run_survives_restart_and_rebuild_is_deterministic` checks that the response has `post_maintenance_observation`, that the check's numbers and pass flag are not in it, and that the reveal's `remedy_check` passed.

**Consequences of these criteria**

- **Small faults pass the hydraulic check.** A remaining pump deficit or leak smaller than 0.03 L/s (2.5 % of rated delivery) passes it. The necessity check still fails a remedy that differs from the one the true fault needed.
- **Unnecessary maintenance fails.** On a healthy plant, `replace_or_repair_pump` passes hydraulics and instrumentation but fails necessity (`test_unnecessary_maintenance_on_a_healthy_plant_is_not_verified`).
- **Rating mismatch fails.** The expected value uses the nominal pump rating. A case whose true pump rating differed from the datasheet by more than 0.03 L/s would fail every remedy. No current scenario (including `dev-v2` and `heldout-v2`) sets a pump-rating mismatch.
- **Bias is not checked.** The tracking check compares the sensing element, before bias and noise, with the true level. An LT-101 calibration bias is not checked here.
- **The post-maintenance observation is public data, not a verdict.** It uses the same noisy instruments and alarm thresholds as the investigation.

---

## 17. Verification tests

All tests below exist in `backend/tests/`.

| Claim | Test (file::function) |
|---|---|
| 0.2 L/s into 2.0 m² gives 6 mm/min | `test_physics.py::test_units_rate_conversion` |
| With no flows, volume is exactly constant and the inflow, demand and leak totals stay zero | `test_physics.py::test_no_flow_volume_is_constant` |
| Constant net flow matches the linear analytic solution (rel 1e-12, 1200 s) | `test_physics.py::test_constant_net_flow_matches_analytic_linear_solution` |
| Pump start matches the first-order analytic solution for flow and cumulative inflow (rel 1e-9, 60 s) | `test_physics.py::test_pump_start_matches_first_order_analytic_solution` |
| Torricelli drain matches the analytic solution (rel 1e-9, 900 s) | `test_physics.py::test_torricelli_drain_matches_analytic_solution` |
| A leak drains to empty without negative volume and conserves water (< 1e-12 m³) | `test_physics.py::test_leak_drains_to_empty_without_negative_volume_and_conserves_water` |
| Volume is clipped at the weir and overflow volume matches the analytic value | `test_physics.py::test_overflow_is_accounted_not_destroyed` |
| Demand stops at the outlet level and is booked as unmet | `test_physics.py::test_demand_stops_below_outlet_and_is_booked_as_unmet` |
| Bounds and conservation (< 1e-11 m³) hold for every fault family with pump cycling, seeds 1–3 | `test_physics.py::test_conservation_and_bounds_with_every_fault_and_pump_cycling` |
| Noise is reproducible for the same seed and differs for a different seed | `test_physics.py::test_seeded_noise_is_reproducible_and_seed_dependent` |
| LT-101 scatter matches the datasheet 3 mm (within 10 %), mean error < 0.5 mm | `test_physics.py::test_level_noise_has_the_documented_spread` |
| Historian runs from −900 s to 0 s at 10 s spacing | `test_physics.py::test_logical_time_and_historian_cadence` |
| A reduced pump lowers delivered flow, but command and run feedback stay 1 | `test_physics.py::test_reduced_pump_lowers_delivered_flow_but_not_run_feedback` |
| Leak outflow equals C·sqrt(h) (within 0.2 %) | `test_physics.py::test_leak_adds_outflow_that_depends_on_level` |
| A stuck LT-101 reads constant (noise-free) while the true level rises; the dip reads the true level | `test_physics.py::test_stuck_sensor_reads_constant_while_true_level_changes` |
| `repair_tank_leak` removes the leak; an unknown action raises `ValueError` (the other actions are exercised only through the remedy-verification tests) | `test_physics.py::test_maintenance_restores_parameters` |
| Twin members have different hidden causes | `test_twins.py::test_twin_members_have_different_hidden_causes` |
| Noise-free twin windows match within the declared 2 mm tolerance; FT-102 difference is 0; same commands and run feedback | `test_twins.py::test_noise_free_alarm_windows_match_within_declared_tolerance` |
| Noisy twin windows raise the same alarms and their trends agree within 4 combined standard errors | `test_twins.py::test_noisy_windows_raise_the_same_alarms_and_trends_agree` |
| Falling pair: FT-101 (0.75 vs 1.20 L/s) and the stop test separate the members; the dip does not | `test_twins.py::test_falling_pair_is_separated_by_inlet_flow_and_pump_stop_but_not_by_dip` |
| Flat pair: the dip, FT-101 and the stop test separate the members | `test_twins.py::test_flat_pair_is_separated_by_dip_inlet_flow_and_pump_stop` |
| Every twin member is identifiable at the standard site | `test_twins.py::test_every_member_is_identifiable_with_standard_instruments` |
| Twin members are not identifiable at `AMBIGUOUS_SITE` (600 s allowance) | `test_twins.py::test_members_are_not_identifiable_when_separating_instruments_are_unavailable` |
| The oracle finds both a balancing pump and a balancing leak as viable alternatives to the stuck sensor | `test_twins.py::test_flat_reading_also_admits_a_balancing_leak_which_the_oracle_finds` |
| The leak wait prediction expects the fall to slow, the pump prediction expects no change of rate, and the leak prediction is closer to the noise-free simulator | `test_twins.py::test_leak_wait_prediction_models_orifice_slowing_unlike_the_pump_hypothesis` |
| The minimum fault size is 0.05 L/s for both pump and leak; 0.10 L/s pump and leak cases are mutual viable alternatives and both not identifiable at `AMBIGUOUS_SITE` | `test_twins.py::test_minimum_fault_size_is_symmetric_for_pump_and_leak` |
| The correct remedy verifies and a wrong remedy does not (three twin members) | `test_persistence_and_evaluator.py::test_correct_remedy_verifies_and_wrong_remedy_does_not` |
| `no_action` verifies on a healthy plant and fails on a leak | `test_persistence_and_evaluator.py::test_no_action_on_healthy_plant_verifies_but_not_on_a_faulty_one` |
| Unnecessary pump repair on a healthy plant passes hydraulics and tracking but fails the necessity check | `test_persistence_and_evaluator.py::test_unnecessary_maintenance_on_a_healthy_plant_is_not_verified` |
| After approval the response carries `post_maintenance_observation` and no check numbers; the sealed check appears in the reveal | `test_persistence_and_evaluator.py::test_run_survives_restart_and_rebuild_is_deterministic` |
| Grading categories, including `wrong_inconclusive` for an inconclusive that rules out the true cause | `test_persistence_and_evaluator.py::test_grading_categories` |
| Pump stop hold limit is enforced in the backend | `test_tools.py::test_site_limit_on_pump_stop_hold_is_enforced_in_backend` |
| Unavailable instruments and forbidden actions are refused and use no logical time | `test_tools.py::test_unavailable_instruments_and_forbidden_actions_are_refused` |
| The logical time allowance is enforced (600 s at `AMBIGUOUS_SITE`: a 500 s wait succeeds, a further 200 s is refused) | `test_tools.py::test_simulated_time_allowance_is_enforced` |
| FT-101 for 60 s is fitted from t = 0 and averages t = 30 to 90 s; a following dip ends at t = 210 s with an LT-101 sample from t = 210 s | `test_tools.py::test_measurements_get_sequential_evidence_ids_and_timestamps` |
| Off-grid durations (45, 95, 125 s) are rejected before the plant is touched | `test_tools.py::test_off_grid_durations_are_rejected_before_touching_the_plant` |
| After a 30 s wait and a 50 s FT-101 measurement, the dip still has a same-step LT-101 sample | `test_tools.py::test_dip_reading_always_has_a_same_step_lt101_comparison` |
| FT-101 right after a stop test reads the steady pump flow (within 4 stated sd of 1.20 L/s) | `test_tools.py::test_inlet_flow_after_a_stop_test_is_measured_at_steady_state` |
| An unexpected exception inside a tool becomes a rejected call with a fixed message | `test_tools.py::test_unexpected_tool_failure_is_contained` |
| Identical actions with the same seed give identical evidence | `test_tools.py::test_identical_actions_reproduce_identical_evidence` |
| The source of `agent/public_model.py` names no plant, case, instrument or judge code | `test_tools.py::test_predictions_use_only_public_inputs` |
| For five cases, listed hidden keys, label words and values do not appear in model requests, API responses, logs or exports before reveal (scripted provider, not a live model) | `test_leakage.py::test_no_hidden_state_in_model_requests_api_logs_or_exports` |
| With the same seed, the two falling-level twins give the same first message apart from digits | `test_leakage.py::test_twin_briefs_differ_only_in_measured_numbers` |
| Private objects redact their `repr` | `test_leakage.py::test_private_objects_redact_their_repr` |
| Live mode without an API key is refused, not replaced by a substitute | `test_leakage.py::test_live_mode_without_key_is_refused_not_substituted` |

How to run (from `backend/`):

```
..\.venv\Scripts\python -m pytest -q -W ignore
..\.venv\Scripts\python -m pytest tests/test_physics.py tests/test_twins.py tests/test_persistence_and_evaluator.py
```

On 2026-10-26 the full suite gave `106 passed` and the three files above gave `53 passed`, in a local run on Windows. Those runs are not stored as result files.

**Not covered by any test:**

- `demand_steps`;
- `leak_height_m` > 0;
- the physical effect of each `MismatchConfig` field;
- the noise statistics of FT-102, FT-101 and DIP-101;
- the LT-101 lag time constant;
- the 0.50 m pump-stop interlock;
- the LAL-101 and BAL-101 thresholds themselves. Tests only check that twins raise the same alarms;
- the wait test separating any case. The values in Section 14 (separable at 900 s and longer) are not asserted;
- the content of `post_maintenance_observation`. Only its presence is tested.

---

## 18. Assumptions and limitations

- **Single fault per case.** The catalogue has three fault families plus `no_fault`. The plant can hold several fault parameters at once, but no case, twin or oracle hypothesis combines them.
- **Pump delivery does not depend on head or tank level.** There is no pump curve and no suction-side model, and the supply sump never runs dry. Spin-up and run-down share one first-order time constant (5 s). Run feedback always equals the command.
- **The tank is a vertical cylinder with a flat bottom and constant area,** so h = V / A everywhere.
- **Demand is constant within a run unless `demand_steps` is given.** No current preset, twin or scenario uses `demand_steps`, and no test covers it.
- **Demand does not depend on head.** It switches fully on or off at the outlet level, judged once at the start of each step. There is no partial flow near the nozzle.
- **The leak is a fixed Torricelli orifice.** The coefficient does not change over time. All current cases use h_leak = 0.
- **Overflow is an instantaneous end-of-step clip at the weir crest.** There is no weir head-discharge relation.
- **No temperature, density, viscosity, evaporation, sloshing, foaming or air-entrainment effects.** Water is incompressible and volume stands in for mass.
- **Sensor noise is white Gaussian noise.** It is independent between samples and between channels. There is no drift, no spikes and no dead band, and only LT-101 has a lag.
- **FT-101 is one draw with a stated sd, after a fixed 30 s fitting period.** No sampled time series is simulated, and the fitting time does not vary.
- **A stuck LT-101 freezes only the sensing element.** Transmitter noise and bias still apply.
- **Model mismatch covers only five quantities:** true tank area, true pump rating, LT-101 noise scale, LT-101 bias and FT-102 bias.
- **Time is logical only, with a fixed 1 s integration step.** Every action lasts a multiple of the 10 s historian interval, so it starts and ends on a logged sample.
- **Reproducibility is shown only within one Python install.** It has not been verified across Python versions.
- **Predictions use the nominal model and a bottom leak.** `predict_under_hypothesis` uses the datasheet area and pump rating, a demand fixed at the window mean, and, for leaks, an orifice at the tank bottom (Section 12.1).
- **Oracle limits are listed in Section 15.** In short: single faults, one best-fit parameter per family, each test alone from t = 0, and a practical 4-sigma rule using datasheet noise and independent-noise rate sds.
- **Remedy-check limits are listed in Section 16.** In short: compared against the nominal pump rating, a 0.03 L/s tolerance, the bias is not checked, overflow is excluded, and the necessity check compares the remedy with the true fault family only.
- **No external validation.** The model and its parameters have not been validated against a physical plant, field data or a reference simulator. Agreement is shown only against the analytic solutions and invariants in Section 17.
