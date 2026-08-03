# Application Design Plan — Clarification Round 2

**Stage**: INCEPTION → Application Design, Step 9 (mandatory follow-up)
**Date**: 2026-08-03
**Trigger**: Step 8 answer analysis of `application-design-plan.md`

---

## What the analysis found

Q1, Q2, Q3, Q4, Q5, Q6 and Q8 are clean single selections with no vagueness, contradiction, or
option-merging. They are consistent with each other and with the requirements, and they are recorded
as resolved.

**Q7 = B** ("a framework with a build step") needs three things settled before design can proceed.
Two are genuine gaps in the answer; the third is a gap in my questions, not yours.

Nothing here reopens Q7. You chose a framework build, and that choice stands.

---

## Question 9 — Which framework, and which bundler?

Q7's option B named "React/Vue/Svelte + bundler" as examples rather than a choice, so the answer
doesn't yet name one. This isn't a formality — the pick determines the Dockerfile or build image,
what goes in the lockfile, how much of the supply-chain surface in Question 11 exists, and whether
the CSP in US-01 can stay strict.

A) **Svelte + Vite** — compiles to plain JS with no runtime framework shipped to the browser, so the
   delivered bundle is closest to the vanilla option's security posture while you still get a
   component model and a build. Smallest dependency tree of the three.

B) **React + Vite** — the most widely known, so most likely to be legible to whoever picks this up
   after the workshop. Ships a runtime to the browser; largest dependency tree of the three.

C) **Vue + Vite** — middle ground on both counts.

D) **You choose** — I pick, optimizing for the smallest dependency tree and the strictest CSP that
   still gives a component model, and record the reasoning. (That would land on A.)

X) Other — name the framework and bundler you want

[Answer]:

## Question 10 — How do the built site files reach S3?

**This gap is mine, not a defect in your answer.** Questions 1–8 asked what stores the snapshot but
never asked how the site's own files get into the bucket — and CloudFormation cannot upload S3
objects, so *something* has to. This would have needed answering even under Q7 = A; the build step
just makes it more visible.

It also matters because two of the three options edit `pipeline.yml`, which `CLAUDE.md` protects.

A) **A new Build stage action in the pipeline** — CodeBuild installs dependencies, runs the
   framework build, and `aws s3 sync`s the output to the site bucket. *Note*: this is very likely
   the **same pipeline edit** as the container-build action the execution plan already identified as
   missing, so it is one change to `pipeline.yml` rather than two. Consistent with the "everything
   deploys through the pipeline" constraint. *Cost*: the pipeline gains a stage it has never run,
   and the site bucket name has to reach CodeBuild.

B) **Commit the built output to the repo**, and have CodeBuild only sync it. *Cost*: build artifacts
   in version control — the reviewable diff for a UI change becomes bundler output, and the repo now
   has two sources of truth for the same UI. Also means a PR reviewer cannot tell whether the
   committed bundle actually corresponds to the committed source.

C) **A CloudFormation custom resource** (Lambda-backed) that writes the files during stack
   deployment. Keeps everything inside the template. *Cost*: the site content would have to be
   embedded in or fetched by the Lambda, custom resources fail in ways that are hard to debug, and
   it puts application content into the infrastructure lifecycle.

X) Other (describe after [Answer]: tag below)

[Answer]:

## Question 11 — Does SECURITY-10 extend to the npm dependency tree?

US-09 [Enabler] currently reads as Python-and-container-image scoped: pinned dependencies verified
against recorded hashes, base image pinned by digest, vulnerability scan, SBOM. Q7 = B adds a second
dependency ecosystem that US-09 does not mention, so its scope needs deciding rather than assuming.

The substantive distinction: npm packages are **build-time** dependencies here. They do not ship in
the Lambda container images, and only their compiled output reaches the browser. So a scan of the
runtime image would not see them at all.

A) **Yes, fully** — `package-lock.json` committed with integrity hashes, npm audit or equivalent in
   the build, and the SBOM covers both ecosystems. Strictest reading; treats a compromised build
   dependency as what it is, since it can inject anything into the delivered bundle.

B) **Lockfile and pinning yes, scanning and SBOM no** — pin exactly so builds are reproducible, but
   don't extend vulnerability scanning or the SBOM to build-time-only dependencies.

C) **No — out of scope**, treated as build tooling like `uv` and `cfn-lint` are today. *Cost*: this
   would be a new accepted exception to SECURITY-10 and would need recording in `requirements.md`
   §4.6 alongside the other four, rather than passing unremarked.

X) Other (describe after [Answer]: tag below)

[Answer]:

---

## Consequences of Q7 = B recorded now, not asked

These follow from your answer and need no decision from you. Recorded so they are visible rather
than discovered during Construction.

1. **The repo gains a second toolchain.** `tools/check` currently needs only `uv`, and CI runs that
   same script. A UI build introduces Node. `tools/check` will need to stay meaningful without
   requiring Node for people who only touch templates — so the site build belongs in the pipeline,
   not in `tools/check`, unless you say otherwise.
2. **GitHub Actions can still do this if needed.** The org policy permits github-owned actions, and
   `actions/setup-node` is github-owned, so it is not blocked. Noting this because the policy
   *sounds* like it would prohibit it.
3. **US-01's CSP needs care.** A production framework build can satisfy a strict CSP, but bundlers
   often emit inline scripts by default. The design will state that no `unsafe-inline` or
   `unsafe-eval` is permitted and that the build must be configured accordingly, rather than
   loosening the header to match the tooling.
4. **The UI build is a second thing that must land in the same `pipeline.yml` edit** as the
   container build. The execution plan already flagged the coordination point; this reinforces it.
