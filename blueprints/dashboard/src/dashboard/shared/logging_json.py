"""Structured JSON logging on the stdlib logger (NFR Design §4; SEC-4, OR-06, CR-04, D-5).

The house pattern, taken verbatim in shape from `blueprints/course-chatbot/src/handler.py` and
`packages/builder-mcp`: `logging.getLogger()` with the level from `os.environ["LOG_LEVEL"]` and a
formatter that emits one JSON object per record. `aws-lambda-powertools` was rejected at NFR Design
Q3 -- a new runtime dependency with zero repo precedent, against Q11 = B's supply-chain posture.

**CR-04's privacy rule is enforced by what callers pass, not by a filter here.** A log record
carries a reason code and an ARN and nothing else; a `cornell:owner` value is a NetID and a log
group has readers, so a tag value must never reach `extra`. The formatter below does not scrub --
it faithfully serializes whatever it is given, which is exactly why the discipline lives at the
call site and is asserted by `test_collector_logging.py`.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any

# Standard LogRecord attributes, so the formatter can tell caller-supplied `extra` fields apart
# from the machinery and promote only the former into the JSON object.
_RESERVED = frozenset(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Render a `LogRecord` as a single-line JSON object.

    Fields: `level`, `logger`, `message`, plus every key passed via `extra=`. On an exception, a
    short `error` string (the exception's class name) -- never the traceback text, which can carry
    ARNs, and never an ARN or tag value of its own.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["error"] = record.exc_info[0].__name__
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def get_logger(name: str) -> logging.Logger:
    """Return a logger writing JSON to stdout at the `LOG_LEVEL` from the environment.

    Idempotent: repeated calls do not stack handlers, so importing this from two modules in one
    process does not double every line. `INFO` when `LOG_LEVEL` is unset or unrecognized.
    """
    logger = logging.getLogger(name)
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False
    if not any(getattr(h, "_dashboard_json", False) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        # Marker so a second get_logger() call recognizes its own handler and does not add another.
        handler._dashboard_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)
    return logger
