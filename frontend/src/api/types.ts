// Types for the FAULTLINE HTTP API (backend/faultline/api.py).
// Shapes follow docs/api-samples/*.json. Fields the UI does not rely on are
// left loose so that additive backend changes do not break the build.

export type RunStatus =
  | "ready"
  | "investigating"
  | "awaiting_approval"
  | "diagnosed"
  | "inconclusive"
  | "failed"
  | "cancelled";

/** "replay" = an imported recording; the original mode is in RunView.versions.recorded_mode. */
export type RunMode = "live" | "reference" | "unstarted" | "replay";
/** The investigator that produced a run's events (never "replay"). */
export type InvestigatorMode = "live" | "reference" | "unstarted";
export type RunKind = "blind" | "twin" | "guided" | string;
export type HypothesisId = "no_fault" | "pump_delivery_reduced" | "tank_leak" | "level_sensor_stuck";
export type HypothesisStatus = "open" | "supported" | "weakened" | "ruled_out";

export const TERMINAL: RunStatus[] = ["diagnosed", "inconclusive", "failed", "cancelled"];
export const ACTIVE: RunStatus[] = ["ready", "investigating"];

export interface CheckResult {
  ok: boolean;
  at: number;
  error?: string;
  model_listed?: boolean;
  nvidia_models?: string[];
}

export interface StatusResponse {
  provider: {
    name: string;
    base_url: string;
    model: string;
    key_configured: boolean;
    reasoning: string;
    last_check: CheckResult | null;
  };
  budgets: {
    max_tool_calls: number;
    max_model_calls: number;
    wall_clock_s: number;
    request_timeout_s: number;
    max_retries: number;
  };
  spend: {
    estimated_total_usd: number;
    ceiling_usd: number;
    price_in_per_m: number;
    price_out_per_m: number;
    price_source: string;
  };
}

export interface ToolSpec {
  name: string;
  description: string;
  parameters: unknown;
}

export interface Nominal {
  tank: {
    tag: string;
    shape: string;
    cross_section_m2: number;
    height_m: number;
    overflow_level_m: number;
    demand_outlet_level_m: number;
  };
  pump: { tag: string; rated_delivery_L_s: number; note: string };
  instruments: Record<string, Record<string, unknown>>;
  historian_interval_s: number;
  alarms: Record<string, string>;
}

export interface TwinPairSummary {
  pair_id: string;
  title: string;
  situation: string;
}

export interface Catalog {
  hypotheses: Record<string, string>;
  tools: ToolSpec[];
  nominal: Nominal;
  twin_pairs: TwinPairSummary[];
}

export interface Warning {
  tag: string;
  text: string;
}

export type SiteConditions = Record<string, string | number>;

export interface PublicContext {
  warning: Warning[];
  situation: string;
  site: SiteConditions;
  nominal: Nominal;
  now_s: number;
}

export interface Budgets {
  max_tool_calls: number;
  max_model_calls: number;
  wall_clock_s: number;
  request_timeout_s: number;
  max_retries: number;
  max_output_tokens?: number;
  price_in_per_m?: number;
  price_out_per_m?: number;
}

export interface ProviderInfo {
  name?: string;
  model?: string;
  label?: string;
  base_url?: string | null;
}

export interface Counters {
  tool_calls: number;
  model_calls: number;
  provider_failures: number;
  rejected_tool_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  reasoning_tokens: number;
  usage_reported_calls: number;
  estimated_cost_usd: number;
  elapsed_s: number;
}

export interface BudgetPayload extends Partial<Counters> {
  tool_calls_remaining?: number;
  model_calls_remaining?: number;
  wall_clock_remaining_s?: number;
  simulated_time_remaining_s?: number;
}

export interface BoardEntry {
  id: HypothesisId | string;
  status: HypothesisStatus;
  supporting_evidence: string[];
  contradicting_evidence: string[];
  note?: string;
}

export interface Diagnosis {
  outcome: "diagnosed" | "inconclusive";
  primary_hypothesis: string | null;
  hypotheses: BoardEntry[];
  confidence: "low" | "medium" | "high";
  summary: string;
  recommended_remedy: string;
  requested_evidence?: string;
}

export interface RemedyCheck {
  check: string;
  passed: boolean;
  [k: string]: unknown;
}

export interface RemedyVerification {
  maintenance_action: string;
  horizon_s: number;
  checks: RemedyCheck[];
  passed: boolean;
  evaluator_version?: string;
  note?: string;
}

export interface PostMaintenanceObservation {
  t_start_s: number;
  t_end_s: number;
  summary: {
    level_trend: { rate_mm_per_min: number; rate_se_mm_per_min: number; first_m: number; last_m: number };
    FT102_mean_L_s: number;
    nominal_expected_rate_mm_per_min: number;
    rate_minus_nominal_mm_per_min: number;
  };
  alarms_on_this_window: { tag: string; text: string }[];
  note?: string;
}

