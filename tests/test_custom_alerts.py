"""Tests for custom alert types, cron integration, and handlers."""

import json
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlite3

from datasette import hookimpl
from datasette.app import Datasette
from datasette.plugins import pm as _pm
from datasette.plugins import pm as _global_pm

from datasette_alerts import (
    AlertType,
    InternalDB,
    Message,
    NewAlertRouteParameters,
    NewSubscription,
    _frequency_to_interval,
)
from datasette_alerts.handlers import _get_alert_types, custom_alert_handler
from datasette_alerts.internal_db import NewDestination


# ---------------------------------------------------------------------------
# Mock AlertType
# ---------------------------------------------------------------------------


class MockAlertType(AlertType):
    slug = "test-type"
    name = "Test Alert"
    description = "A test alert type"
    icon = "<svg/>"

    def __init__(self):
        self.check_calls = []

    async def check(self, datasette, alert_config, database_name, last_check_at):
        self.check_calls.append(
            {"config": alert_config, "db": database_name, "last": last_check_at}
        )
        return [Message("test alert fired")]


_mock_alert_type_instance = MockAlertType()


class _MockAlertTypePlugin:
    @staticmethod
    @hookimpl
    def datasette_alerts_register_alert_types(datasette):
        return [_mock_alert_type_instance]


_pm.register(_MockAlertTypePlugin(), name="test-mock-alert-type-plugin")


# ---------------------------------------------------------------------------
# Mock notifier for subscription send tests
# ---------------------------------------------------------------------------


from datasette_alerts import Notifier
from wtforms import Form, StringField


class _TestNotifier(Notifier):
    slug = "custom-test-notifier"
    name = "Custom Test Notifier"

    def __init__(self):
        self.sent_messages = []

    async def send(self, config, message):
        self.sent_messages.append({"config": config, "message": message})

    async def get_config_form(self):
        class F(Form):
            url = StringField("URL")

        return F


_test_notifier_instance = _TestNotifier()


class _TestNotifierPlugin:
    @staticmethod
    @hookimpl
    def datasette_alerts_register_notifiers(datasette):
        return [_test_notifier_instance]


# Only register if not already registered
try:
    _pm.register(_TestNotifierPlugin(), name="test-custom-notifier-plugin")
