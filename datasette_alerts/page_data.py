from pydantic import BaseModel


class NotifierInfo(BaseModel):
    slug: str
    name: str
    icon: str = ""
    description: str = ""


# /-/datasette-alerts/new-alert — form to create a new alert
class NewAlertPageData(BaseModel):
    notifiers: list[NotifierInfo] = []


__exports__ = [NewAlertPageData]
