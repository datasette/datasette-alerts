from abc import ABC, abstractmethod
from pydantic import BaseModel


class ConfigElement(BaseModel):
    """Declares a web component for rich notifier configuration UI.

    Notifiers can return this from get_config_element() to provide
    a custom web component instead of the default WTForms-based config.
    """

    tag: str  # Custom element tag name, e.g. "datasette-discord-destination-form"
    scripts: list[
        str
    ]  # JS files to load, e.g. ["/-/static-plugins/datasette-alerts-discord/config.js"]


class Message:
    """A message to be delivered through a notifier.

    Notifiers receive this and deliver it to the configured destination.
    The alert system (or any other caller) is responsible for constructing
    the message content before passing it to a notifier.
    """

    def __init__(self, text: str, *, subject: str | None = None):
        self.text = text
        self.subject = subject


class Notifier(ABC):
    @property
    @abstractmethod
    def slug(self): ...

    @property
    @abstractmethod
    def name(self): ...

    description: str = ""
    icon: str = ""

    def get_config_form(self):
        """
        Returns a WTForms form class for configuring this notifier.
        The form should have fields that match the configuration options
        required by the notifier (e.g. webhook_url, channel, topic).

        Do NOT include aggregate or message_template fields here —
        those are handled by the alert layer.
        """
        raise NotImplementedError("Subclasses must implement get_config_form")

    def get_config_element(self) -> ConfigElement | None:
        """
        Optionally return a ConfigElement to use a web component for
        destination configuration instead of WTForms.

        The web component contract:
        - Inputs: config (JSON), datasette-base-url, database-name attributes
        - Output: config-change CustomEvent with { config: {...}, valid: bool }
        """
        return None

    async def send(self, config: dict, message: Message):
        """
        Deliver a message to the destination described by config.

        :param config: Notifier-specific configuration (e.g. webhook_url, channel).
        :param message: The message to deliver.
        """
        raise NotImplementedError("Subclasses must implement send method")
