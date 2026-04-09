from datasette import hookimpl
from datasette.app import Datasette
from datasette_alerts import (
    Notifier,
    Message,
    InternalDB,
    NewAlertRouteParameters,
    NewSubscription,
    send_to_destination,
    DestinationNotFound,
    NotifierNotFound,
)
from datasette_alerts.internal_db import NewDestination
from datasette_alerts.bg_task import _build_messages
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

    async def send(self, config, message):
        """Record sent messages for testing."""
        self.sent_messages.append(
            {"config": config, "message": message}
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

    datasette = Datasette(
        [data],
        config={
            "permissions": {
                "datasette-alerts-access": {"id": "*"},
            },
        },
    )
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
    """Test creating a new alert with a destination-based subscription."""
    internal_db = InternalDB(datasette.get_internal_database())

    # Create a destination first
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="test-notifier", label="Test Dest", config={"url": "https://example.com"})
    )

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={"aggregate": True})
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

    # Check subscription was created with destination_id
    subscriptions = await db.execute(
        "SELECT * FROM datasette_alerts_subscriptions WHERE alert_id = ?", [alert_id]
    )
    sub = dict(subscriptions.first())
    assert sub["destination_id"] == dest_id
    assert json.loads(sub["meta"]) == {"aggregate": True}

    # Check initial log entry was created
    logs = await db.execute(
        "SELECT * FROM datasette_alerts_alert_logs WHERE alert_id = ?", [alert_id]
    )
    log = dict(logs.first())
    assert json.loads(log["new_ids"]) == []
    assert log["cursor"] == "2024-01-01 11:00:00"


@pytest.mark.asyncio
async def test_internal_db_alert_subscriptions(datasette):
    """Test fetching alert subscriptions with destinations."""
    internal_db = InternalDB(datasette.get_internal_database())

    dest1_id = await internal_db.create_destination(
        NewDestination(notifier="notifier1", label="Dest 1", config={"key1": "value1"})
    )
    dest2_id = await internal_db.create_destination(
        NewDestination(notifier="notifier2", label="Dest 2", config={"key2": "value2"})
    )

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[
            NewSubscription(destination_id=dest1_id, meta={"aggregate": True}),
            NewSubscription(destination_id=dest2_id, meta={"aggregate": False}),
        ],
    )

    alert_id = await internal_db.new_alert(params, "2024-01-01 00:00:00")

    # Fetch subscriptions
    subscriptions = await internal_db.alert_subscriptions(alert_id)

    assert len(subscriptions) == 2
    assert subscriptions[0].notifier == "notifier1"
    assert subscriptions[0].destination_id == dest1_id
    assert subscriptions[0].destination_config == {"key1": "value1"}
    assert subscriptions[0].destination_label == "Dest 1"
    assert subscriptions[1].notifier == "notifier2"
    assert subscriptions[1].destination_id == dest2_id
    assert subscriptions[1].destination_config == {"key2": "value2"}


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
    """Test the API endpoint for creating alerts with a destination."""
    internal_db = InternalDB(datasette.get_internal_database())
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="test-notifier", label="Test", config={"url": "https://example.com"})
    )

    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    payload = {
        "database_name": "data",
        "table_name": "events",
        "id_columns": ["id"],
        "timestamp_column": "created_at",
        "frequency": "+1 hour",
        "subscriptions": [
            {"destination_id": dest_id, "meta": {"aggregate": True}}
        ],
    }

    response = await datasette.client.post(
        "/-/data/datasette-alerts/api/new", json=payload, cookies=cookies
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
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    payload = {
        "database_name": "nonexistent",
        "table_name": "events",
        "id_columns": ["id"],
        "timestamp_column": "created_at",
        "frequency": "+1 hour",
        "subscriptions": [],
    }

    response = await datasette.client.post(
        "/-/nonexistent/datasette-alerts/api/new", json=payload, cookies=cookies
    )

    assert response.status_code == 404
    data = response.json()
    assert data["ok"] is False
    assert "not found" in data["error"]


@pytest.mark.asyncio
async def test_api_new_alert_invalid_payload(datasette):
    """Test API endpoint with invalid payload returns an error."""
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    response = await datasette.client.post(
        "/-/data/datasette-alerts/api/new", json={"invalid": "payload"}, cookies=cookies
    )

    assert response.status_code == 500


@pytest.mark.asyncio
async def test_api_new_alert_wrong_method(datasette):
    """Test API endpoint with GET instead of POST returns 404."""
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    response = await datasette.client.get(
        "/-/data/datasette-alerts/api/new", cookies=cookies
    )

    # GET hits the route but body parsing fails
    assert response.status_code == 500


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
    assert "Configure new row alert" in response.text
    assert (
        "/-/data/datasette-alerts/new?table_name=events"
        in response.text
    )


@pytest.mark.asyncio
async def test_table_action_link_without_permission(datasette):
    """Test that the table action link does not appear without permission."""
    # Visit the table page without authentication
    response = await datasette.client.get("/data/events")
    assert response.status_code == 200

    # Check that the alert configuration link is NOT present
    assert "Configure new row alert" not in response.text
    assert "datasette-alerts/new-alert" not in response.text


# --- Stage 1: Message + _build_messages tests ---


def test_message_basic():
    """Test Message class construction."""
    msg = Message("hello")
    assert msg.text == "hello"
    assert msg.subject is None


def test_message_with_subject():
    msg = Message("body text", subject="Alert!")
    assert msg.text == "body text"
    assert msg.subject == "Alert!"


def test_build_messages_fallback_no_template():
    """Without a template, _build_messages returns a single fallback message."""
    messages = _build_messages(
        meta={},
        new_ids=["1", "2", "3"],
        row_data=None,
        table_name="events",
        database_name="data",
    )
    assert len(messages) == 1
    assert messages[0].text == "3 new rows in events"


def test_build_messages_aggregate_with_template():
    """Aggregate mode with a template resolves count and table_name."""
    template_doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "templateVariable", "attrs": {"varName": "count"}},
                    {"type": "text", "text": " new in "},
                    {"type": "templateVariable", "attrs": {"varName": "table_name"}},
                ],
            }
        ],
    }
    messages = _build_messages(
        meta={"aggregate": True, "message_template": template_doc},
        new_ids=["1", "2"],
        row_data=None,
        table_name="events",
        database_name="data",
    )
    assert len(messages) == 1
    assert messages[0].text == "2 new in events"


