import type { ReactNode } from "react";

import type { SectionEnvelope, SectionViewState } from "../types";
import { formatTimestamp } from "../format";

// The section analogue of StateBoundary: the one place that decides whether a cost/usage panel has
// data. Three states must stay visibly distinct (NFR-T7), and the reason is the whole deliverable --
// with no blueprint instrumented, most panels are "not instrumented", and rendering that as an empty
// table or a zero would claim an application is UNUSED when it is merely UNMEASURED.
//
// Each section carries its own timestamp (A4.1): there is no single snapshot age, because cost is
// ~24-48h stale while usage is an hour stale.
interface Props<T> {
  state: SectionViewState<T>;
  label: string;
  children: (data: T, envelope: SectionEnvelope<T>) => ReactNode;
}

export function SectionBoundary<T>({ state, label, children }: Props<T>) {
  if (state.kind === "loading") {
    return (
      <p role="status" className="notice" data-testid="section-loading">
        Loading {label}…
      </p>
    );
  }

  if (state.kind === "failed") {
    return (
      <div role="alert" className="notice notice-error" data-testid="section-request-failed">
        <span aria-hidden="true" className="status-glyph">✕</span>
        <div>
          <h2>The {label} request failed.</h2>
          {state.httpStatus === 0 && <p>The request itself did not complete. Try again shortly.</p>}
        </div>
      </div>
    );
  }

  const envelope = state.envelope;

  if (envelope.state === "absent") {
    return (
      <div role="status" className="notice" data-testid="section-absent">
        <h2>No {label} collected yet.</h2>
        <p>The collector has not completed a successful run.</p>
      </div>
    );
  }

  if (envelope.state === "unreadable" || envelope.data === null) {
    // Deliberately different from "absent": one means nobody has collected it, the other means it
    // was collected and cannot be read. Different operator action, so different words.
    return (
      <div role="alert" className="notice notice-error" data-testid="section-unreadable">
        <span aria-hidden="true" className="status-glyph">✕</span>
        <div>
          <h2>The stored {label} cannot be read.</h2>
        </div>
      </div>
    );
  }

  return (
    <>
      <p className="section-age" data-testid="section-age">
        {label} collected {formatTimestamp(envelope.collected_at)}
      </p>
      {children(envelope.data, envelope)}
    </>
  );
}