export interface Remedy {
  approved: boolean;
  remedy: string | null;
  note?: string;
  maintenance_action?: string;
  post_maintenance_observation?: PostMaintenanceObservation;
  independent_check?: string;
  /** Only in runs recorded by an older version, where the check was public before reveal. */
  verification?: {
    maintenance_action: string;
    horizon_s: number;
    checks: RemedyCheck[];
    passed: boolean;
    evaluator_version?: string;
    note?: string;
  };
}

export interface Evidence {
  evidence_id: string;
  kind: string; // historian_window | inlet_flow_measurement | independent_level | pump_stop_test | observation_wait
  tool: string;
  t_start_s: number;
  t_end_s: number;
  summary: string;
  data: Record<string, unknown>;
}

export interface Prediction {
  prediction_id: string;
  kind: string;
  hypothesis: string;
  test: string;
  assumptions?: string[];
  [k: string]: unknown;
}

export interface SimulatedTime {
  now_s: number;
  used_s: number;
  limit_s: number;
}

export interface RunEvent {
  seq: number;
  at: number;
  type: string;
  payload: Record<string, unknown>;
}

export interface SeparationRow {
  test: string;
  quantity: string;
  delta: number;
  threshold: number;
  separates: boolean;
}

export interface Alternative {
  family: string;
  viable: boolean;
  reason: string;
  parameter: Record<string, unknown>;
  separation?: { rows: SeparationRow[]; separable_by: string[] };
}

export interface TruthSample {
  t_s: number;
  true_level_m: number;
  true_inflow_L_s?: number;
  true_leak_L_s?: number;
  sensed_level_m?: number;
  overflow_total_m3?: number;
}

export interface Grade {
  truth_family: string;
  identifiable: boolean;
  status: string;
  category: string;
  correct: boolean;
  confident_wrong: boolean;
  agent_outcome?: string;
  agent_primary?: string | null;
  agent_confidence?: string;
  remedy_matches_truth?: boolean;
  lucky_guess?: boolean;
  evaluator_version?: string;
}

export interface Reveal {
  fault_family: string;
  label: string;
  hidden_parameters: Record<string, unknown>;
  initial_true_level_m: number;
  model_mismatch: Record<string, unknown> | null;
  grade: Grade;
  identifiability: { identifiable: boolean; alternatives: Alternative[]; oracle_version?: string };
  twin: {
    pair_id: string;
    picked_slot: string;
    slot_labels: Record<string, string>;
    challenge_id?: string;
  } | null;
  remedy_check?: RemedyVerification | null;
  true_state_trace: TruthSample[];
}

export interface RunView {
  id: string;
  kind: RunKind;
  mode: RunMode;
  status: RunStatus;
  status_reason: string;
  created_at: number;
  terminal_at: number | null;
  public: PublicContext;
  budgets: Budgets;
  provider: ProviderInfo;
  counters: Partial<Counters>;
  diagnosis: Diagnosis | null;
  board: BoardEntry[] | null;
  remedy: Remedy | null;
  /** For imported replays: recorded_mode, recorded_at (epoch s) and the recorded run's versions. */
  versions: Record<string, unknown>;
  revealed: boolean;
  evidence: Evidence[];
  predictions: Prediction[];
  simulated_time: SimulatedTime | null;
  events: RunEvent[];
  reveal: Reveal | null;
}

export interface TelemetrySample {
  t_s: number;
  LT101_m: number;
  FT102_L_s: number;
  P101_command: number;
  P101_run_feedback: number;
}

export interface Telemetry {
  samples: TelemetrySample[];
  now_s: number;
  note: string;
}

export interface RunListItem {
  id: string;
  kind: RunKind;
  mode: RunMode;
  /** For imported replays: the mode the run was recorded in. */
  recorded_mode?: string | null;
  status: RunStatus;
  created_at: number;
  revealed: boolean;
  provider: ProviderInfo;
  outcome: string | null;
  primary_hypothesis: string | null;
  warning: string[];
}

export interface Presets {
  families: Record<string, string[]>;
  site_profiles: Record<string, SiteConditions>;
}

export interface WindowSummary {
  level_trend: {
    n: number;
    t_from_s: number;
    t_to_s: number;
    rate_mm_per_min: number;
    rate_se_mm_per_min: number;
    first_m: number;
    last_m: number;
    mean_m: number;
    reading_sd_mm: number;
  };
  FT102_mean_L_s: number;
  P101_command_on_fraction: number;
  nominal_expected_rate_mm_per_min: number;
  rate_minus_nominal_mm_per_min: number;
  implied_net_inflow_L_s?: number;
  implied_net_inflow_note?: string;
}

export interface TwinCard {
  slot: "alpha" | "beta";
  samples: TelemetrySample[];
  summary: WindowSummary;
  alarms: Warning[];
}

export interface TwinChallenge {
  challenge_id: string;
  pair_id: string;
  title: string;
  situation: string;
  candidate_causes: string[];
  site: SiteConditions;
  cards: TwinCard[];
  match: {
    noise_free_max_LT101_difference_mm: number;
    tolerance_mm: number;
    FT102_identical: boolean;
    pump_signals_identical: boolean;
    note: string;
  };
}
