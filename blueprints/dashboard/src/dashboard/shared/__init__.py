"""Runtime helpers shared by the collector and the read API (U-02).

Everything here is above the U-01 boundary: it may read the environment, read the clock, log, and
emit metrics -- the four things `src/dashboard/core/` is forbidden. Nothing here imports boto3
either, though: logging and metrics are stdlib + stdout only (NFR Design §4, §5), so this package
stays testable without an AWS client.
"""
