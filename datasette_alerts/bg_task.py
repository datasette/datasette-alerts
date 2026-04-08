import json

from .internal_db import InternalDB, ReadyJob, TriggerAlert
from .notifier import Message
from .template import resolve_template
from .destinations import get_notifiers
import asyncio
import uuid
from datasette.database import Database
from .trigger_db import claim_queue_items, complete_queue_items, fail_queue_item


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
        print(f"Notifier not found: {subscription.notifier}")
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


async def job_tick(datasette, internal_db: InternalDB, job: ReadyJob):
    db: Database = datasette.databases.get(job.database_name)
    if db is None:
        raise Exception(f"Database {job.database_name} not found")
    result = await db.execute(
        f"""
          SELECT
            {job.id_columns[0]},
            {job.timestamp_column}
          FROM {job.table_name}
          WHERE {job.timestamp_column} > ?
        """,
        [job.cursor],
    )
    new_ids = [row[0] for row in result]
    cursor = max([row[1] for row in result], default=job.cursor)
    print(job.alert_id, new_ids, cursor)
    await internal_db.add_log(job.alert_id, new_ids, cursor)  # type: ignore
    await internal_db.schedule_next(job.alert_id)

    if len(new_ids) > 0:
        new_ids = [str(id) for id in new_ids]
        subscriptions = await internal_db.alert_subscriptions(job.alert_id)

        for subscription in subscriptions:
            # Fetch row data if non-aggregate mode
            row_data = None
            aggregate = subscription.meta.get("aggregate", True)
            if not aggregate and job.id_columns:
                try:
                    row_data = await _fetch_row_data(
                        db, job.table_name, job.id_columns[0], new_ids
                    )
                except Exception as e:
                    print(f"Failed to fetch row data: {e}")

            await _send_for_subscription(
                datasette,
                subscription,
                new_ids,
                row_data,
                job.table_name,
                job.database_name,
            )


async def trigger_tick(datasette, internal_db: InternalDB, alert: TriggerAlert):
    db: Database = datasette.databases.get(alert.database_name)
    if db is None:
        return
    worker_id = str(uuid.uuid4())
    try:
        items = await claim_queue_items(db, alert.alert_id, worker_id)
    except Exception:
        return
    if not items:
        return

    new_ids = [item["item_id"] for item in items]
    item_db_ids = [item["id"] for item in items]
    print(f"trigger {alert.alert_id}: {len(new_ids)} items")

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
                    print(f"Failed to fetch row data: {e2}")

            await _send_for_subscription(
                datasette,
                subscription,
                new_ids,
                row_data,
                alert.table_name,
                alert.database_name,
            )
        except Exception as e:
            print(f"trigger notifier error: {e}")
            for item_db_id in item_db_ids:
                await fail_queue_item(db, alert.alert_id, item_db_id, worker_id, str(e))
            return

    await complete_queue_items(db, alert.alert_id, item_db_ids, worker_id)


async def bg_task(datasette):
    internal_db = InternalDB(datasette.get_internal_database())
    while True:
        # Process cursor alerts
        ready_jobs = await internal_db.start_ready_jobs()
        for job in ready_jobs:
            await job_tick(datasette, internal_db, job)

        # Process trigger alerts
        trigger_alerts = await internal_db.get_trigger_alerts()
        for alert in trigger_alerts:
            await trigger_tick(datasette, internal_db, alert)

        await asyncio.sleep(1)
