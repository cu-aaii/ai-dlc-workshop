import { useEffect, useState } from "react";

import { fetchEnvelope } from "../api";
import type { ViewState } from "../types";

// One fetch per view (Q4 = A). No shared store, no data-fetching library, no client cache -- a
// cache would contradict ER-03's /api/* no-cache and let two views disagree about freshness (the
// US-05 failure). Re-fetches when `path` changes (the grouping tag-key selector is the only case).
export function useView<T>(path: string): ViewState<T> {
  const [state, setState] = useState<ViewState<T>>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    setState({ kind: "loading" });
    fetchEnvelope<T>(path).then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, [path]);

  return state;
}
