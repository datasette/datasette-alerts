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


class AlertInfo(BaseModel):
    id: str
    database_name: str
    table_name: str
    frequency: str
    next_deadline: str | None = None
    seconds_until_next: int | None = None
    alert_created_at: str | None = None
    notifiers: str = ""
    last_notification_at: str | None = None


# /-/{db_name}/datasette-alerts — list of alerts for a database
class AlertsListPageData(BaseModel):
    database_name: str
    alerts: list[AlertInfo] = []


__exports__ = [NewAlertPageData, AlertsListPageData]
