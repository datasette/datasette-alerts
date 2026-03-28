from abc import ABC, abstractmethod


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
    def slug(self):
        ...

    @property
    @abstractmethod
    def name(self):
        ...

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

    async def send(self, config: dict, message: Message):
        """
        Deliver a message to the destination described by config.

        :param config: Notifier-specific configuration (e.g. webhook_url, channel).
        :param message: The message to deliver.
        """
        raise NotImplementedError("Subclasses must implement send method")
