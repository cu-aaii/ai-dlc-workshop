# 0001 — `course-chatbot` ships with its Lambda base image on a mutable tag, as a dated exception to SECURITY-10

**Status**: accepted
**Date**: 2026-08-04
**Deciders**: Fermin Romero (Track C). Raised by the Security Baseline verification at the Units
Generation gate, not found in review.

## Context

`blueprints/course-chatbot/Dockerfile` builds on `public.ecr.aws/lambda/python:3.13`. That is a
**mutable tag**: AWS moves it as patches land, so two builds of the same commit can produce different
images.

SECURITY-10 requires that "Dockerfiles and CI configs do not use `latest` or unpinned image tags for
production", and the Security Baseline extension makes every unmet rule a **blocking** finding — the
Units Generation stage may not offer Continue while one stands. This one stood.

The repository had already predicted it. `blueprints/tiny-chatbot/Dockerfile` says: *"pin this base
image by digest (SECURITY-10, like builder-mcp's Dockerfile) in the PR that wires the Build action."*
The PR that wires Track C's Build action is the one carrying this exception, and the pin was omitted.

Two things constrained the choice. The digest **could not be resolved from the authoring machine** —
two attempts against the public ECR registry API returned no `Docker-Content-Digest` — and a
fabricated digest fails the build rather than degrading quietly. And the leadership demo is at 14:00
on the day this was written.

## Decision

**Ship on the mutable tag for the 2026-08-04 demo, with the gap recorded rather than closed.**

The exception covers exactly one line in one file, expires on the date below, and does not extend to
any other blueprint or to any other SECURITY-10 criterion.

## Alternatives

- **Pin a digest obtained by guess or by pattern-matching another image.** Rejected: an incorrect
  digest fails the build, and a *plausible* one that happened to resolve would be worse — a compliance
  row closed with an unverified value is a false record, which is the specific failure this directory
  exists to prevent.
- **Block CONSTRUCTION until someone with registry access pins it.** Rejected on time, explicitly and
  by the decider rather than by drift. This was the framework's default behaviour and it was overridden
  on purpose.
- **Drop the container and inline the handler**, sidestepping base images entirely. Rejected on
  measurement: the inline handler came to **4114 characters against CloudFormation's 4096-character
  `ZipFile` cap**, and getting under it meant removing RS256 signature verification — trading a
  reproducibility gap for an authentication gap, which is a worse trade.
- **Pin to a patch tag** such as `:3.13.1`. Rejected as false comfort: still mutable, while *looking*
  pinned. A digest or nothing.

## Consequences

**What this makes easy**: the demo ships today.

**What it commits us to**: an unreproducible build input. The exposure is narrower than it first
appears and the boundary is worth being precise about —

- **The deployed artifact IS pinned.** The Build stage exports `CONTAINER_DIGEST` and the deploy passes
  it by digest (FR-28), so what is *running* is always identifiable and immutable. SECURITY-13 is
  unaffected.
- **Dependencies ARE pinned.** `src/requirements.lock` fixes all 20 transitive packages at exact
  versions.
- **The floating input is the base image layer alone**, so the real risk is "two builds of this commit
  may differ", not "we cannot tell what is deployed". For a *blueprint* — a thing meant to be
  instantiated repeatedly by other people — that is still a genuine defect, because reproducibility is
  most of what makes a governed building block trustworthy.

**The demo-day risk specifically**: if AWS moves the tag between a rehearsal build and the demo build,
the demonstrated image is not the rehearsed one. Low probability over a few hours; not zero, and worth
knowing before blaming something else.

**What would make us revisit — any one of these, whichever comes first:**

1. **2026-08-05.** The exception expires the day after the demo. It is dated, not open-ended.
2. Anyone with registry access running `docker manifest inspect public.ecr.aws/lambda/python:3.13`,
   which reduces this to a one-line edit.
3. This blueprint being offered to a builder outside the workshop, at which point "reproducible for
   whoever instantiates it" stops being optional.
4. Any second blueprint copying the pattern. One dated exception is a decision; two is a convention
   nobody chose.

**Note on numbering**: this is `0001` because it is the first decision written, not the most
consequential. `docs/decisions/README.md` nominates Track D's inter-block protocol decision as the one
that matters most, and it is still outstanding.
