from typing import Annotated

from pydantic import BaseModel
from datasette import Response
from datasette_plugin_router import Body

from .internal_db import InternalDB, NewAlertRouteParameters
from .page_data import AlertInfo, AlertsListPageData, NewAlertPageData, NewAlertResponse, NotifierConfigField, NotifierInfo
from .router import router, check_permission
from .bg_task import get_notifiers


async def render_page(
    datasette, request, *, page_title: str, entrypoint: str, page_data: BaseModel
) -> Response:
    return Response.html(
        await datasette.render_template(
            "alerts_base.html",
            {
                "page_title": page_title,
                "entrypoint": entrypoint,
                "page_data": page_data.model_dump(),
            },
            request=request,
        )
    )


def extract_config_fields(form_class) -> list[NotifierConfigField]:
    """Extract field metadata from a WTForms Form class."""
    form = form_class()
    fields = []
    for field in form:
        render_kw = field.render_kw or {}
        fields.append(
            NotifierConfigField(
                name=field.name,
                label=str(field.label.text) if field.label else field.name,
                field_type="text",
                placeholder=render_kw.get("placeholder", ""),
                description=field.description or "",
                default=str(field.default) if field.default else "",
            )
        )
    return fields


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
    )


@router.GET("/-/datasette-alerts/new-alert$")
@check_permission()
async def ui_new_alert(datasette, request):
    notifiers = await get_notifiers(datasette)
    notifier_infos = []
    for n in notifiers:
        config_fields = []
        try:
            form_class = await n.get_config_form()
            config_fields = extract_config_fields(form_class)
        except NotImplementedError:
            pass
        notifier_infos.append(
            NotifierInfo(
                slug=n.slug,
                name=n.name,
                icon=n.icon,
                description=n.description,
                config_fields=config_fields,
            )
        )
    return await render_page(
        datasette,
        request,
        page_title="Create Alert",
        entrypoint="src/pages/new_alert/index.ts",
        page_data=NewAlertPageData(notifiers=notifier_infos),
    )


@router.POST("/-/datasette-alerts/api/new-alert$", output=NewAlertResponse)
@check_permission()
async def api_new_alert(
    datasette, request, body: Annotated[NewAlertRouteParameters, Body()]
):
    db = datasette.databases.get(body.database_name)
    if db is None:
        return Response.json(
            {"ok": False, "error": f"Database {body.database_name} not found"},
            status=404,
        )

    internal_db = InternalDB(datasette.get_internal_database())

    result = await db.execute(
        f"select max({body.timestamp_column}) from {body.table_name}"
    )
    initial_cursor = result.rows[0][0]
    alert_id = await internal_db.new_alert(body, initial_cursor)
    return Response.json({"ok": True, "data": {"alert_id": alert_id}})
