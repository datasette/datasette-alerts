from abc import ABC, abstractmethod
from typing import List

class Alert:
    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description
    
    def resolve_ids(self, ids: List[str]) -> List[str]:
        return []
        
class Notifier(ABC):
    @property
    @abstractmethod
    def slug(self):
        # A unique short text identifier for this notifier
        ...

    @property
    @abstractmethod
    def name(self):
        # The name of this enrichment
        ...

    description: str = ""  # Short description of this enrichment
    icon: str = ""

    def get_config_form(self):
        """
        Returns a WTForms form class for configuring this notifier.
        The form should have fields that match the configuration options
        required by the notifier.
        """
        raise NotImplementedError("Subclasses must implement get_config_form")

    async def send(
        self,
        alert_id: str,
        new_ids: list[str],
        config: dict,
        *,
        row_data: list[dict] | None = None,
        table_name: str | None = None,
        database_name: str | None = None,
    ):
        """
        Sends the alert notification.

        :param alert_id: The ID of the alert being notified about.
        :param new_ids: A list of new IDs that triggered the alert.
        :param config: A dictionary containing configuration options for this notifier.
        :param row_data: Full row data for each new ID (when aggregate is false).
        :param table_name: Name of the table that triggered the alert.
        :param database_name: Name of the database that triggered the alert.
        """
        raise NotImplementedError("Subclasses must implement send method")