except ValueError:
    pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def datasette_instance(tmp_path):
    """Create a Datasette instance with datasette-cron scheduler."""
    data = str(tmp_path / "data.db")
    db = sqlite3.connect(data)
    with db:
        db.execute(
            """
            CREATE TABLE events (
                id INTEGER PRIMARY KEY,
                title TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        db.execute(
            "INSERT INTO events (title, created_at) VALUES ('Event 1', '2024-01-01 10:00:00')"
        )

    ds = Datasette(
        [data],
        config={
            "permissions": {
                "datasette-alerts-access": {"id": "*"},
            },
        },
    )
    # _get_alert_types uses datasette.plugin_manager
    ds.plugin_manager = _global_pm

    await ds.invoke_startup()
    return ds


@pytest_asyncio.fixture
async def internal_db(datasette_instance):
    return InternalDB(datasette_instance.get_internal_database())


# ---------------------------------------------------------------------------
# 1. Migration m004 - custom_config and last_check_at columns exist
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_migration_m004_columns_exist(datasette_instance):
    """After startup, the alerts table has custom_config and last_check_at columns."""
    idb = datasette_instance.get_internal_database()
    result = await idb.execute(
        "SELECT name FROM pragma_table_info('datasette_alerts_alerts')"
    )
    col_names = [row[0] for row in result.rows]
    assert "custom_config" in col_names
    assert "last_check_at" in col_names


# ---------------------------------------------------------------------------
# 2. Creating a custom alert via API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_custom_alert(datasette_instance, internal_db):
    """POST to api/new with alert_type='custom:test-type' creates the right DB row."""
    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier",
            label="Test Dest",
            config={"url": "https://example.com"},
        )
    )

    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    payload = {
        "database_name": "data",
        "table_name": "",
        "alert_type": "custom:test-type",
        "frequency": "+5 minutes",
        "custom_config": {"committee_id": "C001234", "threshold": 1000},
        "subscriptions": [
            {"destination_id": dest_id, "meta": {"aggregate": True}}
        ],
    }

    response = await datasette_instance.client.post(
        "/-/data/datasette-alerts/api/new", json=payload, cookies=cookies
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    alert_id = data["data"]["alert_id"]

    # Verify DB row
    idb = datasette_instance.get_internal_database()
    result = await idb.execute(
        "SELECT alert_type, custom_config, frequency FROM datasette_alerts_alerts WHERE id = ?",
        [alert_id],
    )
    row = dict(result.first())
    assert row["alert_type"] == "custom:test-type"
    assert json.loads(row["custom_config"]) == {
        "committee_id": "C001234",
        "threshold": 1000,
    }
    assert row["frequency"] == "+5 minutes"


# ---------------------------------------------------------------------------
# 3. Custom alert type registration - appears in api/alert-types
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_list_alert_types(datasette_instance):
    """Registered AlertType appears in the api/alert-types endpoint."""
    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    response = await datasette_instance.client.get(
        "/-/data/datasette-alerts/api/alert-types", cookies=cookies
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True

    slugs = [at["slug"] for at in data["data"]]
    assert "test-type" in slugs

    test_type = next(at for at in data["data"] if at["slug"] == "test-type")
    assert test_type["name"] == "Test Alert"
    assert test_type["description"] == "A test alert type"
    assert test_type["icon"] == "<svg/>"


# ---------------------------------------------------------------------------
# 4. custom_alert_handler - calls AlertType.check() and sends messages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_alert_handler_calls_check_and_sends(
    datasette_instance, internal_db
):
    """custom_alert_handler calls AlertType.check(), sends messages, updates last_check_at."""
    _mock_alert_type_instance.check_calls.clear()
    _test_notifier_instance.sent_messages.clear()

    # Create destination + alert + subscription
    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier",
            label="Handler Test",
            config={"url": "https://hook.example.com"},
        )
    )
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:test-type",
        frequency="+5 minutes",
        custom_config={"key": "value"},
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={})
        ],
    )
    alert_id = await internal_db.new_alert(params)

    # Invoke handler
    config = {"alert_id": alert_id, "type_slug": "test-type"}
    await custom_alert_handler(datasette_instance, config)

    # AlertType.check was called once
    assert len(_mock_alert_type_instance.check_calls) == 1
    call = _mock_alert_type_instance.check_calls[0]
    assert call["config"] == {"key": "value"}
    assert call["db"] == "data"
    assert call["last"] is None  # first check

    # Message was sent to notifier
    assert len(_test_notifier_instance.sent_messages) == 1
    assert _test_notifier_instance.sent_messages[0]["message"].text == "test alert fired"
    assert _test_notifier_instance.sent_messages[0]["config"] == {
        "url": "https://hook.example.com"
    }

    # last_check_at was updated
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert.last_check_at is not None


@pytest.mark.asyncio
async def test_custom_alert_handler_no_messages(datasette_instance, internal_db):
    """When check() returns an empty list, no messages are sent."""
    _test_notifier_instance.sent_messages.clear()

    # Use a special AlertType that returns no messages
    class EmptyAlertType(AlertType):
        slug = "empty-type"
        name = "Empty Alert"

        async def check(self, datasette, alert_config, database_name, last_check_at):
            return []

    empty_at = EmptyAlertType()

    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier", label="Empty Test", config={}
        )
    )
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:empty-type",
        frequency="+5 minutes",
        custom_config={},
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={})
        ],
    )
    alert_id = await internal_db.new_alert(params)

    # Patch _get_alert_types to return our empty type
    with patch(
        "datasette_alerts.handlers._get_alert_types",
        return_value={"empty-type": empty_at},
    ):
        await custom_alert_handler(
            datasette_instance, {"alert_id": alert_id, "type_slug": "empty-type"}
        )

    assert len(_test_notifier_instance.sent_messages) == 0


@pytest.mark.asyncio
async def test_custom_alert_handler_unknown_type(datasette_instance, internal_db):
    """Handler returns early for an unregistered alert type slug."""
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:unknown-slug",
        frequency="+5 minutes",
        custom_config={},
        subscriptions=[],
    )
    alert_id = await internal_db.new_alert(params)

    # Should not raise
    with patch(
        "datasette_alerts.handlers._get_alert_types", return_value={}
    ):
        await custom_alert_handler(
            datasette_instance,
            {"alert_id": alert_id, "type_slug": "unknown-slug"},
        )


@pytest.mark.asyncio
async def test_custom_alert_handler_nonexistent_alert(datasette_instance):
    """Handler returns early when alert_id doesn't exist."""
    await custom_alert_handler(
        datasette_instance,
        {"alert_id": "nonexistent", "type_slug": "test-type"},
    )
    # No exception means success


# ---------------------------------------------------------------------------
# 5. get_all_alerts() - returns alerts including custom ones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_alerts_includes_custom(datasette_instance, internal_db):
    """get_all_alerts returns custom alerts with correct fields."""
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:test-type",
        frequency="+10 minutes",
        custom_config={"foo": "bar"},
        subscriptions=[],
    )
    alert_id = await internal_db.new_alert(params)

    alerts = await internal_db.get_all_alerts()
    custom_alerts = [a for a in alerts if a.id == alert_id]
    assert len(custom_alerts) == 1

    alert = custom_alerts[0]
    assert alert.alert_type == "custom:test-type"
    assert json.loads(alert.custom_config) == {"foo": "bar"}
    assert alert.frequency == "+10 minutes"
    assert alert.database_name == "data"


