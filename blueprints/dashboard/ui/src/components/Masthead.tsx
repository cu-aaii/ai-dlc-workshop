import logo from "../assets/cornell-reduced-white.svg";

// The Cornell mark (brand gate, non-waivable). The official white-fill reduced logo asset, placed
// on a carnelian band (#B31B1B) -- white on carnelian is 6.80:1, compliant. Fixed 45px tall (the
// "reduced logo -- exactly 45px" band) at every breakpoint, so fluid CSS cannot shrink it out of
// band. The asset is used verbatim; the mark is never redrawn, recolored beyond the three allowed
// fills, or reconstructed. Exactly one mark per page. The "Cost & Usage Dashboard" text below is a
// typographic heading, NOT a logo, and does not consume the one-mark allowance.
export function Masthead() {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <img className="masthead-logo" src={logo} alt="Cornell University" />
        <span className="masthead-divider" aria-hidden="true" />
        <span className="masthead-title">Cost &amp; Usage Dashboard</span>
      </div>
    </header>
  );
}
