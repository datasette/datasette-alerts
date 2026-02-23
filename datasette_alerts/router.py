from functools import wraps

from datasette import Forbidden
from datasette_plugin_router import Router

router = Router()

ALERTS_ACCESS_NAME = "datasette-alerts-access"


def check_permission():
    """Decorator for routes requiring alerts access."""

    def decorator(func):
        @wraps(func)
        async def wrapper(datasette, request, **kwargs):
            result = await datasette.allowed(
                action=ALERTS_ACCESS_NAME, actor=request.actor
            )
            if not result:
                raise Forbidden("Permission denied for datasette-alerts access")
            return await func(datasette=datasette, request=request, **kwargs)

        return wrapper

    return decorator
