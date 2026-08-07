import type { ReactNode } from "react";

import { useView } from "../hooks/useView";
import type { Envelope } from "../types";
import { StateBoundary } from "./StateBoundary";
import { StatusStrip } from "./StatusStrip";

// One fetch per view, then the StatusStrip (from that view's envelope) above the StateBoundary. The
// StatusStrip shows only once there is an envelope; during loading/failure the StateBoundary owns
// the screen. Keeps "StatusStrip reads the active view's envelope; does not fetch" true.
interface Props<T> {
  path: string;
  children: (data: T, envelope: Envelope<T>) => ReactNode;
}

export function ViewShell<T>({ path, children }: Props<T>) {
  const state = useView<T>(path);
  return (
    <section className="view">
      {state.kind === "ready" && <StatusStrip envelope={state.envelope} />}
      <StateBoundary state={state}>
        {(envelope) => children(envelope.data, envelope)}
      </StateBoundary>
    </section>
  );
}
