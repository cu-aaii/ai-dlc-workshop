import { useState } from "react";

import { REQUIRED_TAGS, type GroupingPayload, type RequiredTag } from "../types";
import { ViewShell } from "./ViewShell";

// Grouping by a required tag (US-03). Identity is carried by TEXT and a proportional bar in ONE
// accent (blue #006699, 6.25:1 on white) -- never by categorical colour (Q5 = A): a shared account
// yields more groups than any accessible palette has hues. Group order is the server's (count desc,
// value asc, missing pinned last); the UI must not re-sort. The missing group gets a distinct label,
// not a blank cell, and is the row TagGapView acts on.
export function GroupingView() {
  const [tagKey, setTagKey] = useState<RequiredTag>(REQUIRED_TAGS[0]);

  return (
    <>
      <div className="view-toolbar">
        <label htmlFor="grouping-tag-key" className="field-label">
          Group by
        </label>
        <select
          id="grouping-tag-key"
          className="select"
          data-testid="grouping-tag-key-select"
          value={tagKey}
          onChange={(e) => setTagKey(e.target.value as RequiredTag)}
        >
          {REQUIRED_TAGS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      <ViewShell<GroupingPayload> path={`/groups/${tagKey}`}>
        {(payload) => {
          const max = payload.groups.reduce((m, g) => Math.max(m, g.count), 0) || 1;
          return (
            <table className="data-table" data-testid="grouping-table">
              <caption>
                Resources grouped by <code>{payload.tag_key}</code> ({payload.total} total)
              </caption>
              <thead>
                <tr>
                  <th scope="col">Value</th>
                  <th scope="col">Count</th>
                  <th scope="col">Share</th>
                </tr>
              </thead>
              <tbody>
                {payload.groups.map((g) => {
                  const missing = g.value === null;
                  return (
                    <tr
                      key={g.value ?? "__missing__"}
                      data-testid={missing ? "grouping-missing-group-row" : undefined}
                    >
                      <td>{missing ? `(no ${payload.tag_key} tag)` : g.value}</td>
                      <td>{g.count}</td>
                      <td>
                        {/* Proportional bar: width encodes the count; the number beside it is the
                            non-colour carrier. aria-hidden so the count (already in the prior cell)
                            is not announced twice. Width comes from a bucket CLASS, never an inline
                            style attribute -- the strict CSP (style-src 'self', no unsafe-inline)
                            forbids inline styles, so the widths live in styles.css. */}
                        <span
                          className={`bar bar-w-${Math.round((g.count / max) * 20) * 5}`}
                          aria-hidden="true"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          );
        }}
      </ViewShell>
    </>
  );
}
