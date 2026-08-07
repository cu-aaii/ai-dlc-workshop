import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SectionBoundary } from "../SectionBoundary";
import type { SectionEnvelope, SectionViewState } from "../../types";

// The three section states must stay visibly distinct (NFR-T7), and that is not a nicety here: with
// no blueprint instrumented, most panels render an empty state, so the empty state IS the visible
// deliverable. "Never collected", "collected but unreadable" and "the request failed" call for three
// different operator actions, so they must not read alike.

type Payload = { value: number };

const ready = (
  state: SectionEnvelope<Payload>["state"],
  data: Payload | null,
): SectionViewState<Payload> => ({
  kind: "ready",
  envelope: { status: "ok", state, collected_at: "2026-08-07T00:00:00+00:00", data },
});

const renderBoundary = (state: SectionViewState<Payload>) =>
  render(
    <SectionBoundary state={state} label="cost">
      {(data) => <p data-testid="payload">value {data.value}</p>}
    </SectionBoundary>,
  );

describe("SectionBoundary", () => {
  it("renders the payload when the section is ok", () => {
    renderBoundary(ready("ok", { value: 42 }));
    expect(screen.getByTestId("payload")).toHaveTextContent("value 42");
    expect(screen.getByTestId("section-age")).toBeInTheDocument();
  });

  it("shows a loading state before the fetch resolves", () => {
    renderBoundary({ kind: "loading" });
    expect(screen.getByTestId("section-loading")).toBeInTheDocument();
  });

  it("distinguishes absent from unreadable", () => {
    const absent = renderBoundary(ready("absent", null));
    expect(screen.getByTestId("section-absent")).toBeInTheDocument();
    expect(screen.queryByTestId("section-unreadable")).toBeNull();
    absent.unmount();

    renderBoundary(ready("unreadable", null));
    expect(screen.getByTestId("section-unreadable")).toBeInTheDocument();
    expect(screen.queryByTestId("section-absent")).toBeNull();
  });

  it("treats an ok state with null data as unreadable rather than rendering nothing", () => {
    // Defensive: a section that claims ok but carries no payload is a contract violation, and
    // rendering a blank panel would hide it.
    renderBoundary(ready("ok", null));
    expect(screen.getByTestId("section-unreadable")).toBeInTheDocument();
  });

  it("distinguishes a failed request from an absent section", () => {
    renderBoundary({ kind: "failed", httpStatus: 500 });
    expect(screen.getByTestId("section-request-failed")).toBeInTheDocument();
    expect(screen.queryByTestId("section-absent")).toBeNull();
  });

  it("announces the error states assertively and the empty states politely", () => {
    // A screen reader must be interrupted for an error, not for "nothing collected yet".
    const absent = renderBoundary(ready("absent", null));
    expect(screen.getByTestId("section-absent")).toHaveAttribute("role", "status");
    absent.unmount();

    renderBoundary(ready("unreadable", null));
    expect(screen.getByTestId("section-unreadable")).toHaveAttribute("role", "alert");
  });

  it("never renders the payload for any non-ok state", () => {
    for (const state of [
      { kind: "loading" } as SectionViewState<Payload>,
      { kind: "failed", httpStatus: 0 } as SectionViewState<Payload>,
      ready("absent", null),
      ready("unreadable", null),
    ]) {
      const view = renderBoundary(state);
      expect(screen.queryByTestId("payload")).toBeNull();
      view.unmount();
    }
  });
});
