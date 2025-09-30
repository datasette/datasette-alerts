from .internal_db import InternalDB, ReadyJob
from datasette.utils import await_me_maybe
from typing import List
import asyncio
from datasette.plugins import pm
from .notifier import Notifier
from datasette.database import Database

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
            await notifier.send(
                job.alert_id, new_ids, subscription.meta
            )

async def bg_task(datasette):
    internal_db = InternalDB(datasette.get_internal_database())
    while True:
        ready_jobs = await internal_db.start_ready_jobs()
        if not ready_jobs:
            await asyncio.sleep(1)
            continue
        for job in ready_jobs:
            await job_tick(datasette, internal_db, job)
            
        await asyncio.sleep(1)
