# Integration Test Instructions

**Date**: 2026-08-04. Applicable from U-02.

## What "integration" means here, honestly

U-02's seams are: collector → Tagging API → `dashboard.core` → S3, and browser → CloudFront → API
Gateway → api Lambda → S3. **None can be stood up locally without AWS**, and mocking the whole chain
would test the mocks. So integration is split into what a non-deployed test *can* prove and what only
a deploy can.

### Runnable now — seam behaviour with stubbed AWS boundaries

These exercise the real code across the U-02↔U-01 boundary and the S3/Tagging seams, with only the AWS
edge stubbed (botocore-style fakes, not full mocks of our logic):

| Seam | Test | What it proves |
|---|---|---|
| collector → core → (S3 put) | `test_collector_logging.py` (end-to-end `run()` with fake Tagging + fake S3) | a real snapshot is built from Tagging items and written once; the tag value is in the object but never in a log |
| collector pagination → core | `test_collector_pagination.py` | multi-page accumulation feeds `normalize_all`; breach raises |
| S3 → core → api envelope | `test_api_states.py`, `test_api_loading.py` | a stored snapshot's bytes round-trip through `deserialize_snapshot` into the six-state response |

Run: `cd blueprints/dashboard && uv run pytest -q`.

### Deployed-only — the real transport chain

CloudFront → WAF → API Gateway → Lambda → S3, and the EventBridge → collector → S3 path, have **no
local substitute** (no transport to stand up; the U-01↔U-02 seam is an in-process import). These are
verified by the first `Environment=test` (or `main`) deploy, reading:

- `aws bedrock-agent`-style status is N/A here; instead check the collector's CloudWatch logs for a
  successful run and the snapshot object's presence/age;
- open the CloudFront domain from an allowlisted IP and confirm each view renders and `/api/*` returns
  the envelope.

These map to the four `deployed`-only requirements (SEC-7, A-4, P-6, R-8) and are the reason U-02
cannot reach U-01's fully-executed bar without a merge.
