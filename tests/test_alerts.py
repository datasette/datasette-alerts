from datasette.app import Datasette
from datasette_alerts import (
    Notifier,
    InternalDB,
    NewAlertRouteParameters,
    NewSubscription,
)
from wtforms import Form, StringField
import pytest
import pytest_asyncio
import sqlite3
import asyncio
import json


class MockNotifier(Notifier):
    """A mock notifier for testing."""

    @property
    def slug(self):
        return "mock-notifier"

    @property
    def name(self):
        return "Mock Notifier"

    description = "A test notifier"
    icon = "🔔"

    def __init__(self):
        self.sent_messages = []

    async def send(self, alert_id, new_ids, meta):
        """Record sent messages for testing."""
        self.sent_messages.append(
            {"alert_id": alert_id, "new_ids": new_ids, "meta": meta}
        )

    async def get_config_form(self):
        """Return a simple config form."""

        class ConfigForm(Form):
            url = StringField("URL")

        return ConfigForm


@pytest_asyncio.fixture
async def datasette(tmpdir):
    """Create a test Datasette instance with a sample database."""
    data = str(tmpdir / "data.db")
    db = sqlite3.connect(data)
    with db:
        db.execute(
            """
            create table events (
                id integer primary key,
                title text,
                created_at timestamp default current_timestamp
            )
        """
        )
        db.execute(
            """
            insert into events (title, created_at)
            values ('Event 1', '2024-01-01 10:00:00')
        """
        )
        db.execute(
            """
            insert into events (title, created_at)
            values ('Event 2', '2024-01-01 11:00:00')
        """
        )

    datasette = Datasette([data])
    datasette._test_db = db
    await datasette.invoke_startup()
    return datasette


@pytest.mark.asyncio
async def test_plugin_loads_and_creates_tables(datasette):
    """Test that the plugin loads and creates internal tables."""
    internal_db = datasette.get_internal_database()

    # Check that internal tables exist
    tables = await internal_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    table_names = [row[0] for row in tables.rows]

    assert "datasette_alerts_alerts" in table_names
    assert "datasette_alerts_subscriptions" in table_names
    assert "datasette_alerts_alert_logs" in table_names


@pytest.mark.asyncio
async def test_internal_db_new_alert(datasette):
    """Test creating a new alert."""
    internal_db = InternalDB(datasette.get_internal_database())

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[
            NewSubscription(
                notifier_slug="test-notifier", meta={"url": "https://example.com"}
            )
        ],
    )

    alert_id = await internal_db.new_alert(params, "2024-01-01 11:00:00")

    # Verify alert was created
    assert alert_id is not None

    # Check alert details
    db = datasette.get_internal_database()
    result = await db.execute(
        "SELECT * FROM datasette_alerts_alerts WHERE id = ?", [alert_id]
    )
    alert = dict(result.first())

    assert alert["database_name"] == "data"
    assert alert["table_name"] == "events"
    assert json.loads(alert["id_columns"]) == ["id"]
    assert alert["timestamp_column"] == "created_at"
    assert alert["frequency"] == "+1 hour"

    # Check subscription was created
    subscriptions = await db.execute(
        "SELECT * FROM datasette_alerts_subscriptions WHERE alert_id = ?", [alert_id]
    )
    sub = dict(subscriptions.first())
    assert sub["notifier"] == "test-notifier"
    assert json.loads(sub["meta"]) == {"url": "https://example.com"}

    # Check initial log entry was created
    logs = await db.execute(
        "SELECT * FROM datasette_alerts_alert_logs WHERE alert_id = ?", [alert_id]
    )
    log = dict(logs.first())
    assert json.loads(log["new_ids"]) == []
    assert log["cursor"] == "2024-01-01 11:00:00"


@pytest.mark.asyncio
async def test_internal_db_alert_subscriptions(datasette):
    """Test fetching alert subscriptions."""
    internal_db = InternalDB(datasette.get_internal_database())

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[
            NewSubscription(notifier_slug="notifier1", meta={"key1": "value1"}),
            NewSubscription(notifier_slug="notifier2", meta={"key2": "value2"}),
        ],
    )

    alert_id = await internal_db.new_alert(params, "2024-01-01 00:00:00")

    # Fetch subscriptions
    subscriptions = await internal_db.alert_subscriptions(alert_id)

    assert len(subscriptions) == 2
    assert subscriptions[0]["notifier"] == "notifier1"
    assert json.loads(subscriptions[0]["meta"]) == {"key1": "value1"}
    assert subscriptions[1]["notifier"] == "notifier2"
    assert json.loads(subscriptions[1]["meta"]) == {"key2": "value2"}


@pytest.mark.asyncio
async def test_internal_db_add_log(datasette):
    """Test adding a log entry."""
    internal_db = InternalDB(datasette.get_internal_database())

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[],
    )

    alert_id = await internal_db.new_alert(params, "2024-01-01 00:00:00")

    # Add a log entry
    await internal_db.add_log(alert_id, ["1", "2", "3"], "2024-01-01 12:00:00")

    # Verify log entry
    db = datasette.get_internal_database()
    logs = await db.execute(
        "SELECT * FROM datasette_alerts_alert_logs WHERE alert_id = ? ORDER BY logged_at ASC",
        [alert_id],
    )
    rows = list(logs.rows)

    # Should have 2 logs: initial + new one
    assert len(rows) == 2

    # First log is the initial empty one
    initial_log = dict(rows[0])
    assert json.loads(initial_log["new_ids"]) == []
    assert initial_log["cursor"] == "2024-01-01 00:00:00"

    # Second log is the new one we added
    latest_log = dict(rows[1])
    assert json.loads(latest_log["new_ids"]) == ["1", "2", "3"]
    assert latest_log["cursor"] == "2024-01-01 12:00:00"


