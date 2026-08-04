// Same-origin /api/* (Application Design Q4): no CORS, no credentials, no token (FR-4.5). A view
// state is derived from one fetch; a non-2xx or a non-JSON body becomes `failed`, which
// StateBoundary renders as the generic error rather than crashing.

import type { Envelope, ViewState } from "./types";

export const API_BASE = "/api";

export async function fetchEnvelope<T>(path: string): Promise<ViewState<T>> {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { accept: "application/json" },
    });
    if (!res.ok) {
      return { kind: "failed", httpStatus: res.status };
    }
    const envelope = (await res.json()) as Envelope<T>;
    return { kind: "ready", envelope };
  } catch {
    // Network failure or non-JSON body -> row 6. httpStatus 0 marks "the request itself failed".
    return { kind: "failed", httpStatus: 0 };
  }
}
