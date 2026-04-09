"""Backward-compatibility shim.

The bg_task loop has been replaced by cron handlers in handlers.py.
This module re-exports helpers that external code may still import.
"""

from .handlers import (  # noqa: F401
    _build_messages,
    _fetch_row_data,
    _send_for_subscription,
)
