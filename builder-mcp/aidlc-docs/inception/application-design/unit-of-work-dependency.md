# Unit Dependency Matrix — builder-mcp

Verified by import analysis (every import in the package, not eyeballed), 2026-08-04:

```
config.py       (stdlib only)          shared kernel
validation.py   (stdlib only)          shared kernel
patching.py     (stdlib only)          U2
spec_export.py  (stdlib only)          U4
catalog.py      → config               U1
github_ops.py   → config               U2
aws_ops.py      → config, validation   U3
server.py       → all of the above     U5
```

| Depends on → | U1 | U2 | U3 | U4 | U5 | kernel |
|---|---|---|---|---|---|---|
| **U1 Catalog** | — | ✗ | ✗ | ✗ | ✗ | ✓ |
| **U2 Lifecycle** | — | — | ✗ | ✗ | ✗ | ✓ |
| **U3 Operations** | — | — | — | ✗ | ✗ | ✓ |
| **U4 Spec** | — | — | — | — | ✗ | ✗ (stdlib) |
| **U5 Shell** | ✓ | ✓ | ✓ | ✓ | — | ✓ |

Reading: no unit imports another unit; U5 composes all of them; the kernel is imported by
everyone and owned by no one (change by agreement, SPEC C8).

Consequences:
- U1–U4 can be worked **fully in parallel** with no coordination beyond the kernel rule.
- Every cross-unit interaction is visible in exactly one place (`server.py` → `tools/*`
  after UOW-0), which is also where contract C3 is enforced.
- A kernel change is the only edit that fans out — hence the by-agreement rule.
