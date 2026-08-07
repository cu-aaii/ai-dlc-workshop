import type { ViewName } from "../types";

// Real <button>s in a role="tablist" (keyboard operable, WCAG 2.2 AA). aria-selected marks the
// active tab; focus is never removed (the token focus ring is surface-aware, in styles.css).
interface Props {
  active: ViewName;
  onSelect: (view: ViewName) => void;
}

const TABS: { name: ViewName; label: string; testid: string }[] = [
  { name: "inventory", label: "Inventory", testid: "view-tabs-inventory" },
  { name: "grouping", label: "Grouping", testid: "view-tabs-grouping" },
  { name: "tag-gaps", label: "Tag gaps", testid: "view-tabs-tag-gaps" },
  { name: "status", label: "Status", testid: "view-tabs-status" },
  { name: "financial", label: "Financial", testid: "view-tabs-financial" },
  { name: "adoption", label: "Adoption", testid: "view-tabs-adoption" },
];

export function ViewTabs({ active, onSelect }: Props) {
  return (
    <div role="tablist" aria-label="Dashboard views" className="view-tabs">
      {TABS.map((t) => (
        <button
          key={t.name}
          role="tab"
          type="button"
          aria-selected={active === t.name}
          className={`view-tab${active === t.name ? " is-active" : ""}`}
          data-testid={t.testid}
          onClick={() => onSelect(t.name)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
