from pydantic import BaseModel


class Health(BaseModel):
    status: str


class SystemStatus(BaseModel):
    label: str
    colour: str