def test_build_messages_per_row_with_template():
    """Non-aggregate mode builds one message per row."""
    template_doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Row: "},
                    {"type": "templateVariable", "attrs": {"varName": "title"}},
                ],
            }
        ],
    }
    row_data = [
        {"id": "1", "title": "First"},
        {"id": "2", "title": "Second"},
    ]
    messages = _build_messages(
        meta={"aggregate": False, "message_template": template_doc},
        new_ids=["1", "2"],
        row_data=row_data,
        table_name="events",
        database_name="data",
    )
    assert len(messages) == 2
    assert messages[0].text == "Row: First"
    assert messages[1].text == "Row: Second"


def test_build_messages_per_row_no_row_data_falls_back_to_aggregate():
    """Non-aggregate with no row_data falls back to aggregate behavior."""
    template_doc = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "templateVariable", "attrs": {"varName": "count"}},
                    {"type": "text", "text": " items"},
                ],
            }
        ],
    }
    messages = _build_messages(
        meta={"aggregate": False, "message_template": template_doc},
        new_ids=["1", "2", "3"],
        row_data=None,
        table_name="events",
        database_name="data",
    )
    assert len(messages) == 1
    assert messages[0].text == "3 items"


# --- Stage 2: Destination CRUD tests ---


@pytest.mark.asyncio
async def test_destination_crud(datasette):
    """Test full lifecycle: create, get, list, update, delete destinations."""
    internal_db = InternalDB(datasette.get_internal_database())

    # Create
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="slack", label="Ops Channel", config={"webhook_url": "https://hooks.slack.com/1"})
    )
    assert dest_id is not None

    # Get
    dest = await internal_db.get_destination(dest_id)
    assert dest is not None
    assert dest.notifier == "slack"
    assert dest.label == "Ops Channel"
    assert dest.config == {"webhook_url": "https://hooks.slack.com/1"}

    # List
    dests = await internal_db.list_destinations()
    assert len(dests) >= 1
    assert any(d.id == dest_id for d in dests)

    # Update
    await internal_db.update_destination(dest_id, "Ops Channel v2", {"webhook_url": "https://hooks.slack.com/2"})
    updated = await internal_db.get_destination(dest_id)
    assert updated.label == "Ops Channel v2"
    assert updated.config == {"webhook_url": "https://hooks.slack.com/2"}

    # Delete
    await internal_db.delete_destination(dest_id)
    deleted = await internal_db.get_destination(dest_id)
    assert deleted is None


@pytest.mark.asyncio
async def test_destination_not_found(datasette):
    """Test get_destination returns None for nonexistent ID."""
    internal_db = InternalDB(datasette.get_internal_database())
    result = await internal_db.get_destination("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_alert_detail_includes_destination_info(datasette):
    """Test that get_alert_detail includes destination info in subscriptions."""
    internal_db = InternalDB(datasette.get_internal_database())

    dest_id = await internal_db.create_destination(
        NewDestination(notifier="slack", label="My Slack", config={"webhook_url": "https://example.com"})
    )

    params = NewAlertRouteParameters(
        database_name="data",
        table_name="events",
        id_columns=["id"],
        timestamp_column="created_at",
        frequency="+1 hour",
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={"aggregate": True})
        ],
    )
    alert_id = await internal_db.new_alert(params, "2024-01-01 00:00:00")

    detail = await internal_db.get_alert_detail(alert_id)
    assert detail is not None
    assert len(detail.subscriptions) == 1
    sub = detail.subscriptions[0]
    assert sub.destination_id == dest_id
    assert sub.destination_label == "My Slack"
    assert sub.notifier == "slack"


