import type { ReactNode } from "react";

import type { Envelope, ViewState } from "../types";
import { formatTimestamp } from "../format";

// The ONLY component that decides whether to render data -- the six states live here once, so
// `no_data` and `ok`-with-zero-resources cannot drift into looking the same (frontend-components.md).
// Every view delegates to it. Live regions (role=status/alert) announce a view swap to a screen
// reader (WCAG 2.2 AA, non-waivable).
interface Props<T> {
  state: ViewState<T>;
  children: (envelope: Envelope<T>) => ReactNode;
}

export function StateBoundary<T>({ state, children }: Props<T>) {
  if (state.kind === "loading") {
    return (
      <p role="status" className="notice" data-testid="state-boundary-loading">
        Loading…
      </p>
    );
  }

  if (state.kind === "failed") {
    // Rows 5 and 6: 503 (unreadable/invalid) and network/non-JSON. Same words -- from the user's
    // side both mean "the data cannot be trusted"; the distinction lives in the logs and alarm.
    return (
      <div role="alert" className="notice notice-error" data-testid="state-boundary-error">
        <span aria-hidden="true" className="status-glyph">✕</span>
        <div>
          <h2>The dashboard cannot read its data right now.</h2>
          {state.httpStatus === 0 && <p>The request itself failed. Try again shortly.</p>}
        </div>
      </div>
    );
  }

  const envelope = state.envelope;

  if (envelope.status === "no_data") {
    return (
      <div role="status" className="notice" data-testid="state-boundary-no-data">
        <h2>No data collected yet.</h2>
        <p>The collector has not completed a successful run.</p>
      </div>
    );
  }

  if (envelope.status === "ok" && envelope.counts.resources === 0) {
    // Deliberately different wording, heading and icon from "no data" above -- the US-06 crux.
    return (
      <div role="status" className="notice" data-testid="state-boundary-no-resources">
        <h2>No tagged resources found.</h2>
        <p>The collector ran successfully and found nothing carrying <code>cornell:*</code> tags.</p>
      </div>
    );
  }

  if (envelope.status === "error") {
    // A 200 body should not carry status "error", but if it ever does, fail closed.
    return (
      <div role="alert" className="notice notice-error" data-testid="state-boundary-error">
        <span aria-hidden="true" className="status-glyph">✕</span>
        <h2>The dashboard cannot read its data right now.</h2>
      </div>
    );
  }

  return (
    <>
      {envelope.status === "stale" && (
        <div role="status" className="banner-stale" data-testid="state-boundary-stale-banner">
          <span aria-hidden="true" className="status-glyph">⚠</span>
          <span>
            <strong>Data is stale.</strong> Last collected {formatTimestamp(envelope.collected_at)}.
          </span>
        </div>
      )}
      {children(envelope)}
    </>
  );
}