# ---------------------------------------------------------------------------
# 6. get_alert_for_check() - returns alert with custom_config and last_check_at
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_alert_for_check_custom(datasette_instance, internal_db):
    """get_alert_for_check returns custom_config and last_check_at for a custom alert."""
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:test-type",
        frequency="+5 minutes",
        custom_config={"threshold": 42},
        subscriptions=[],
    )
    alert_id = await internal_db.new_alert(params)

    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert is not None
    assert alert.id == alert_id
    assert alert.alert_type == "custom:test-type"
    assert json.loads(alert.custom_config) == {"threshold": 42}
    assert alert.last_check_at is None
    assert alert.database_name == "data"
    assert alert.cursor == ""  # no log entries with cursor


@pytest.mark.asyncio
async def test_get_alert_for_check_nonexistent(internal_db):
    """get_alert_for_check returns None for nonexistent alert."""
    result = await internal_db.get_alert_for_check("nonexistent-id")
    assert result is None


# ---------------------------------------------------------------------------
# 7. update_last_check() - sets last_check_at to now
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_last_check(datasette_instance, internal_db):
    """update_last_check sets last_check_at to the current timestamp."""
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:test-type",
        frequency="+5 minutes",
        custom_config={},
        subscriptions=[],
    )
    alert_id = await internal_db.new_alert(params)

    # Initially None
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert.last_check_at is None

    # Update
    await internal_db.update_last_check(alert_id)

    # Now set
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert.last_check_at is not None
    # Should be a valid ISO-ish datetime string
    assert "20" in alert.last_check_at  # starts with year 20xx


# ---------------------------------------------------------------------------
# 8. Deleting a custom alert - row removed from DB
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_custom_alert_db(datasette_instance, internal_db):
    """Deleting a custom alert removes it from the database."""
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="custom-test-notifier", label="Del Test", config={})
    )
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:test-type",
        frequency="+5 minutes",
        custom_config={"x": 1},
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={})
        ],
    )
    alert_id = await internal_db.new_alert(params)

    # Verify it exists
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert is not None

    # Delete
    info = await internal_db.delete_alert(alert_id)
    assert info is not None
    assert info.alert_type == "custom:test-type"

    # Verify gone
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert is None

    # Subscriptions also gone
    idb = datasette_instance.get_internal_database()
    subs = await idb.execute(
        "SELECT COUNT(*) FROM datasette_alerts_subscriptions WHERE alert_id = ?",
        [alert_id],
    )
    assert subs.rows[0][0] == 0


