// The response envelope, mirrored from the API's shaping.py (AR-03, AR-05). `freshness` is the
// server's judgement (U-01's evaluate_freshness) and is NEVER recomputed here (US-05): two viewers
// must reach the same verdict.

export type ViewName =
  | "inventory"
  | "grouping"
  | "tag-gaps"
  | "status"
  | "financial"
  | "adoption";

export const REQUIRED_TAGS = [
  "cornell:owner",
  "cornell:blueprint",
  "cornell:blueprint-version",
  "cornell:deployment-id",
] as const;
export type RequiredTag = (typeof REQUIRED_TAGS)[number];

export interface Counts {
  resources: number;
  skipped: number;
  duplicates_removed: number;
  raw_returned: number;
}

export type EnvelopeStatus = "ok" | "stale" | "no_data" | "error";
export type Freshness = "fresh" | "stale" | "invalid" | null;

export interface Envelope<T> {
  status: EnvelopeStatus;
  collected_at: string | null;
  freshness: Freshness;
  counts: Counts;
  data: T;
}

// A single view's lifecycle. `failed` carries the HTTP status (0 = network/non-JSON failure), so
// StateBoundary can show the row-6 generic error without leaking anything internal.
export type ViewState<T> =
  | { kind: "loading" }
  | { kind: "ready"; envelope: Envelope<T> }
  | { kind: "failed"; httpStatus: number };

// --- data payloads, one per endpoint --------------------------------------------------
export interface ResourceRow {
  arn: string;
  service: string;
  resource_type: string;
  region: string;
  tags: Record<string, string>;
}

export interface GroupRow {
  value: string | null; // null == the missing group, pinned last by the server
  count: number;
}
export interface GroupingPayload {
  tag_key: string;
  total: number;
  groups: GroupRow[];
}

export interface IncompleteRow {
  arn: string;
  service: string;
  region: string;
  missing_tags: string[];
}
export interface TagGapPayload {
  complete_count: number;
  incomplete: IncompleteRow[];
}

export interface StatusPayload {
  schema_version: string;
  skipped_reasons: Record<string, number>;
}

// --- FR-9 / FR-10: cost and usage sections (A4.1) ---------------------------------------
//
// These use a DIFFERENT envelope from the four inventory views above, and deliberately so. The store
// holds three objects with three owners on two cadences, so there is no single snapshot age: each
// section carries its own `state` and its own `collected_at`. HTTP status is always 200 -- a section's
// absence is data, not a request failure, because returning 503 for a missing cost object would hide a
// perfectly good usage payload.
export type SectionState = "ok" | "absent" | "unreadable";

export interface SectionEnvelope<T> {
  status: "ok";
  state: SectionState;
  collected_at: string | null;
  data: T | null;
}

export interface CostTotals {
  day?: string;
  month_to_date?: string;
  year_to_date?: string;
}

// `outcome: "no_tasks"` is NOT zero (COST-12): "no tasks completed" and "each task was free" are
// different claims, and only one can be true.
export interface PerTask {
  state: SectionState;
  outcome: "ok" | "no_tasks" | "no_cost" | null;
  amount: string | null;
  completed_tasks?: number;
  cost_basis?: string;
}

export interface CostSummaryPayload {
  currency: string;
  totals: CostTotals;
  // What the "day" figure actually covers. NOT the same as collected_at -- Cost Explorer lags
  // 24-48h, so "today" means the last finalized day (COST-04).
  covered_through: string | null;
  is_estimate: boolean;
  ce_calls: number | null;
}

export interface CostGroupRow {
  key: string;
  amount: string;
}

// `unattributed` is a NAMED SIBLING of `attributed`, never an entry in the list. That shape is what
// stops the empty-value tag group (`cornell:blueprint$`) rendering as a blueprint name (FR-10.3.6).
export interface AttributionPayload {
  attributed: CostGroupRow[];
  unattributed: string;
  fully_unattributed: boolean;
}

export interface CostBreakdownPayload {
  by_blueprint: AttributionPayload;
  by_deployment: AttributionPayload;
  by_service: CostGroupRow[];
  is_estimate: boolean;
}

export type CounterState = "ok" | "no_data_yet" | "not_instrumented" | "cannot_read";

export interface ModelRow {
  model: string;
  requests: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost: string | null;
  rate_missing: boolean;
}

export interface UsageModelsPayload {
  aws_state: CounterState;
  declared_state: CounterState;
  not_instrumented: string[];
  models: ModelRow[];
  estimated_total: string;
  is_estimate: boolean;
  rates_state: "ok" | "not_configured" | "malformed";
  missing_rates: string[];
}

// A rate keeps its numerator and denominator (TEL-06) so it can be re-aggregated. `rate: null` with a
// state is NOT zero -- "no requests, so no error rate" differs from "every request succeeded".
export interface RateRow {
  rate: number | null;
  percent: number | null;
  numerator: number;
  denominator: number;
  state: CounterState;
}

export interface UsageQualityPayload {
  aws_state: CounterState;
  declared_state: CounterState;
  not_instrumented: string[];
  error_rate: RateRow;
  timeout_rate: RateRow;
  approval_rate: RateRow;
  success_rate: RateRow;
}

export type SectionViewState<T> =
  | { kind: "loading" }
  | { kind: "ready"; envelope: SectionEnvelope<T> }
  | { kind: "failed"; httpStatus: number };
