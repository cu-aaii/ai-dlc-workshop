import { useState } from "react";

import { Masthead } from "./components/Masthead";
import { ViewTabs } from "./components/ViewTabs";
import { InventoryView } from "./components/InventoryView";
import { GroupingView } from "./components/GroupingView";
import { TagGapView } from "./components/TagGapView";
import { StatusView } from "./components/StatusView";
import { FinancialView } from "./components/FinancialView";
import { AdoptionView } from "./components/AdoptionView";
import type { ViewName } from "./types";

// One URL for the whole app (Q4 = A): view is local state, no router. Switching a tab remounts the
// active view, which re-fetches (one fetch per view). No global store -- four read-only views share
// no mutable state.
export function App() {
  const [view, setView] = useState<ViewName>("inventory");

  return (
    <>
      <Masthead />
      <main className="container">
        <h1>AWS resource tag inventory</h1>
        <ViewTabs active={view} onSelect={setView} />
        {view === "inventory" && <InventoryView />}
        {view === "grouping" && <GroupingView />}
        {view === "tag-gaps" && <TagGapView />}
        {view === "status" && <StatusView />}
        {view === "financial" && <FinancialView />}
        {view === "adoption" && <AdoptionView />}
      </main>
    </>
  );
}
