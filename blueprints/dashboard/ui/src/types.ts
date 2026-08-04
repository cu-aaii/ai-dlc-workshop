// The response envelope, mirrored from the API's shaping.py (AR-03, AR-05). `freshness` is the
// server's judgement (U-01's evaluate_freshness) and is NEVER recomputed here (US-05): two viewers
// must reach the same verdict.

export type ViewName = "inventory" | "grouping" | "tag-gaps" | "status";

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
