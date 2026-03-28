from sqlite_utils import Database
from sqlite_migrate import Migrations

internal_migrations = Migrations("datasette-alerts.internal")


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


@internal_migrations()
def m002_trigger_alerts(db: Database):
    db.executescript(
        """
          ALTER TABLE datasette_alerts_alerts
            ADD COLUMN alert_type TEXT NOT NULL DEFAULT 'cursor';
          ALTER TABLE datasette_alerts_alerts
            ADD COLUMN filter_params TEXT;
        """
    )


@internal_migrations()
def m003_destinations(db: Database):
    db.executescript(
        """
          CREATE TABLE datasette_alerts_destinations (
            id TEXT PRIMARY KEY,
            notifier TEXT NOT NULL,
            label TEXT NOT NULL,
            config JSON NOT NULL DEFAULT '{}',
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
          );

          ALTER TABLE datasette_alerts_subscriptions
            ADD COLUMN destination_id TEXT REFERENCES datasette_alerts_destinations(id);
        """
    )
