import { SectionBoundary } from "./SectionBoundary";
import { useSection } from "../hooks/useSection";
import type { CounterState, RateRow, UsageModelsPayload, UsageQualityPayload } from "../types";

// US-20..US-23. The panel most of this component exists for is the EMPTY one: no blueprint emits
// usage counters yet, so approval rate, success rate and completed tasks all report their absence.
// Rendering those as 0% would claim an application is working perfectly when nothing is measured.
//
// The AWS-emitted half (requests, tokens, error counts) does have real data with no instrumentation,
// so this view routinely shows one populated panel beside an unpopulated one -- which is exactly why
// the three states have to stay visually distinct.

const STATE_TEXT: Record<CounterState, string> = {
  ok: "reported",
  no_data_yet: "no data in this window",
  not_instrumented: "not instrumented",
  cannot_read: "could not be read",
};

function NotInstrumentedNote({ blueprints }: { blueprints: string[] }) {
  if (blueprints.length === 0) return null;
  // FR-9.7.3: name them. A blank panel makes a reader wonder whether the dashboard is broken.
  return (
    <p className="notice" data-testid="not-instrumented-list">
      These blueprints report no usage counters yet:{" "}
      <strong>{blueprints.join(", ")}</strong>. Emitting them is a change in each blueprint, not in
      this dashboard.
    </p>
  );
}

function Rate({ label, row, testid }: { label: string; row: RateRow; testid: string }) {
  if (row.rate === null) {
    return (
      <div className="rate-card" data-testid={`${testid}-unavailable`}>
        <dt>{label}</dt>
        {/* Never "0%" -- the state says why there is no number. */}
        <dd className="muted">{STATE_TEXT[row.state]}</dd>
      </div>
    );
  }
  return (
    <div className="rate-card" data-testid={testid}>
      <dt>{label}</dt>
      <dd>
        <strong>{row.percent?.toFixed(1)}%</strong>
        {/* TEL-06: the counts travel with the rate, so it can be judged and re-aggregated. */}
        <span className="muted"> ({row.numerator} of {row.denominator})</span>
      </dd>
    </div>
  );
}

export function AdoptionView() {
  const models = useSection<UsageModelsPayload>("/usage/models");
  const quality = useSection<UsageQualityPayload>("/usage/quality");

  return (
    <section aria-label="Adoption">
      <h2>Model usage</h2>
      <SectionBoundary state={models} label="usage">
        {(data) => (
          <>
            <NotInstrumentedNote blueprints={data.not_instrumented} />
            {data.models.length === 0 ? (
              <p className="notice" data-testid="no-model-usage">
                No model invocations recorded in this window.
              </p>
            ) : (
              <table className="data-table" data-testid="model-usage">
                <caption>
                  Requests and tokens from AWS-emitted metrics — available without instrumenting any
                  blueprint. Traffic routed through an external gateway does not appear here.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Model</th>
                    <th scope="col">Requests</th>
                    <th scope="col">Input tokens</th>
                    <th scope="col">Output tokens</th>
                    <th scope="col">Estimated cost</th>
                  </tr>
                </thead>
                <tbody>
                  {data.models.map((row) => (
                    <tr key={row.model}>
                      <td>{row.model}</td>
                      <td>{row.requests}</td>
                      <td>{row.input_tokens.toLocaleString()}</td>
                      <td>{row.output_tokens.toLocaleString()}</td>
                      <td>
                        {row.rate_missing ? (
                          // COST-09: no rate configured is NOT $0.00.
                          <span className="muted" data-testid="rate-missing">no rate configured</span>
                        ) : (
                          <span>~${Number(row.estimated_cost).toFixed(4)}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {/* NFR-T1: the estimate is never shown as, or added to, billed cost. */}
            <p className="notice notice-estimate" data-testid="estimate-caveat">
              <strong>Estimated</strong>, not billed: model cost is derived from token counts times a
              configured rate table, and is not comparable to the billed figures on the Financial tab.
              {data.rates_state === "not_configured" && " No rate table is configured, so no estimate is shown."}
              {data.rates_state === "malformed" && " The configured rate table could not be parsed."}
            </p>
          </>
        )}
      </SectionBoundary>

      <h2>Quality and reliability</h2>
      <SectionBoundary state={quality} label="quality metrics">
        {(data) => (
          <dl className="rate-row" data-testid="quality-rates">
            <Rate label="Error rate" row={data.error_rate} testid="rate-error" />
            <Rate label="Timeout rate" row={data.timeout_rate} testid="rate-timeout" />
            <Rate label="Human approval rate" row={data.approval_rate} testid="rate-approval" />
            <Rate label="Prompt success rate" row={data.success_rate} testid="rate-success" />
          </dl>
        )}
      </SectionBoundary>
    </section>
  );
}
