"""C-01 Collector: the hourly job that turns the Resource Groups Tagging API into a snapshot.

Above the U-01 boundary -- this package reads the environment, reads the clock, configures boto3,
logs, and emits metrics. It delegates every *decision* about the data (parsing, deduping, counting)
to `dashboard.core`, which can do none of those things. CR-03 and the import boundary are two views
of the same rule.
"""
