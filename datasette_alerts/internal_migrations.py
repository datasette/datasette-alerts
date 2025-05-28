from sqlite_utils import Database
from sqlite_migrate import Migrations
from pathlib import Path

internal_migrations = Migrations("datasette-alerts.internal")


ALERTS_TABLE = "datasette_alerts_alerts"
ALERT_LOGS_TABLE = "datasette_alerts_alert_logs"


@internal_migrations()
def m001_initial(db: Database):
    db.executescript(
        """
          create table datasette_alerts_alerts(
            id text primary key,
            alert_creator_id text,
            alert_created_at timestamp default current_timestamp,
            database_name text NOT NULL,
            table_name text,
            id_columns text,
            timestamp_column text,
            frequency text,
            next_deadline timestamp,
            current_schedule_started_at timestamp
          );

          create table datasette_alerts_subscriptions(
            id text primary key,
            alert_id text references alerts(id),
            notifier text,
            meta json
          );
          
          create table datasette_alerts_alert_logs(
            id text primary key,
            alert_id text references datasette_alerts_alerts(id),
            logged_at timestamp default current_timestamp,
            new_ids json,
            cursor any
          );
        """
    )
