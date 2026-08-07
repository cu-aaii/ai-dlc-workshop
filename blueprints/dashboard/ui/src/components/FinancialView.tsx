import { SectionBoundary } from "./SectionBoundary";
import { useSection } from "../hooks/useSection";
import type { AttributionPayload, CostBreakdownPayload, CostSummaryPayload, PerTask } from "../types";

// US-16..US-19. Two fetches, because summary and breakdown are separate routes and either can be
// absent independently.
//
// Three rules this component exists to honour, all of them about not lying with a number:
//  * "today" is labelled with what it COVERS, not with today's date (COST-04) -- Cost Explorer lags.
//  * unattributed spend is a named row, never a group called `cornell:blueprint$` (FR-10.3.6).
//  * "no tasks completed" is not "$0.00 per task" (COST-12).

function Money({ amount, currency }: { amount: string | undefined; currency: string }) {
  if (amount === undefined) return <span className="muted">—</span>;
  return (
    <span>
      {currency === "USD" ? "$" : ""}
      {Number(amount).toFixed(2)}
    </span>
  );
}

function PerTaskFigure({ perTask }: { perTask: PerTask | undefined }) {
  if (!perTask || perTask.state !== "ok") {
    return (
      <p className="notice" data-testid="per-task-unavailable">
        Cost per completed task is unavailable — it needs both cost and usage data.
      </p>
    );
  }
  if (perTask.outcome === "no_tasks") {
    // NOT "$0.00". No application reports completed tasks yet, and a zero would read as "free".
    return (
      <p className="notice" data-testid="per-task-no-tasks">
        No completed tasks reported, so there is no cost-per-task figure. No blueprint emits a{" "}
        <code>completed_tasks</code> counter yet.
      </p>
    );
  }
  return (
    <p data-testid="per-task-amount">
      <strong>${Number(perTask.amount).toFixed(4)}</strong> per completed task
      {perTask.completed_tasks !== undefined && (
        <span className="muted"> ({perTask.completed_tasks} tasks, month to date)</span>
      )}
    </p>
  );
}

function Attribution({ title, payload, testid }: { title: string; payload: AttributionPayload; testid: string }) {
  if (payload.fully_unattributed) {
    // The measured default: `cornell:*` are not activated as cost allocation tags, and only the
    // Organization payer can activate them. Saying so is the honest answer; a one-row breakdown
    // holding the account total would be a confident lie.
    return (
      <div className="notice" data-testid={`${testid}-unavailable`}>
        <h3>{title}</h3>
        <p>
          Attribution unavailable — all <Money amount={payload.unattributed} currency="USD" /> of
          spend is untagged for cost allocation. Activating <code>cornell:*</code> as cost allocation
          tags is a billing-account action and cannot be done from this account.
        </p>
      </div>
    );
  }
  return (
    <div data-testid={testid}>
      <h3>{title}</h3>
      <table className="data-table">
        <tbody>
          {payload.attributed.map((row) => (
            <tr key={row.key}>
              <td>{row.key.split("$")[1] || row.key}</td>
              <td><Money amount={row.amount} currency="USD" /></td>
            </tr>
          ))}
          {payload.unattributed !== "0" && (
            <tr data-testid={`${testid}-unattributed-row`}>
              <td><em>Unattributed</em></td>
              <td><Money amount={payload.unattributed} currency="USD" /></td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export function FinancialView() {
  const summary = useSection<CostSummaryPayload & { per_task?: PerTask }>("/cost/summary");
  const breakdown = useSection<CostBreakdownPayload>("/cost/breakdown");

  return (
    <section aria-label="Financial">
      <h2>Platform cost</h2>
      <SectionBoundary state={summary} label="cost">
        {(data, envelope) => {
          const perTask = (envelope as unknown as { per_task?: PerTask }).per_task;
          return (
            <>
              <dl className="stat-row" data-testid="cost-totals">
                <div>
                  <dt>Latest finalized day</dt>
                  <dd><Money amount={data.totals.day} currency={data.currency} /></dd>
                  {/* COST-04: what the figure covers, not when we asked. */}
                  <dd className="muted" data-testid="cost-covered-through">
                    covering {data.covered_through ?? "an unknown period"}
                  </dd>
                </div>
                <div>
                  <dt>Month to date</dt>
                  <dd><Money amount={data.totals.month_to_date} currency={data.currency} /></dd>
                </div>
                <div>
                  <dt>Year to date</dt>
                  <dd><Money amount={data.totals.year_to_date} currency={data.currency} /></dd>
                </div>
              </dl>
              <p className="muted" data-testid="cost-lag-note">
                Billed infrastructure cost, from Cost Explorer. Figures lag 24–48 hours, so the most
                recent day shown is the last one the billing data has finalized.
              </p>
              <h3>Cost per completed task</h3>
              <PerTaskFigure perTask={perTask} />
              {data.ce_calls !== null && (
                <p className="muted" data-testid="cost-self-cost">
                  This dashboard made {data.ce_calls} Cost Explorer requests on its last run
                  (about ${(data.ce_calls * 0.01).toFixed(2)}).
                </p>
              )}
            </>
          );
        }}
      </SectionBoundary>

      <h2>Where the money goes</h2>
      <SectionBoundary state={breakdown} label="cost breakdown">
        {(data) => (
          <>
            <Attribution title="By application" payload={data.by_blueprint} testid="by-blueprint" />
            <Attribution title="By deployment" payload={data.by_deployment} testid="by-deployment" />
            <h3>By service</h3>
            <table className="data-table" data-testid="by-service">
              <thead>
                <tr><th scope="col">Service</th><th scope="col">Month to date</th></tr>
              </thead>
              <tbody>
                {data.by_service
                  .slice()
                  .sort((a, b) => Number(b.amount) - Number(a.amount))
                  .map((row) => (
                    <tr key={row.key}>
                      <td>{row.key}</td>
                      <td><Money amount={row.amount} currency="USD" /></td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </>
        )}
      </SectionBoundary>
    </section>
  );
}
