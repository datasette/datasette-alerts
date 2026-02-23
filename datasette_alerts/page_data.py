from pydantic import BaseModel


class NotifierInfo(BaseModel):
    slug: str
    name: str
    icon: str = ""
    description: str = ""


# /-/datasette-alerts/new-alert — form to create a new alert
class NewAlertPageData(BaseModel):
    notifiers: list[NotifierInfo] = []


class NewAlertResponseData(BaseModel):
    alert_id: str


class NewAlertResponse(BaseModel):
    ok: bool
    data: NewAlertResponseData | None = None
    error: str | None = None


__exports__ = [NewAlertPageData]
