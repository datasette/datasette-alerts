from pydantic import BaseModel


class NotifierConfigField(BaseModel):
    name: str
    label: str
    field_type: str = "text"
    placeholder: str = ""
    description: str = ""
    default: str = ""


class NotifierInfo(BaseModel):
    slug: str
    name: str
    icon: str = ""
    description: str = ""
    config_fields: list[NotifierConfigField] = []


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
