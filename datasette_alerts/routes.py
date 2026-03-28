from typing import Annotated

from pydantic import BaseModel
from datasette import Response
from datasette_plugin_router import Body

from .internal_db import InternalDB, NewAlertRouteParameters, NewDestination
from .page_data import AlertDetailPageData, AlertInfo, AlertsListPageData, DestinationInfo, DestinationsPageData, NewAlertPageData, NewAlertResponse, NotifierConfigField, NotifierInfo
from .router import router, check_permission
from .destinations import get_notifiers
from .trigger_db import create_queue_and_trigger, drop_queue_and_trigger


async def render_page(
    datasette, request, *, page_title: str, entrypoint: str, page_data: BaseModel,
    breadcrumbs: list[dict] | None = None,
) -> Response:
    return Response.html(
        await datasette.render_template(
            "alerts_base.html",
            {
                "page_title": page_title,
                "entrypoint": entrypoint,
                "page_data": page_data.model_dump(),
                "breadcrumbs": breadcrumbs or [],
            },
            request=request,
        )
    )


def extract_config_fields(form_class) -> list[NotifierConfigField]:
    """Extract field metadata from a WTForms Form class."""
    from wtforms import BooleanField

    form = form_class()
    fields = []
    for field in form:
        render_kw = field.render_kw or {}

        # Determine field_type: explicit render_kw override, BooleanField detection, or default "text"
        if "field_type" in render_kw:
            field_type = render_kw["field_type"]
        elif isinstance(field, BooleanField):
            field_type = "boolean"
        else:
            field_type = "text"

        fields.append(
            NotifierConfigField(
                name=field.name,
                label=str(field.label.text) if field.label else field.name,
                field_type=field_type,
                placeholder=render_kw.get("placeholder", ""),
                description=field.description or "",
                default=str(field.default) if field.default else "",
                metadata=render_kw.get("metadata", {}),
            )
        )
    return fields


async def _build_notifier_infos(datasette) -> list[NotifierInfo]:
    """Build NotifierInfo list from registered notifiers."""
    notifiers = await get_notifiers(datasette)
    infos = []
    for n in notifiers:
        config_fields = []
        try:
            form_class = await n.get_config_form()
            config_fields = extract_config_fields(form_class)
        except NotImplementedError:
            pass
        infos.append(
            NotifierInfo(
                slug=n.slug,
                name=n.name,
                icon=n.icon,
                description=n.description,
                config_fields=config_fields,
            )
        )
    return infos


async def _build_destination_infos(internal_db: InternalDB) -> list[DestinationInfo]:
    """Build DestinationInfo list from stored destinations."""
    dests = await internal_db.list_destinations()
    return [
        DestinationInfo(
            id=d.id, notifier=d.notifier, label=d.label,
            config=d.config, created_at=d.created_at,
        )
        for d in dests
    ]


def _base_crumbs(datasette, db_name: str) -> list[dict]:
    return [
        {"href": datasette.urls.instance(), "label": "home"},
        {"href": datasette.urls.database(db_name), "label": db_name},
    ]


def _alerts_crumbs(datasette, db_name: str) -> list[dict]:
    return _base_crumbs(datasette, db_name) + [
        {"href": datasette.urls.path(f"-/{db_name}/datasette-alerts"), "label": "Alerts"},
    ]


@router.GET(r"/-/(?P<db_name>[^/]+)/datasette-alerts$")
@check_permission()
async def ui_alerts_list(datasette, request, db_name: str):
    db = datasette.databases.get(db_name)
    if db is None:
        return Response.html("Database not found", status=404)

    internal_db = InternalDB(datasette.get_internal_database())
    rows = await internal_db.list_alerts_for_database(db_name)
    alerts = [AlertInfo(**row) for row in rows]

    return await render_page(
        datasette,
        request,
        page_title=f"Alerts — {db_name}",
        entrypoint="src/pages/alerts_list/index.ts",
        page_data=AlertsListPageData(database_name=db_name, alerts=alerts),
        breadcrumbs=_alerts_crumbs(datasette, db_name),
    )


