import type { TagGapPayload } from "../types";
import { ViewShell } from "./ViewShell";

// Which resources lack which required tags (US-04). The actionable companion to the grouping view's
// pinned-last missing group. `missing_tags` names the specific tags, not just "incomplete".
export function TagGapView() {
  return (
    <ViewShell<TagGapPayload> path="/tag-gaps">
      {(payload) => (
        <>
          <p className="summary">
            {payload.complete_count} fully tagged · {payload.incomplete.length} with gaps
          </p>
          <table className="data-table" data-testid="tag-gap-table">
            <caption>Resources missing one or more required <code>cornell:*</code> tags</caption>
            <thead>
              <tr>
                <th scope="col">ARN</th>
                <th scope="col">Service</th>
                <th scope="col">Region</th>
                <th scope="col">Missing tags</th>
              </tr>
            </thead>
            <tbody>
              {payload.incomplete.map((r) => (
                <tr key={r.arn}>
                  <td className="mono">{r.arn}</td>
                  <td>{r.service}</td>
                  <td>{r.region}</td>
                  <td data-testid="tag-gap-missing-tags">{r.missing_tags.join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </ViewShell>
  );
}
