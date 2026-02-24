import json

from .internal_db import InternalDB, ReadyJob, TriggerAlert
from datasette.utils import await_me_maybe
from typing import List
import asyncio
import uuid
from datasette.plugins import pm
from .notifier import Notifier
from datasette.database import Database
from .trigger_db import claim_queue_items, complete_queue_items, fail_queue_item

async def _fetch_row_data(db: Database, table_name: str, id_column: str, ids: list) -> list[dict]:
    """Fetch full row data for given IDs from the target database."""
    if not ids:
        return []
    result = await db.execute(
        f"SELECT * FROM [{table_name}] WHERE [{id_column}] IN (SELECT value FROM json_each(?))",
        [json.dumps(ids)],
    )
    columns = [desc[0] for desc in result.description]
    return [dict(zip(columns, row)) for row in result.rows]


async def get_notifiers(datasette) -> List[Notifier]:
    notifiers = []
    for result in pm.hook.datasette_alerts_register_notifiers(datasette=datasette):
        result = await await_me_maybe(result)
        notifiers.extend(result)
    return notifiers


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
    cursor = max(
        [row[1] for row in result], default=job.cursor
    )
    print(job.alert_id, new_ids, cursor)
    await internal_db.add_log(job.alert_id, new_ids, cursor) # type: ignore
    await internal_db.schedule_next(job.alert_id)

    if len(new_ids) > 0:
        subscriptions = await internal_db.alert_subscriptions(job.alert_id)
        print(subscriptions)
        for subscription in subscriptions:
            notifier = next(
                (
                    n
                    for n in await get_notifiers(datasette)
                    if n.slug == subscription.notifier
                ),
                None,
            )
            if notifier is None:
                print("Notifier not found")
                continue
            print(f"Sending {len(new_ids)} new ids to {notifier.name}")
            new_ids = [str(id) for id in new_ids]

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

            await notifier.send(
                job.alert_id, new_ids, subscription.meta,
                row_data=row_data,
                table_name=job.table_name,
                database_name=job.database_name,
            )

async def trigger_tick(datasette, internal_db: InternalDB, alert: TriggerAlert):
    db: Database = datasette.databases.get(alert.database_name)
    if db is None:
        return
    worker_id = str(uuid.uuid4())
    try:
        items = await claim_queue_items(db, alert.alert_id, worker_id)
    except Exception:
        # Queue table may not exist yet or DB error
        return
    if not items:
        return

    new_ids = [item["item_id"] for item in items]
    item_db_ids = [item["id"] for item in items]
    print(f"trigger {alert.alert_id}: {len(new_ids)} items")

    await internal_db.add_log(alert.alert_id, new_ids, "")

    subscriptions = await internal_db.alert_subscriptions(alert.alert_id)
    for subscription in subscriptions:
        notifier = next(
            (n for n in await get_notifiers(datasette) if n.slug == subscription.notifier),
            None,
        )
        if notifier is None:
            continue
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

            await notifier.send(
                alert.alert_id, new_ids, subscription.meta,
                row_data=row_data,
                table_name=alert.table_name,
                database_name=alert.database_name,
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