@router.GET(r"/-/(?P<db_name>[^/]+)/datasette-alerts/alerts/(?P<alert_id>[^/]+)$")
@check_permission()
async def ui_alert_detail(datasette, request, db_name: str, alert_id: str):
    db = datasette.databases.get(db_name)
    if db is None:
        return Response.html("Database not found", status=404)

    internal_db = InternalDB(datasette.get_internal_database())
    detail = await internal_db.get_alert_detail(alert_id)
    if detail is None:
        return Response.html("Alert not found", status=404)

    notifier_infos = await _build_notifier_infos(datasette)
    destination_infos = await _build_destination_infos(internal_db)

    return await render_page(
        datasette,
        request,
        page_title=f"Alert — {detail['table_name']}",
        entrypoint="src/pages/alert_detail/index.ts",
        page_data=AlertDetailPageData(**detail, notifiers=notifier_infos, destinations=destination_infos),
        breadcrumbs=_alerts_crumbs(datasette, db_name) + [
            {"href": datasette.urls.path(f"-/{db_name}/datasette-alerts/alerts/{alert_id}"), "label": detail["table_name"]},
        ],
    )


@router.GET(r"/-/(?P<db_name>[^/]+)/datasette-alerts/new$")
@check_permission()
async def ui_new_alert(datasette, request, db_name: str):
    db = datasette.databases.get(db_name)
    if db is None:
        return Response.html("Database not found", status=404)

    internal_db = InternalDB(datasette.get_internal_database())
    notifier_infos = await _build_notifier_infos(datasette)
    destination_infos = await _build_destination_infos(internal_db)

    # Extract filter params from URL (non-_ params, or params with __ in them)
    filter_params = []
    for key in request.args:
        if key.startswith("_") and "__" not in key:
            continue
        if key in ("table_name", "alert_type"):
            continue
        for v in request.args.getlist(key):
            filter_params.append([key, v])

    return await render_page(
        datasette,
        request,
        page_title="Create Alert",
        entrypoint="src/pages/new_alert/index.ts",
        page_data=NewAlertPageData(
            database_name=db_name,
            notifiers=notifier_infos,
            destinations=destination_infos,
            filter_params=filter_params,
        ),
        breadcrumbs=_alerts_crumbs(datasette, db_name) + [
            {"href": datasette.urls.path(f"-/{db_name}/datasette-alerts/new"), "label": "New Alert"},
        ],
    )


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/new$", output=NewAlertResponse)
@check_permission()
async def api_new_alert(
    datasette, request, db_name: str, body: Annotated[NewAlertRouteParameters, Body()]
):
    db = datasette.databases.get(db_name)
    if db is None:
        return Response.json(
            {"ok": False, "error": f"Database {db_name} not found"},
            status=404,
        )

    body.database_name = db_name
    internal_db = InternalDB(datasette.get_internal_database())

    if body.alert_type == "trigger":
        # Auto-detect PK columns from table schema
        result = await db.execute(
            f"select name from pragma_table_info('{body.table_name}') where pk > 0 order by pk"
        )
        pk_columns = [row[0] for row in result.rows]
        if not pk_columns:
            pk_columns = ["rowid"]
        body.id_columns = pk_columns

        alert_id = await internal_db.new_alert(body)
        await create_queue_and_trigger(
            db, alert_id, body.table_name, pk_columns, body.filter_params
        )
    else:
        result = await db.execute(
            f"select max({body.timestamp_column}) from {body.table_name}"
        )
        initial_cursor = result.rows[0][0]
        alert_id = await internal_db.new_alert(body, initial_cursor)

    return Response.json({"ok": True, "data": {"alert_id": alert_id}})


class AddSubscriptionBody(BaseModel):
    destination_id: str
    meta: dict = {}


