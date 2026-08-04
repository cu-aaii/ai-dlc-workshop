# Requirements/Story Text Alignment with Q11 = B

**Stage**: INCEPTION → Application Design, arising from Step 8 analysis of Q9–Q11
**Date**: 2026-08-03
**Blocking**: **No.** The Application Design artifacts are complete and internally consistent under
Q11 = B either way. What is at stake is whether two *approved* artifacts still say what the design
does. Answer this whenever convenient — including after approving the design.

---

## Why this is being asked at all

Question 11's own text said that option **C** "would be a new accepted exception to SECURITY-10 and
would need recording in `requirements.md` §4.6 alongside the other four." You chose **B**, which is
narrower than C but still declines two of SECURITY-10's four provisions — vulnerability scanning and
SBOM coverage — for one of the blueprint's two dependency ecosystems.

I am not re-asking Q11. The decision stands. The question is only whether the approved requirement and
story texts get amended to match it, because as written they claim more than the design will deliver,
and an implementer reading only the story would build npm scanning you said not to build.

Both artifacts are approved, so amending either is your call and not mine.

---

## Question 12 — Does `requirements.md` §4.6 gain a fifth entry?

§4.6 currently documents **four** accepted exceptions. Part A2 already records that Q3 = A *kept* it at
four rather than adding a fifth.

A) **Yes — record it as a fifth accepted exception.** SECURITY-10 asks for pinning, scanning, and an
   SBOM; npm gets pinning only. Recording it keeps §4.6 an honest complete list of every place the
   blueprint knowingly falls short of a baseline rule, which is the property that makes §4.6 worth
   having.

B) **No — record it as a scope clarification of SECURITY-10 instead**, not an exception. The
   reasoning: SECURITY-10's scan and SBOM targets are the *produced artifacts*, and npm packages are
   build-time only — they are not in the Lambda container images, so an image scan structurally cannot
   see them. On that reading nothing is being excepted; the rule's scope simply never included them.
   *Cost*: a reader comparing SECURITY-10 to the implementation has to find the clarification to
   understand why there is no npm scan.

C) **You choose** — I pick and record the reasoning. (That would land on A: B's argument is sound for
   the SBOM and the image scan, but it does not cover the residual risk in
   `application-design.md` §6.2 — a compromised build-time dependency can inject arbitrary code into
   the delivered bundle, so *something* real is going unscanned. §4.6 exists to list exactly that
   class of thing.)

X) Other (describe after [Answer]: tag below)

[Answer]:

## Question 13 — Does US-09's fourth acceptance criterion get narrowed?

It currently reads, unqualified:

> **Given** a dependency with a known vulnerability above the agreed threshold, **when** the build
> runs, **then** the failure is surfaced rather than passing silently

Under Q11 = B this is true of Python dependencies and container base images, and not true of npm.

A) **Yes — narrow the wording** to name the ecosystems it applies to, and add a criterion covering
   what npm *does* get (committed lockfile, integrity hashes, exact pinning). This edits an approved
   story, so it needs your say-so.

B) **No — leave US-09 as written** and let `application-design.md` §6.3 carry the qualification.
   *Cost*: the story and the design disagree, and the story is the artifact Code Generation reads
   most closely.

C) **You choose** — I pick and record the reasoning. (That would land on A. A story whose acceptance
   criterion cannot be satisfied is worse than one that is narrower than you might like, and the
   npm-side criterion is a real acceptance test — the lockfile is either committed with integrity
   hashes or it is not.)

X) Other (describe after [Answer]: tag below)

[Answer]:
