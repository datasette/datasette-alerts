"""Cron handler functions for datasette-alerts.

These replace the old bg_task loop. Each handler is registered with
datasette-cron and called on schedule.
"""

import json
import logging
import uuid

from datasette.database import Database

from .destinations import get_notifiers
from .internal_db import InternalDB
from .notifier import Message
from .template import resolve_template
from .trigger_db import claim_queue_items, complete_queue_items, fail_queue_item

logger = logging.getLogger("datasette_alerts.handlers")


def _get_alert_types(datasette):
    """Collect all registered custom alert types from plugins."""
    from datasette.plugins import pm

    alert_types = {}
    for result in pm.hook.datasette_alerts_register_alert_types(datasette=datasette):
        if result:
            for at in result:
                alert_types[at.slug] = at
    return alert_types


def _build_messages(
    meta: dict,
    new_ids: list[str],
    row_data: list[dict] | None,
    table_name: str,
    database_name: str,
) -> list[Message]:
    """Build Message objects from subscription meta, handling aggregate/template logic.

    This is the alert layer's responsibility — notifiers just receive Messages.
    """
    template_json = meta.get("message_template")
    aggregate = meta.get("aggregate", True)

    if template_json and isinstance(template_json, dict):
        if aggregate or not row_data:
            text = resolve_template(
                template_json,
                {
                    "count": str(len(new_ids)),
                    "table_name": table_name,
                },
            )
            return [Message(text)]
        else:
            messages = []
            for row in row_data:
                variables = {k: str(v) for k, v in row.items()}
                variables["table_name"] = table_name
                variables["database_name"] = database_name
                text = resolve_template(
                    template_json,
                    variables,
                )
                messages.append(Message(text))
            return messages
    else:
        return [Message(f"{len(new_ids)} new rows in {table_name}")]


def _notifier_config(meta: dict) -> dict:
    """Extract notifier-specific config from subscription meta.

    Removes alert-layer keys (aggregate, message_template) so the notifier
    only sees its own config (e.g. webhook_url, topic).
    """
    return {k: v for k, v in meta.items() if k not in ("aggregate", "message_template")}


async def _fetch_row_data(
    db: Database, table_name: str, id_column: str, ids: list
) -> list[dict]:
    """Fetch full row data for given IDs from the target database."""
    if not ids:
        return []
    result = await db.execute(
        f"SELECT * FROM [{table_name}] WHERE [{id_column}] IN (SELECT value FROM json_each(?))",
        [json.dumps(ids)],
    )
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row)) for row in result.rows]


async def _send_for_subscription(
    datasette,
    subscription,
    new_ids: list[str],
    row_data: list[dict] | None,
    table_name: str,
    database_name: str,
):
    """Build messages and send them through the subscription's notifier."""
    notifier = next(
        (n for n in await get_notifiers(datasette) if n.slug == subscription.notifier),
        None,
    )
    if notifier is None:
        logger.warning("Notifier not found: %s", subscription.notifier)
        return

    # Use destination config if available, otherwise fall back to legacy meta
    if subscription.destination_id:
        config = subscription.destination_config
    else:
        config = _notifier_config(subscription.meta)
    messages = _build_messages(
        subscription.meta, new_ids, row_data, table_name, database_name
    )

    for message in messages:
        await notifier.send(config, message)


async def cursor_alert_handler(datasette, config):
    """Cron handler for cursor-based alerts.

    config: {"alert_id": "..."}
    Replaces the old job_tick() + start_ready_jobs() pattern.
    """
    alert_id = config["alert_id"]
    internal_db = InternalDB(datasette.get_internal_database())

    # Fetch alert details
    alert = await internal_db.get_alert_for_check(alert_id)
    if alert is None:
        return

    db: Database = datasette.databases.get(alert.database_name)
    if db is None:
        logger.warning("Database %s not found", alert.database_name)
        return

    cursor = alert.cursor
    result = await db.execute(
        f"""
          SELECT
            {alert.id_columns[0]},
            {alert.timestamp_column}
          FROM {alert.table_name}
          WHERE {alert.timestamp_column} > ?
        """,
        [cursor],
    )
    new_ids = [row[0] for row in result]
    cursor = max([row[1] for row in result], default=cursor)
    logger.debug("cursor check: alert=%s new_ids=%s cursor=%s", alert_id, new_ids, cursor)
    await internal_db.add_log(alert_id, new_ids, cursor)

    if len(new_ids) > 0:
        new_ids = [str(id) for id in new_ids]
        subscriptions = await internal_db.alert_subscriptions(alert_id)

        for subscription in subscriptions:
            # Fetch row data if non-aggregate mode
            row_data = None
            aggregate = subscription.meta.get("aggregate", True)
            if not aggregate and alert.id_columns:
                try:
                    row_data = await _fetch_row_data(
                        db, alert.table_name, alert.id_columns[0], new_ids
                    )
                except Exception as e:
                    logger.warning("Failed to fetch row data: %s", e)

            await _send_for_subscription(
                datasette,
                subscription,
                new_ids,
                row_data,
                alert.table_name,
                alert.database_name,
            )