@pytest.mark.asyncio
async def test_api_delete_custom_alert(datasette_instance, internal_db):
    """API delete endpoint removes custom alert and its cron task."""
    scheduler = datasette_instance._cron_scheduler

    # Create alert via API so cron task is registered automatically
    dest_id = await internal_db.create_destination(
        NewDestination(notifier="custom-test-notifier", label="Del API", config={})
    )
    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    create_response = await datasette_instance.client.post(
        "/-/data/datasette-alerts/api/new",
        json={
            "database_name": "data",
            "table_name": "",
            "alert_type": "custom:test-type",
            "frequency": "+5 minutes",
            "custom_config": {},
            "subscriptions": [{"destination_id": dest_id, "meta": {}}],
        },
        cookies=cookies,
    )
    assert create_response.status_code == 200
    alert_id = create_response.json()["data"]["alert_id"]

    # Verify cron task exists
    task = await scheduler.internal_db.get_task(f"alerts:custom:{alert_id}")
    assert task is not None

    # Delete
    response = await datasette_instance.client.post(
        f"/-/data/datasette-alerts/api/alerts/{alert_id}/delete",
        json={},
        cookies=cookies,
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True

    # Verify alert gone from DB
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert is None

    # Verify cron task removed
    task = await scheduler.internal_db.get_task(f"alerts:custom:{alert_id}")
    assert task is None


@pytest.mark.asyncio
async def test_delete_alert_not_found(datasette_instance):
    """Deleting a nonexistent alert returns 404."""
    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    response = await datasette_instance.client.post(
        "/-/data/datasette-alerts/api/alerts/nonexistent/delete",
        json={},
        cookies=cookies,
    )
    assert response.status_code == 404
    assert response.json()["ok"] is False


# ---------------------------------------------------------------------------
# 9. _frequency_to_interval() - conversion tests
# ---------------------------------------------------------------------------


def test_frequency_to_interval_minutes():
    assert _frequency_to_interval("+5 minutes") == {"interval": 300}


def test_frequency_to_interval_single_minute():
    assert _frequency_to_interval("+1 minute") == {"interval": 60}


def test_frequency_to_interval_hour():
    assert _frequency_to_interval("+1 hour") == {"interval": 3600}


def test_frequency_to_interval_hours():
    assert _frequency_to_interval("+2 hours") == {"interval": 7200}


def test_frequency_to_interval_seconds():
    assert _frequency_to_interval("+30 seconds") == {"interval": 30}


def test_frequency_to_interval_single_second():
    assert _frequency_to_interval("+1 second") == {"interval": 1}


def test_frequency_to_interval_day():
    assert _frequency_to_interval("+1 day") == {"interval": 86400}


def test_frequency_to_interval_days():
    assert _frequency_to_interval("+7 days") == {"interval": 604800}


def test_frequency_to_interval_no_plus():
    """Should handle frequency strings without leading +."""
    assert _frequency_to_interval("5 minutes") == {"interval": 300}


def test_frequency_to_interval_extra_whitespace():
    assert _frequency_to_interval("  +10 minutes  ") == {"interval": 600}


# ---------------------------------------------------------------------------
# 10. Cron task registration on alert create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cron_task_registered_on_custom_alert_create(
    datasette_instance, internal_db
):
    """Creating a custom alert via API registers a cron task with the scheduler."""
    scheduler = datasette_instance._cron_scheduler

    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier",
            label="Cron Test",
            config={"url": "https://cron.example.com"},
        )
    )

    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    payload = {
        "database_name": "data",
        "table_name": "",
        "alert_type": "custom:test-type",
        "frequency": "+5 minutes",
        "custom_config": {"key": "val"},
        "subscriptions": [
            {"destination_id": dest_id, "meta": {}}
        ],
    }

    response = await datasette_instance.client.post(
        "/-/data/datasette-alerts/api/new", json=payload, cookies=cookies
    )
    assert response.status_code == 200
    alert_id = response.json()["data"]["alert_id"]

    # Verify cron task was registered
    task_name = f"alerts:custom:{alert_id}"
    task = await scheduler.internal_db.get_task(task_name)
    assert task is not None
    assert task.handler == "alerts:custom-check"
    task_config = json.loads(task.config) if isinstance(task.config, str) else task.config
    assert task_config == {"alert_id": alert_id, "type_slug": "test-type"}
    assert task.overlap_policy == "skip"


