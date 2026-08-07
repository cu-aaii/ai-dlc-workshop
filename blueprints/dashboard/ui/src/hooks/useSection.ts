import { useEffect, useState } from "react";

import { fetchSection } from "../api";
import type { SectionViewState } from "../types";

// Same one-fetch-per-view discipline as useView, over the section envelope.
export function useSection<T>(path: string): SectionViewState<T> {
  const [state, setState] = useState<SectionViewState<T>>({ kind: "loading" });

  useEffect(() => {
    let live = true;
    setState({ kind: "loading" });
    fetchSection<T>(path).then((next) => {
      if (live) setState(next);
    });
    return () => {
      live = false;
    };
  }, [path]);

  return state;
}
