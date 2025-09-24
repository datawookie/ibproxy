from datetime import datetime

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str


class SystemStatus(BaseModel):
    label: str
    colour: str


class Uptime(BaseModel):
    started: datetime = Field(..., description="The UTC timestamp when the server started.")
    uptime_seconds: float = Field(..., description="The number of seconds since the server started.")
    uptime_human: str = Field(..., description="Human-readable uptime string.")
