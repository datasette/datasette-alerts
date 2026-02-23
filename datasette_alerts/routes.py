from typing import Annotated

from pydantic import BaseModel
from datasette import Response
from datasette_plugin_router import Body

from .internal_db import InternalDB, NewAlertRouteParameters
from .page_data import NewAlertPageData, NotifierInfo
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


@router.GET("/-/datasette-alerts/new-alert$")
@check_permission()
async def ui_new_alert(datasette, request):
    notifiers = await get_notifiers(datasette)
    return await render_page(
        datasette,
        request,
        page_title="Create Alert",
        entrypoint="src/pages/new_alert/index.ts",
        page_data=NewAlertPageData(
            notifiers=[
                NotifierInfo(
                    slug=n.slug,
                    name=n.name,
                    icon=n.icon,
                    description=n.description,
                )
                for n in notifiers
            ],
        ),
    )


@router.POST("/-/datasette-alerts/api/new-alert$")
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
