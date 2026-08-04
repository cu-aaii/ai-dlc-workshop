import { API_BASE } from "../api";
import type { ResourceRow } from "../types";
import { ViewShell } from "./ViewShell";

// Every resource in a native <table> (US-01/US-02), plus a copy-URL affordance that copies the API
// URL (Q6 = A -- there is no per-view deep link, so the API endpoint is what is shareable).
export function InventoryView() {
  return (
    <ViewShell<ResourceRow[]> path="/inventory">
      {(rows) => (
        <>
          <div className="view-toolbar">
            <button
              type="button"
              className="btn"
              data-testid="inventory-copy-url-button"
              onClick={() => {
                void navigator.clipboard?.writeText(`${location.origin}${API_BASE}/inventory`);
              }}
            >
              Copy API URL
            </button>
          </div>
          <table className="data-table" data-testid="inventory-table">
            <caption>Every resource carrying, or missing, the required tags</caption>
            <thead>
              <tr>
                <th scope="col">ARN</th>
                <th scope="col">Service</th>
                <th scope="col">Type</th>
                <th scope="col">Region</th>
                <th scope="col">Owner</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.arn}>
                  <td className="mono">{r.arn}</td>
                  <td>{r.service}</td>
                  <td>{r.resource_type}</td>
                  <td>{r.region}</td>
                  <td>{r.tags["cornell:owner"] ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </ViewShell>
  );
}
