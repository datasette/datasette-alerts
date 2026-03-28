"""Public API for sending messages through configured destinations."""

from .internal_db import InternalDB
from .notifier import Message, Notifier
from datasette.utils import await_me_maybe
from datasette.plugins import pm
from typing import List


class DestinationNotFound(Exception):
    pass


class NotifierNotFound(Exception):
    pass


async def get_notifiers(datasette) -> List[Notifier]:
    """Collect all registered notifiers from plugins."""
    notifiers = []
    for result in pm.hook.datasette_alerts_register_notifiers(datasette=datasette):
        result = await await_me_maybe(result)
        notifiers.extend(result)
    return notifiers


def _find_notifier(notifiers: List[Notifier], slug: str) -> Notifier | None:
    return next((n for n in notifiers if n.slug == slug), None)


async def send_to_destination(datasette, destination_id: str, message: Message) -> None:
    """
    Send a message through a configured destination.

    This is the public API for any plugin to send notifications
    without needing the alert system.

    :param datasette: The Datasette instance.
    :param destination_id: ID of the destination to send through.
    :param message: The Message to deliver.
    :raises DestinationNotFound: If the destination_id doesn't exist.
    :raises NotifierNotFound: If the destination's notifier plugin is missing.
    """
    internal_db = InternalDB(datasette.get_internal_database())
    dest = await internal_db.get_destination(destination_id)
    if dest is None:
        raise DestinationNotFound(f"Destination {destination_id!r} not found")

    notifiers = await get_notifiers(datasette)
    notifier = _find_notifier(notifiers, dest.notifier)
    if notifier is None:
        raise NotifierNotFound(f"Notifier {dest.notifier!r} not found")

    await notifier.send(dest.config, message)
