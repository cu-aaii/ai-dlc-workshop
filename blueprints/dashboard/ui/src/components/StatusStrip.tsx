import type { Envelope, Freshness } from "../types";
import { formatTimestamp } from "../format";

// collected_at, freshness (icon + word, never colour alone), and the three provenance counts. Reads
// the active view's envelope; it does NOT fetch (a fifth request could return a different snapshot
// than the view beneath it -- the US-05 failure in miniature).
interface Props {
  envelope: Envelope<unknown>;
}

const FRESHNESS: Record<Exclude<Freshness, null>, { word: string; glyph: string; cls: string }> = {
  fresh: { word: "Fresh", glyph: "✓", cls: "fresh" },
  stale: { word: "Stale", glyph: "⚠", cls: "stale" },
  invalid: { word: "Invalid", glyph: "✕", cls: "error" },
};

export function StatusStrip({ envelope }: Props) {
  const f = envelope.freshness ? FRESHNESS[envelope.freshness] : null;
  const c = envelope.counts;
  return (
    <dl className="status-strip">
      <div className="status-item">
        <dt>Collected</dt>
        <dd data-testid="status-strip-collected-at">{formatTimestamp(envelope.collected_at)}</dd>
      </div>
      <div className="status-item">
        <dt>Freshness</dt>
        <dd data-testid="status-strip-freshness">
          {f ? (
            <span className={`freshness freshness-${f.cls}`}>
              <span aria-hidden="true" className="status-glyph">{f.glyph}</span> {f.word}
            </span>
          ) : (
            "—"
          )}
        </dd>
      </div>
      <div className="status-item">
        <dt>Resources</dt>
        <dd>{c.resources}</dd>
      </div>
      <div className="status-item">
        <dt>Skipped</dt>
        <dd data-testid="status-strip-skipped-count">{c.skipped}</dd>
      </div>
      <div className="status-item">
        <dt>Duplicates removed</dt>
        <dd>{c.duplicates_removed}</dd>
      </div>
    </dl>
  );
}