class UpdateSubscriptionBody(BaseModel):
    meta: dict = {}


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/alerts/(?P<alert_id>[^/]+)/subscriptions$")
@check_permission()
async def api_add_subscription(
    datasette, request, db_name: str, alert_id: str, body: Annotated[AddSubscriptionBody, Body()]
):
    internal_db = InternalDB(datasette.get_internal_database())
    detail = await internal_db.get_alert_detail(alert_id)
    if detail is None:
        return Response.json({"ok": False, "error": "Alert not found"}, status=404)
    sub_id = await internal_db.add_subscription(alert_id, body.destination_id, body.meta)
    return Response.json({"ok": True, "data": {"subscription_id": sub_id}})


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/alerts/(?P<alert_id>[^/]+)/subscriptions/(?P<sub_id>[^/]+)/update$")
@check_permission()
async def api_update_subscription(
    datasette, request, db_name: str, alert_id: str, sub_id: str, body: Annotated[UpdateSubscriptionBody, Body()]
):
    internal_db = InternalDB(datasette.get_internal_database())
    await internal_db.update_subscription(sub_id, body.meta)
    return Response.json({"ok": True})


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/alerts/(?P<alert_id>[^/]+)/subscriptions/(?P<sub_id>[^/]+)/delete$")
@check_permission()
async def api_delete_subscription(
    datasette, request, db_name: str, alert_id: str, sub_id: str
):
    internal_db = InternalDB(datasette.get_internal_database())
    await internal_db.delete_subscription(sub_id)
    return Response.json({"ok": True})


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/alerts/(?P<alert_id>[^/]+)/delete$")
@check_permission()
async def api_delete_alert(datasette, request, db_name: str, alert_id: str):
    internal_db = InternalDB(datasette.get_internal_database())
    info = await internal_db.delete_alert(alert_id)
    if info is None:
        return Response.json({"ok": False, "error": "Alert not found"}, status=404)

    # Drop queue table and trigger if this was a trigger alert
    if info["alert_type"] == "trigger":
        db = datasette.databases.get(info["database_name"])
        if db is not None:
            try:
                await drop_queue_and_trigger(db, alert_id, info["table_name"])
            except Exception:
                pass  # Queue/trigger may already be gone

    return Response.json({"ok": True})


# --- Destination routes ---


@router.GET(r"/-/(?P<db_name>[^/]+)/datasette-alerts/destinations$")
@check_permission()
async def ui_destinations_list(datasette, request, db_name: str):
    db = datasette.databases.get(db_name)
    if db is None:
        return Response.html("Database not found", status=404)

    internal_db = InternalDB(datasette.get_internal_database())
    notifier_infos = await _build_notifier_infos(datasette)
    destination_infos = await _build_destination_infos(internal_db)

    return await render_page(
        datasette,
        request,
        page_title=f"Destinations — {db_name}",
        entrypoint="src/pages/destinations/index.ts",
        page_data=DestinationsPageData(
            database_name=db_name,
            destinations=destination_infos,
            notifiers=notifier_infos,
        ),
        breadcrumbs=_alerts_crumbs(datasette, db_name) + [
            {"href": datasette.urls.path(f"-/{db_name}/datasette-alerts/destinations"), "label": "Destinations"},
        ],
    )


class NewDestinationBody(BaseModel):
    notifier: str
    label: str
    config: dict = {}


class UpdateDestinationBody(BaseModel):
    label: str
    config: dict = {}


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/destinations/new$")
@check_permission()
async def api_new_destination(
    datasette, request, db_name: str, body: Annotated[NewDestinationBody, Body()]
):
    internal_db = InternalDB(datasette.get_internal_database())
    created_by = request.actor.get("id") if request.actor else None
    dest_id = await internal_db.create_destination(
        NewDestination(notifier=body.notifier, label=body.label, config=body.config),
        created_by=created_by,
    )
    return Response.json({"ok": True, "data": {"destination_id": dest_id}})


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/destinations/(?P<dest_id>[^/]+)/update$")
@check_permission()
async def api_update_destination(
    datasette, request, db_name: str, dest_id: str, body: Annotated[UpdateDestinationBody, Body()]
):
    internal_db = InternalDB(datasette.get_internal_database())
    dest = await internal_db.get_destination(dest_id)
    if dest is None:
        return Response.json({"ok": False, "error": "Destination not found"}, status=404)
    await internal_db.update_destination(dest_id, body.label, body.config)
    return Response.json({"ok": True})


@router.POST(r"/-/(?P<db_name>[^/]+)/datasette-alerts/api/destinations/(?P<dest_id>[^/]+)/delete$")
@check_permission()
async def api_delete_destination(
    datasette, request, db_name: str, dest_id: str
):
    internal_db = InternalDB(datasette.get_internal_database())
    dest = await internal_db.get_destination(dest_id)
    if dest is None:
        return Response.json({"ok": False, "error": "Destination not found"}, status=404)
    await internal_db.delete_destination(dest_id)
    return Response.json({"ok": True})