@pytest.mark.asyncio
async def test_cron_task_registered_for_cursor_alert(
    datasette_instance, internal_db
):
    """Creating a cursor alert via API registers a cron task."""
    scheduler = datasette_instance._cron_scheduler

    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    payload = {
        "database_name": "data",
        "table_name": "events",
        "alert_type": "cursor",
        "id_columns": ["id"],
        "timestamp_column": "created_at",
        "frequency": "+1 hour",
        "subscriptions": [],
    }

    response = await datasette_instance.client.post(
        "/-/data/datasette-alerts/api/new", json=payload, cookies=cookies
    )
    assert response.status_code == 200
    alert_id = response.json()["data"]["alert_id"]

    task_name = f"alerts:cursor:{alert_id}"
    task = await scheduler.internal_db.get_task(task_name)
    assert task is not None
    assert task.handler == "alerts:cursor-check"
    task_config = json.loads(task.config) if isinstance(task.config, str) else task.config
    assert task_config == {"alert_id": alert_id}


# ---------------------------------------------------------------------------
# Extra: _get_alert_types helper
# ---------------------------------------------------------------------------


def test_get_alert_types_returns_registered(datasette_instance):
    """_get_alert_types returns our mock AlertType registered via hook."""
    alert_types = _get_alert_types(datasette_instance)
    assert "test-type" in alert_types
    assert alert_types["test-type"].name == "Test Alert"


# ---------------------------------------------------------------------------
# Extra: cron sync on startup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_alerts_to_cron_on_startup(tmp_path):
    """_sync_alerts_to_cron registers existing alerts as cron tasks during startup."""
    data = str(tmp_path / "data2.db")
    db = sqlite3.connect(data)
    with db:
        db.execute(
            "CREATE TABLE t (id INTEGER PRIMARY KEY, ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
        )

    ds = Datasette(
        [data],
        config={
            "permissions": {"datasette-alerts-access": {"id": "*"}},
        },
    )
    ds.plugin_manager = _global_pm

    await ds.invoke_startup()

    scheduler = ds._cron_scheduler

    # Insert an alert directly into the internal DB
    idb = InternalDB(ds.get_internal_database())
    params = NewAlertRouteParameters(
        database_name="data2",
        table_name="",
        alert_type="custom:test-type",
        frequency="+15 minutes",
        custom_config={"a": 1},
        subscriptions=[],
    )
    alert_id = await idb.new_alert(params)

    # Re-run sync
    from datasette_alerts import _sync_alerts_to_cron

    await _sync_alerts_to_cron(ds)

    task = await scheduler.internal_db.get_task(f"alerts:custom:{alert_id}")
    assert task is not None
    assert task.handler == "alerts:custom-check"


# ---------------------------------------------------------------------------
# Extra: handler passes last_check_at on second call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handler_passes_last_check_at_on_second_call(
    datasette_instance, internal_db
):
    """On the second invocation, last_check_at is set from the first call."""
    _mock_alert_type_instance.check_calls.clear()
    _test_notifier_instance.sent_messages.clear()

    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier", label="2nd call", config={}
        )
    )
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:test-type",
        frequency="+5 minutes",
        custom_config={"repeat": True},
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={})
        ],
    )
    alert_id = await internal_db.new_alert(params)

    handler_config = {"alert_id": alert_id, "type_slug": "test-type"}

    # First call
    await custom_alert_handler(datasette_instance, handler_config)
    assert _mock_alert_type_instance.check_calls[-1]["last"] is None

    # Second call
    await custom_alert_handler(datasette_instance, handler_config)
    assert _mock_alert_type_instance.check_calls[-1]["last"] is not None


# ---------------------------------------------------------------------------
# Extra: custom alert new_alert stores custom_config as JSON
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_alert_custom_config_stored_as_json(internal_db):
    """InternalDB.new_alert stores custom_config as valid JSON in the DB."""
    config = {"nested": {"list": [1, 2, 3]}, "flag": True}
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="my_table",
        alert_type="custom:test-type",
        frequency="+5 minutes",
        custom_config=config,
        subscriptions=[],
    )
    alert_id = await internal_db.new_alert(params)

    alert = await internal_db.get_alert_for_check(alert_id)
    parsed = json.loads(alert.custom_config)
    assert parsed == config