async def trigger_queue_handler(datasette, config):
    """Cron handler for trigger-based alerts (global drain).

    config: {} (runs for all trigger alerts)
    Replaces the trigger processing loop from bg_task.
    """
    internal_db = InternalDB(datasette.get_internal_database())
    trigger_alerts = await internal_db.get_trigger_alerts()

    for alert in trigger_alerts:
        db: Database = datasette.databases.get(alert.database_name)
        if db is None:
            continue

        worker_id = str(uuid.uuid4())
        try:
            items = await claim_queue_items(db, alert.alert_id, worker_id)
        except Exception:
            continue
        if not items:
            continue

        new_ids = [item["item_id"] for item in items]
        item_db_ids = [item["id"] for item in items]
        logger.debug("trigger %s: %d items", alert.alert_id, len(new_ids))

        await internal_db.add_log(alert.alert_id, new_ids, "")

        subscriptions = await internal_db.alert_subscriptions(alert.alert_id)
        for subscription in subscriptions:
            try:
                # Fetch row data if non-aggregate mode
                row_data = None
                aggregate = subscription.meta.get("aggregate", True)
                if not aggregate and alert.id_columns:
                    try:
                        row_data = await _fetch_row_data(
                            db, alert.table_name, alert.id_columns[0], new_ids
                        )
                    except Exception as e2:
                        logger.warning("Failed to fetch row data: %s", e2)

                await _send_for_subscription(
                    datasette,
                    subscription,
                    new_ids,
                    row_data,
                    alert.table_name,
                    alert.database_name,
                )
            except Exception as e:
                logger.error("trigger notifier error: %s", e)
                for item_db_id in item_db_ids:
                    await fail_queue_item(
                        db, alert.alert_id, item_db_id, worker_id, str(e)
                    )
                break
        else:
            await complete_queue_items(db, alert.alert_id, item_db_ids, worker_id)


async def custom_alert_handler(datasette, config):
    """Cron handler for custom alert types.

    config: {"alert_id": "...", "type_slug": "..."}
    Looks up the registered AlertType by slug, calls check(), sends messages.
    """
    alert_id = config["alert_id"]
    type_slug = config["type_slug"]

    logger.debug(
        "custom_alert_handler called: alert_id=%s, type_slug=%s", alert_id, type_slug
    )

    alert_types = _get_alert_types(datasette)
    alert_type = alert_types.get(type_slug)
    if alert_type is None:
        logger.error(
            "Custom alert type not found: %s (available: %s)",
            type_slug,
            list(alert_types.keys()),
        )
        return

    internal_db = InternalDB(datasette.get_internal_database())
    alert = await internal_db.get_alert_for_check(alert_id)
    if alert is None:
        logger.error("Alert not found in DB: %s", alert_id)
        return

    custom_config = json.loads(alert.custom_config or "{}")
    last_check_at = alert.last_check_at

    logger.debug(
        "Calling %s.check(): db=%s, last_check_at=%s, config=%s",
        type_slug,
        alert.database_name,
        last_check_at,
        custom_config,
    )

    try:
        messages = await alert_type.check(
            datasette=datasette,
            alert_config=custom_config,
            database_name=alert.database_name,
            last_check_at=last_check_at,
        )
    except Exception as e:
        logger.error("Custom alert check failed for %s: %s", alert_id, e, exc_info=True)
        return

    await internal_db.update_last_check(alert_id)

    logger.info(
        "custom_alert_handler: alert=%s type=%s messages=%d",
        alert_id[:12],
        type_slug,
        len(messages),
    )

    if messages:
        subscriptions = await internal_db.alert_subscriptions(alert_id)
        notifiers = await get_notifiers(datasette)

        logger.debug(
            "Sending %d messages to %d subscriptions (notifiers available: %s)",
            len(messages),
            len(subscriptions),
            [n.slug for n in notifiers],
        )

        for subscription in subscriptions:
            notifier = next(
                (n for n in notifiers if n.slug == subscription.notifier),
                None,
            )
            if notifier is None:
                logger.error(
                    "Notifier not found: %s (available: %s)",
                    subscription.notifier,
                    [n.slug for n in notifiers],
                )
                continue

            if subscription.destination_id:
                notifier_config = subscription.destination_config
            else:
                notifier_config = _notifier_config(subscription.meta)

            logger.debug(
                "Sending via %s to destination %s",
                subscription.notifier,
                subscription.destination_id,
            )

            for message in messages:
                try:
                    await notifier.send(notifier_config, message)
                    logger.info("Sent: %s", message.text[:80])
                except Exception as e:
                    logger.error("Custom alert send failed: %s", e, exc_info=True)

        # Log the alert check
        await internal_db.add_log(
            alert_id,
            [f"custom:{i}" for i in range(len(messages))],
            "",
        )
