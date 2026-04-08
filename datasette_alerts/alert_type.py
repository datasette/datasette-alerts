from abc import ABC, abstractmethod
from datasette_alerts.notifier import Message, ConfigElement


class AlertType(ABC):
    """Base class for custom alert types.

    Plugins implement this to provide custom alert checking logic.
    datasette-alerts handles scheduling, delivery, and logging.
    """

    @property
    @abstractmethod
    def slug(self) -> str:
        """Unique identifier for this alert type, e.g. 'fec-filing'."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name, e.g. 'FEC Filing Alert'."""
        ...

    description: str = ""
    icon: str = ""

    @abstractmethod
    async def check(
        self,
        datasette,
        alert_config: dict,
        database_name: str,
        last_check_at: str | None,
    ) -> list[Message]:
        """Run custom check logic.

        Args:
            datasette: Datasette instance
            alert_config: dict from the alert's custom_config column
            database_name: which database this alert is scoped to
            last_check_at: ISO timestamp of last successful check, or None on first run

        Returns:
            List of Message objects to send. Empty list means nothing to report.
        """
        ...

    def get_config_element(self) -> ConfigElement | None:
        """Optional web component for configuring this alert type in the UI."""
        return None

    def get_config_form(self):
        """Optional WTForms form for configuration."""
        return None
