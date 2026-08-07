import { render, screen } from "@testing-library/react";

import { StateBoundary } from "../StateBoundary";
import type { Counts, Envelope, EnvelopeStatus, ViewState } from "../../types";

const COUNTS: Counts = { resources: 3, skipped: 0, duplicates_removed: 0, raw_returned: 3 };

function envelope(status: EnvelopeStatus, resources: number): Envelope<string> {
  return {
    status,
    collected_at: "2026-08-04T12:00:00+00:00",
    freshness: status === "stale" ? "stale" : "fresh",
    counts: { ...COUNTS, resources },
    data: "payload",
  };
}

function ready(status: EnvelopeStatus, resources = 3): ViewState<string> {
  return { kind: "ready", envelope: envelope(status, resources) };
}

const child = () => <div data-testid="child">rendered data</div>;

function renderState(state: ViewState<string>) {
  return render(<StateBoundary state={state}>{child}</StateBoundary>);
}

describe("StateBoundary — the six states", () => {
  it("loading shows a status region, no data", () => {
    renderState({ kind: "loading" });
    expect(screen.getByTestId("state-boundary-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("row 5: 503 failure shows the generic error, no internals, no data", () => {
    renderState({ kind: "failed", httpStatus: 503 });
    expect(screen.getByTestId("state-boundary-error")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("row 6: network failure adds the request-failed note", () => {
    renderState({ kind: "failed", httpStatus: 0 });
    expect(screen.getByTestId("state-boundary-error")).toHaveTextContent(/request itself failed/i);
  });

  it("row 4: no_data renders its own message, not data", () => {
    renderState(ready("no_data", 0));
    expect(screen.getByTestId("state-boundary-no-data")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("row 3: ok with zero resources renders the no-resources message, not data", () => {
    renderState(ready("ok", 0));
    expect(screen.getByTestId("state-boundary-no-resources")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("row 1: ok with resources renders the data, no notice", () => {
    renderState(ready("ok", 3));
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.queryByTestId("state-boundary-no-resources")).not.toBeInTheDocument();
  });

  it("row 2: stale renders the banner AND the data", () => {
    renderState(ready("stale", 3));
    expect(screen.getByTestId("state-boundary-stale-banner")).toBeInTheDocument();
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  it("US-06: no_data and no-resources are DISTINCT screens", () => {
    const a = render(<StateBoundary state={ready("no_data", 0)}>{child}</StateBoundary>);
    expect(a.queryByTestId("state-boundary-no-data")).toBeInTheDocument();
    expect(a.queryByTestId("state-boundary-no-resources")).not.toBeInTheDocument();
    a.unmount();

    const b = render(<StateBoundary state={ready("ok", 0)}>{child}</StateBoundary>);
    expect(b.queryByTestId("state-boundary-no-resources")).toBeInTheDocument();
    expect(b.queryByTestId("state-boundary-no-data")).not.toBeInTheDocument();
  });
});
