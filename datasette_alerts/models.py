from dataclasses import dataclass
from typing import Optional


@dataclass
class AlertRecord:
    """Returned by get_all_alerts()."""

    id: str
    database_name: str
    table_name: str
    id_columns: list
    timestamp_column: str
    frequency: str
    alert_type: str
    custom_config: str
    last_check_at: Optional[str]


@dataclass
class AlertForCheck:
    """Returned by get_alert_for_check()."""

    id: str
    database_name: str
    table_name: str
    id_columns: list
    timestamp_column: str
    frequency: str
    alert_type: str
    custom_config: str
    last_check_at: Optional[str]
    cursor: str


@dataclass
class SubscriptionDetail:
    """Nested in AlertDetail."""

    id: str
    notifier: str
    meta: dict
    destination_id: str
    destination_label: str


@dataclass
class AlertLogEntry:
    """Nested in AlertDetail."""

    logged_at: str
    new_ids: list
    cursor: str


@dataclass
class AlertDetail:
    """Returned by get_alert_detail()."""

    id: str
    database_name: str
    table_name: str
    id_columns: list
    timestamp_column: str
    frequency: str
    next_deadline: Optional[str]
    alert_created_at: Optional[str]
    seconds_until_next: Optional[int]
    alert_type: str
    filter_params: list
    custom_config: str
    last_check_at: Optional[str]
    subscriptions: list  # list[SubscriptionDetail]
    logs: list  # list[AlertLogEntry]


@dataclass
class AlertCleanupInfo:
    """Returned by delete_alert()."""

    alert_type: str
    database_name: str
    table_name: str
