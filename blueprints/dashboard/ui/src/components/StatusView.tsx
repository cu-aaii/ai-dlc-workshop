import type { StatusPayload } from "../types";
import { ViewShell } from "./ViewShell";

// Provenance detail: the schema version and the skip breakdown. Freshness and the counts already
// ride the StatusStrip above every view; this view is where "why were things skipped" lives.
export function StatusView() {
  return (
    <ViewShell<StatusPayload> path="/status">
      {(payload) => {
        const reasons = Object.entries(payload.skipped_reasons);
        return (
          <div className="status-view">
            <p className="summary">
              Snapshot schema version <code>{payload.schema_version}</code>
            </p>
            <h2>Skip reasons</h2>
            {reasons.length === 0 ? (
              <p className="notice">Nothing was skipped in the last collection.</p>
            ) : (
              <table className="data-table" data-testid="status-skip-reasons">
                <caption>Why resources were skipped, by reason code</caption>
                <thead>
                  <tr>
                    <th scope="col">Reason</th>
                    <th scope="col">Count</th>
                  </tr>
                </thead>
                <tbody>
                  {reasons.map(([reason, count]) => (
                    <tr key={reason}>
                      <td>{reason}</td>
                      <td>{count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        );
      }}
    </ViewShell>
  );
}