@pytest.mark.asyncio
async def test_internal_db_schedule_next(datasette):
    """Test scheduling the next alert run."""
    internal_db = InternalDB(datasette.get_internal_database())

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[],
    )

    alert_id = await internal_db.new_alert(params, "2024-01-01 00:00:00")

    # Simulate starting the job
    db = datasette.get_internal_database()
    await db.execute_write(
        "UPDATE datasette_alerts_alerts SET current_schedule_started_at = datetime('now') WHERE id = ?",
        [alert_id],
    )

    # Schedule next run
    await internal_db.schedule_next(alert_id)

    # Verify next_deadline was updated and current_schedule_started_at was cleared
    result = await db.execute(
        "SELECT next_deadline, current_schedule_started_at FROM datasette_alerts_alerts WHERE id = ?",
        [alert_id],
    )
    row = dict(result.first())

    assert row["next_deadline"] is not None
    assert row["current_schedule_started_at"] is None


@pytest.mark.asyncio
async def test_internal_db_start_ready_jobs(datasette):
    """Test finding and starting ready jobs."""
    internal_db = InternalDB(datasette.get_internal_database())

    # Create an alert with a deadline in the past
    db = datasette.get_internal_database()

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[],
    )

    alert_id = await internal_db.new_alert(params, "2024-01-01 00:00:00")

    # Set the deadline to the past
    await db.execute_write(
        "UPDATE datasette_alerts_alerts SET next_deadline = datetime('now', '-1 hour') WHERE id = ?",
        [alert_id],
    )

    # Get ready jobs
    ready_jobs = await internal_db.start_ready_jobs()

    assert len(ready_jobs) == 1
    job = ready_jobs[0]
    assert job.alert_id == alert_id
    assert job.database_name == "data"
    assert job.table_name == "events"
    assert job.id_columns == ["id"]
    assert job.timestamp_column == "created_at"
    assert job.cursor == "2024-01-01 00:00:00"

    # Verify current_schedule_started_at was set
    result = await db.execute(
        "SELECT current_schedule_started_at FROM datasette_alerts_alerts WHERE id = ?",
        [alert_id],
    )
    row = dict(result.first())
    assert row["current_schedule_started_at"] is not None


@pytest.mark.asyncio
async def test_api_new_alert_endpoint(datasette):
    """Test the API endpoint for creating alerts."""
    payload = {
        "database_name": "data",
        "table_name": "events",
        "id_columns": ["id"],
        "timestamp_column": "created_at",
        "frequency": "+1 hour",
        "subscriptions": [
            {"notifier_slug": "test-notifier", "meta": {"url": "https://example.com"}}
        ],
    }

    response = await datasette.client.post(
        "/-/datasette-alerts/api/new-alert", json=payload
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "alert_id" in data["data"]

    # Verify alert was created
    alert_id = data["data"]["alert_id"]
    db = datasette.get_internal_database()
    result = await db.execute(
        "SELECT * FROM datasette_alerts_alerts WHERE id = ?", [alert_id]
    )
    alert = dict(result.first())
    assert alert["table_name"] == "events"


@pytest.mark.asyncio
async def test_api_new_alert_invalid_database(datasette):
    """Test API endpoint with invalid database name."""
    payload = {
        "database_name": "nonexistent",
        "table_name": "events",
        "id_columns": ["id"],
        "timestamp_column": "created_at",
        "frequency": "+1 hour",
        "subscriptions": [],
    }

    response = await datasette.client.post(
        "/-/datasette-alerts/api/new-alert", json=payload
    )

    assert response.status_code == 404
    data = response.json()
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_api_new_alert_invalid_payload(datasette):
    """Test API endpoint with invalid payload."""
    response = await datasette.client.post(
        "/-/datasette-alerts/api/new-alert", json={"invalid": "payload"}
    )

    assert response.status_code == 400
    data = response.json()
    assert data["ok"] is False


@pytest.mark.asyncio
async def test_api_new_alert_wrong_method(datasette):
    """Test API endpoint with GET instead of POST."""
    response = await datasette.client.get("/-/datasette-alerts/api/new-alert")

    assert response.status_code == 405


@pytest.mark.asyncio
async def test_table_action_link_with_permission(datasette):
    """Test that the table action link appears when user has permission."""
    # Set root_enabled to allow root permissions
    datasette.root_enabled = True

    # Create a signed cookie for root user
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}

    # Visit the table page
    response = await datasette.client.get("/data/events", cookies=cookies)
    assert response.status_code == 200

    # Check that the alert configuration link is present
    assert "Configure new alert" in response.text
    assert (
        "/-/datasette-alerts/new-alert?db_name=data&amp;table_name=events"
        in response.text
    )


@pytest.mark.asyncio
async def test_table_action_link_without_permission(datasette):
    """Test that the table action link does not appear without permission."""
    # Visit the table page without authentication
    response = await datasette.client.get("/data/events")
    assert response.status_code == 200

    # Check that the alert configuration link is NOT present
    assert "Configure new alert" not in response.text
    assert "datasette-alerts/new-alert" not in response.text
