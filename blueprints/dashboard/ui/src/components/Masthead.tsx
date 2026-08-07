import logo from "../assets/cornell-reduced-white.svg";

// The Cornell mark (brand gate, non-waivable). The official white-fill reduced logo asset, placed
// on a carnelian band (#B31B1B) -- white on carnelian is 6.80:1, compliant. Fixed 45px tall (the
// "reduced logo -- exactly 45px" band) at every breakpoint, so fluid CSS cannot shrink it out of
// band. The asset is used verbatim; the mark is never redrawn, recolored beyond the three allowed
// fills, or reconstructed. Exactly one mark per view.
//
// NO DIVIDER between the mark and the title, deliberately -- see contracts/ui-design-language.md
// §3.1. This dashboard is not a college or school, so it gets no lockup, and a hairline plus a name
// set beside the mark *is* the lockup configuration the rule forbids ("Hairline and seal logo are
// equal height" is how the real academic lockup is built). A hairline was present here until
// 2026-08-07 and was removed when that rule was added. Plain text beside the mark is explicitly
// allowed -- "It may sit beside the seal logo with equal prominence -- that is not a lockup" -- so
// the title stays; only the rule-defining hairline goes. Clear space to the text stays >= 1/4 the
// seal diameter (~11px at 45px) via the logo's own padding plus the flex gap.
export function Masthead() {
  return (
    <header className="masthead">
      <div className="masthead-inner">
        <img className="masthead-logo" src={logo} alt="Cornell University" />
        <span className="masthead-title">Cost &amp; Usage Dashboard</span>
      </div>
    </header>
  );
}