# ---------------------------------------------------------------------------
# Bug-guard tests: solidify critical patterns
# ---------------------------------------------------------------------------


def test_frequency_one_second_converts_correctly():
    """_frequency_to_interval('+1 second') must return {'interval': 1}."""
    result = _frequency_to_interval("+1 second")
    assert result == {"interval": 1}, f"Expected {{'interval': 1}}, got {result}"


@pytest.mark.asyncio
async def test_handler_updates_last_check_even_when_no_messages(
    datasette_instance, internal_db
):
    """custom_alert_handler must update last_check_at even when check() returns []."""

    class NoMessageAlertType(AlertType):
        slug = "no-msg-type"
        name = "No Message Alert"

        async def check(self, datasette, alert_config, database_name, last_check_at):
            return []

    no_msg_at = NoMessageAlertType()

    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier", label="No Msg Test", config={}
        )
    )
    params = NewAlertRouteParameters(
        database_name="data",
        table_name="",
        alert_type="custom:no-msg-type",
        frequency="+5 minutes",
        custom_config={},
        subscriptions=[
            NewSubscription(destination_id=dest_id, meta={})
        ],
    )
    alert_id = await internal_db.new_alert(params)

    # Verify last_check_at starts as None
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert.last_check_at is None

    # Run handler with empty check result
    with patch(
        "datasette_alerts.handlers._get_alert_types",
        return_value={"no-msg-type": no_msg_at},
    ):
        await custom_alert_handler(
            datasette_instance,
            {"alert_id": alert_id, "type_slug": "no-msg-type"},
        )

    # last_check_at MUST be updated even though no messages were produced
    alert = await internal_db.get_alert_for_check(alert_id)
    assert alert.last_check_at is not None, (
        "last_check_at was not updated when check() returned empty list"
    )


@pytest.mark.asyncio
async def test_cron_task_uses_correct_handler_name(datasette_instance, internal_db):
    """Cron task for custom alert must use 'alerts:custom-check' handler name."""
    scheduler = datasette_instance._cron_scheduler

    dest_id = await internal_db.create_destination(
        NewDestination(
            notifier="custom-test-notifier",
            label="Handler Name Test",
            config={},
        )
    )
    cookies = {
        "ds_actor": datasette_instance.sign({"a": {"id": "root"}}, "actor")
    }
    response = await datasette_instance.client.post(
        "/-/data/datasette-alerts/api/new",
        json={
            "database_name": "data",
            "table_name": "",
            "alert_type": "custom:test-type",
            "frequency": "+5 minutes",
            "custom_config": {},
            "subscriptions": [{"destination_id": dest_id, "meta": {}}],
        },
        cookies=cookies,
    )
    assert response.status_code == 200
    alert_id = response.json()["data"]["alert_id"]

    task = await scheduler.internal_db.get_task(f"alerts:custom:{alert_id}")
    assert task is not None

    # Must be "alerts:custom-check", NOT "datasette-alerts:custom-check"
    assert task.handler == "alerts:custom-check", (
        f"Expected handler 'alerts:custom-check', got '{task['handler']}'"
    )


@pytest.mark.asyncio
async def test_get_alert_types_uses_global_pm(tmp_path):
    """_get_alert_types must work without datasette.plugin_manager attribute.

    It must use `from datasette.plugins import pm` (global plugin manager),
    NOT `datasette.plugin_manager`.
    """
    data = str(tmp_path / "data_pm_test.db")
    db = sqlite3.connect(data)
    with db:
        db.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

    ds = Datasette(
        [data],
        config={"permissions": {"datasette-alerts-access": {"id": "*"}}},
    )
    await ds.invoke_startup()

    # Explicitly remove plugin_manager attribute if it exists,
    # to prove _get_alert_types does NOT depend on it.
    if hasattr(ds, "plugin_manager"):
        delattr(ds, "plugin_manager")
    assert not hasattr(ds, "plugin_manager")

    # _get_alert_types should still work via the global pm
    alert_types = _get_alert_types(ds)
    assert "test-type" in alert_types, (
        "_get_alert_types failed when datasette.plugin_manager is absent; "
        "it must use `from datasette.plugins import pm`"
    )
