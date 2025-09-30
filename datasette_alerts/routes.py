from .internal_db import InternalDB, NewAlertRouteParameters
from datasette import Response
from .bg_task import get_notifiers


async def api_new_alert(scope, receive, datasette, request):
    if request.method != "POST":
        return Response.text("", status=405)
    try:
        params: NewAlertRouteParameters = (
            NewAlertRouteParameters.model_validate_json(await request.post_body())
        )
    except ValueError:
        return Response.json({"ok": False}, status=400)

    db = datasette.databases.get(params.database_name)
    if db is None:
        return Response.json(
            {"ok": False, "error": f"Database {params.database_name} not found"},
            status=404,
        )
    
    internal_db = InternalDB(datasette.get_internal_database())

    result = await db.execute(f'select max({params.timestamp_column}) from {params.table_name}')
    initial_cursor = result.rows[0][0]
    alert_id = await internal_db.new_alert(params, initial_cursor)
    return Response.json({"ok": True, "data": {"alert_id": alert_id}})


async def ui_new_alert(scope, receive, datasette, request):
    notifiers = await get_notifiers(datasette)
    forms = []
    data = []
    for notifier in notifiers:
        c = await notifier.get_config_form()
        forms.append(
            {
                "html": c(prefix=f"{notifier.slug}-"),
                "slug": notifier.slug,
                "icon": notifier.icon,
                "name": notifier.name,
            }
        )
        data.append(
            {
                "slug": notifier.slug,
                "icon": notifier.icon,
                "name": notifier.name,
            }
        )
    return Response.html(
        await datasette.render_template(
            "tmp.html",
            {"forms": forms, "data": data},
        )
    )