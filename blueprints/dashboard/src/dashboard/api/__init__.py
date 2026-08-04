"""C-03 Read API: turn one stored snapshot into the four read-only views (AR-01..AR-08).

Above the U-01 boundary (reads S3, reads the clock, logs), but every *derivation* -- grouping,
tag-gap classification, freshness -- is delegated to `dashboard.core`. The API chooses which
derivation a route needs and passes the snapshot; it never iterates records itself (AR-04, CR-03).

Two totality decisions, both structural (NFR Design §6, `business-logic-model.md`):
`load_current_snapshot` classifies rather than raises, and `handler` wraps everything after the
closed route table in one error boundary that maps any escape to a generic 503.
"""
