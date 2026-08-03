# Versioning, Releases, Backups & Recovery — Options for the Mob

Requested 2026-08-03. Recommendations marked ⭐. The framing case from the mob:

> If you build an MCP from a blueprint, all that code still lives somewhere. If you build a
> project knowledge base from a blueprint and lose it, that data is gone forever. Oops.

That case generalizes: **a deployment is code + infrastructure + state, and only the first
two are recoverable from git.** Everything below follows from making state explicit.

---

## 1 · Versioning

Blueprints already pin semver in `blueprint.yaml` (`version: 2.3.1`, D1: deployments
reference a `ref:`, never copy). The open question is where the version *lives*.

| Option | How | Trade-off |
|---|---|---|
| **A ⭐ Per-blueprint git tags in the blueprints repo** | Tag `course-chatbot/v2.3.1`; the manifest's `module.ref` points at the tag | One repo to govern, tags are cheap, matches the `git::cornell/blueprints//course-chatbot?ref=` module source already in the proposal. Con: repo-wide history is noisier |
| B Repo per blueprint | Each blueprint is its own repo with plain `vX.Y.Z` releases | Cleanest ownership boundary (P3 federated maintainers) — but repo sprawl now, and the catalog needs an index anyway |
| C Version registry file | `catalog.yml` maps name → versions → refs | Single source the MCP can read cheaply; but it duplicates git tags and drifts unless CI enforces agreement |

**Note**: A now, B is a natural P3 evolution when outside units author blueprints. Either
way the *deployment* repo records exactly one pinned version — upgrades are dependency-bump
PRs the platform can propose automatically (the whole point of D1).

## 2 · Releases & release notes

| Option | How | Trade-off |
|---|---|---|
| **A ⭐ GitHub Releases + git-cliff** | Conventional-commit messages; `git-cliff` generates notes per blueprint tag; GitHub Release created by CI on tag push | Zero-maintenance notes; upstream aidlc-workflows itself uses `cliff.toml`, so there's a working config to crib. Requires commit-message discipline |
| B Hand-written CHANGELOG.md per blueprint | Author writes notes in the release PR | Best prose for the `narrative` audience; humans stop doing it by the fifth release |
| C MCP-surfaced release notes | However notes are produced, add a `release_notes` field to the manifest / a tool that shows "what changed" when proposing an upgrade PR | Not an alternative — a consumer of A or B. Builders see "v2.3.1 → v2.4.0 fixes X" *inside the conversation*, which is where the upgrade decision happens |

**Recommendation**: A for production, C layered on top. The release note has two audiences —
the reviewer at the gate and the builder deciding whether to take an upgrade — and both
should get it without leaving their surface.

## 3 · Backups & recovery

### The organizing idea ⭐: the manifest declares state

Add a `state:` block to `blueprint.yaml`, and make the gate refuse blueprints that have
stateful resources without one:

```yaml
state:
  - resource: corpus_bucket        # logical name in the template
    class: authoritative           # stateless | derived | authoritative
    backup: aws-backup-daily       # named platform backup plan
    rpo: 24h
  - resource: kb_index
    class: derived                 # rebuildable from corpus_bucket
    rebuild: reingest              # recovery = re-run ingestion
```

Three state classes, three recovery stories:

| Class | Example | Recovery | Cost |
|---|---|---|---|
| `stateless` | Lambda, API, Teams bot frontend | Redeploy from repo (merge or `restart_deployment`) | Free — git is the backup |
| `derived` | KB index, embeddings, caches | **Re-ingest from the authoritative source** — the index is a cache, never the system of record | Re-ingestion time; no storage cost |
| `authoritative` | Document corpus, Aurora rows, uploaded files | Real backups (below) — this is the "gone forever" class | Storage + ops |

The mob's "oops" case is exactly a KB blueprint that made the *index* look authoritative.
Rule of thumb worth adopting as policy: **a blueprint may not make derived data the only
copy — every `derived` resource must name the `authoritative` source it rebuilds from.**

### Mechanisms for the `authoritative` class

| Option | How | Trade-off |
|---|---|---|
| **A ⭐ AWS Backup, tag-driven** | One platform backup plan selects resources by `cornell:deployment-id` tag — Aurora, S3, DynamoDB, EFS covered by one policy | The four mandatory tags literally pay for themselves; per-blueprint effort is zero. Con: restore is platform-side, coarse-grained per resource |
| B Per-blueprint backup resources | Each template ships its own snapshot/replication config | Tunable per blueprint; forty blueprints = forty backup implementations to review |
| C `DeletionPolicy: Retain`/`Snapshot` baseline | CloudFormation keeps or snapshots stateful resources on stack delete; add stack termination protection | Not a backup (no protection against data-level loss) but the cheapest insurance against the worst accident — **do this regardless**, today, in every blueprint template |
| D Logical export via `export_spec` | The FR7 `transfer`/`offboarding` audiences double as a portable logical backup (spec + data export instructions) | Human-speed; right for off-boarding, wrong for disaster recovery |

**Recommendation**: C immediately (template-level, one line per resource), A as the P1
platform mechanism, D for the faculty-departure story. B only when a blueprint's RPO
genuinely can't be met by the shared plan.

### Recovery drills

A backup nobody has restored is a hypothesis. P1 gate suggestion: before a blueprint
reaches `maturity: supported`, someone restores a deployment of it from backup in a
sandbox account, and the restore steps go in the blueprint's README.

---

## Decision asks for the mob

1. Versioning: per-blueprint tags in one repo (A) — yes/no?
2. Releases: conventional commits + git-cliff (A), notes surfaced in-conversation (C) — yes/no?
3. Adopt the `state:` manifest block and the three classes as part of the blueprint contract?
4. Adopt "derived data must name its authoritative source" as gate policy?
5. `DeletionPolicy: Retain` + termination protection on stateful resources starting with the
   course-chatbot blueprint — this week?