# --- Stage 3: Destination API route tests ---


@pytest.mark.asyncio
async def test_api_create_destination(datasette):
    """Test creating a destination via API."""
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    response = await datasette.client.post(
        "/-/data/datasette-alerts/api/destinations/new",
        json={"notifier": "slack", "label": "Test Slack", "config": {"webhook_url": "https://hooks.slack.com/test"}},
        cookies=cookies,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "destination_id" in data["data"]


@pytest.mark.asyncio
async def test_api_update_destination(datasette):
    """Test updating a destination via API."""
    internal_db = InternalDB(datasette.get_internal_database())
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="slack", label="Old Label", config={"webhook_url": "https://old"})
    )

    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    response = await datasette.client.post(
        f"/-/data/datasette-alerts/api/destinations/{dest_id}/update",
        json={"label": "New Label", "config": {"webhook_url": "https://new"}},
        cookies=cookies,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # Verify update
    dest = await internal_db.get_destination(dest_id)
    assert dest.label == "New Label"
    assert dest.config == {"webhook_url": "https://new"}


@pytest.mark.asyncio
async def test_api_delete_destination(datasette):
    """Test deleting a destination via API."""
    internal_db = InternalDB(datasette.get_internal_database())
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="slack", label="To Delete", config={})
    )

    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    response = await datasette.client.post(
        f"/-/data/datasette-alerts/api/destinations/{dest_id}/delete",
        json={},
        cookies=cookies,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # Verify deleted
    dest = await internal_db.get_destination(dest_id)
    assert dest is None


@pytest.mark.asyncio
async def test_api_delete_destination_not_found(datasette):
    """Test deleting a nonexistent destination returns 404."""
    cookies = {"ds_actor": datasette.sign({"a": {"id": "root"}}, "actor")}
    response = await datasette.client.post(
        "/-/data/datasette-alerts/api/destinations/nonexistent/delete",
        json={},
        cookies=cookies,
    )
    assert response.status_code == 404
    assert response.json()["ok"] is False


# --- Stage 5: send_to_destination() tests ---

_mock_notifier_instance = MockNotifier()


class _MockNotifierPlugin:
    @staticmethod
    @hookimpl
    def datasette_alerts_register_notifiers(datasette):
        return [_mock_notifier_instance]


from datasette.plugins import pm as _pm
_pm.register(_MockNotifierPlugin(), name="test-mock-notifier-plugin")


@pytest.mark.asyncio
async def test_send_to_destination(datasette):
    """Test the public send_to_destination() API."""
    internal_db = InternalDB(datasette.get_internal_database())
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="mock-notifier", label="Test Mock", config={"key": "value"})
    )

    _mock_notifier_instance.sent_messages.clear()
    msg = Message("Hello from a plugin!", subject="Test")
    await send_to_destination(datasette, dest_id, msg)

    assert len(_mock_notifier_instance.sent_messages) == 1
    assert _mock_notifier_instance.sent_messages[0]["config"] == {"key": "value"}
    assert _mock_notifier_instance.sent_messages[0]["message"].text == "Hello from a plugin!"
    assert _mock_notifier_instance.sent_messages[0]["message"].subject == "Test"


@pytest.mark.asyncio
async def test_send_to_destination_not_found(datasette):
    """Test send_to_destination raises DestinationNotFound."""
    with pytest.raises(DestinationNotFound):
        await send_to_destination(datasette, "nonexistent", Message("test"))


@pytest.mark.asyncio
async def test_send_to_destination_notifier_not_found(datasette):
    """Test send_to_destination raises NotifierNotFound for unknown notifier."""
    internal_db = InternalDB(datasette.get_internal_database())
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="unknown-notifier", label="Bad", config={})
    )
    with pytest.raises(NotifierNotFound):
        await send_to_destination(datasette, dest_id, Message("test"))


# --- Stage 6: ConfigElement tests ---


def test_config_element():
    """Test ConfigElement model."""
    from datasette_alerts import ConfigElement
    ce = ConfigElement(tag="my-form", scripts=["/-/static/my-plugin/config.js"])
    assert ce.tag == "my-form"
    assert ce.scripts == ["/-/static/my-plugin/config.js"]


def test_notifier_get_config_element_default():
    """Default get_config_element returns None (WTForms path)."""
    notifier = MockNotifier()
    assert notifier.get_config_element() is None


def test_notifier_with_config_element():
    """A notifier can return a ConfigElement."""
    from datasette_alerts import ConfigElement

    class WebComponentNotifier(Notifier):
        slug = "wc-test"
        name = "WC Test"

        def get_config_element(self):
            return ConfigElement(
                tag="my-wc-form",
                scripts=["/-/static/test/config.js"],
            )

        async def send(self, config, message):
            pass

    notifier = WebComponentNotifier()
    ce = notifier.get_config_element()
    assert ce is not None
    assert ce.tag == "my-wc-form"
    assert ce.scripts == ["/-/static/test/config.js"]
