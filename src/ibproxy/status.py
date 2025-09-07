import re

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter

from .const import STATUS_URL
from .models import SystemStatus

router = APIRouter()

STATUS_COLOURS = {
    "#cc3333": SystemStatus(label="Problem / Outage", colour="🟥"),
    "#ffcc00": SystemStatus(label="Scheduled Maintenance", colour="🟧"),
    "#99cccc": SystemStatus(label="General Information", colour="🟦"),
    "#66cc33": SystemStatus(label="Normal Operations", colour="🟩"),
    "#999999": SystemStatus(label="Resolved", colour="⬜"),
}


async def get_system_status() -> SystemStatus:
    async with httpx.AsyncClient() as client:
        response = await client.get(STATUS_URL)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Get system availability table.
    availability = soup.find("td", string=re.compile("System Availability")).parent.parent

    colour = availability.select_one("tr.odd > td.centeritem[style]")["style"].split(":")[-1].strip()

    return STATUS_COLOURS[colour]


@router.get(
    "",
    summary="IBKR System Status",
    description=f"Retrieve the status of the IBKR system from {STATUS_URL}.",
    response_model=SystemStatus,
    responses={
        200: {
            "description": "Status successfully found",
            "content": {
                "application/json": {
                    "examples": {
                        "problem": {
                            "summary": "Problem / Outage",
                            "description": "There is an outage affecting the service.",
                            "value": STATUS_COLOURS["#cc3333"],
                        },
                        "maintenance": {
                            "summary": "Scheduled Maintenance",
                            "description": "Scheduled maintenance is in progress.",
                            "value": STATUS_COLOURS["#ffcc00"],
                        },
                        "general": {
                            "summary": "General Information",
                            "value": STATUS_COLOURS["#99cccc"],
                        },
                        "normal": {
                            "summary": "Normal Operations",
                            "description": "Everything is operating normally.",
                            "value": STATUS_COLOURS["#66cc33"],
                        },
                        "resolved": {
                            "summary": "Resolved",
                            "description": "Everything is operating normally.",
                            "value": STATUS_COLOURS["#999999"],
                        },
                    }
                }
            },
        },
    },
)  # type: ignore[misc]
async def status() -> SystemStatus:
    return await get_system_status()


if __name__ == "__main__":
    import asyncio

    status = asyncio.run(get_system_status())
    print(status)
