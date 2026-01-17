import re

import httpx
from bs4 import BeautifulSoup
from fastapi import APIRouter, HTTPException

from ..const import STATUS_URL
from ..models import SystemStatus

router = APIRouter()

STATUS_COLOURS = {
    "#cc3333": SystemStatus(label="Problem / Outage", colour="🟥"),
    "#ffcc00": SystemStatus(label="Scheduled Maintenance", colour="🟧"),
    "#99cccc": SystemStatus(label="General Information", colour="🟦"),
    "#66cc33": SystemStatus(label="Normal Operations", colour="🟩"),
    "#999999": SystemStatus(label="Resolved", colour="⬜"),
}


async def get_system_status(timeout: float = 10) -> SystemStatus:
    """
    Retrieve the current system status from the IBKR status page.

    Raises:
        httpx.ConnectTimeout: If the request to the status page times out.
        RuntimeError: If the status page cannot be parsed.
    """

    async with httpx.AsyncClient() as client:
        response = await client.get(STATUS_URL, timeout=timeout)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    # Get system availability table.
    #
    # Layout of relevant part of status page:
    #
    # <table>
    #     <tbody>
    #         <tr>
    #             <td>System Availability</td>
    #         </tr>
    #         <tr>
    #             <td>Stat</td>
    #             <td>Message</td>
    #             <td>Created/Updated</td>
    #         </tr>
    #         <tr class="odd">
    #             <td class="centeritem" style="background-color:#66cc33">&nbsp;</td>
    #             <td><strong>No problems</strong><br>No problems reported at this time.</td>
    #             <td class="centeritem">
    #                 2025/09/16<br>
    #                 2025/09/16
    #             </td>
    #         </tr>
    #     </tbody>
    # </table>
    #
    try:
        # Other tables on the page. Most reliable way to find the right one.
        #
        availability = soup.find("td", string=re.compile("(System|Exchange) Availability")).parent.parent

        colour = availability.select_one("tr.odd > td.centeritem[style]")["style"].split(":")[-1].strip()

        return STATUS_COLOURS[colour]
    except AttributeError as error:
        raise RuntimeError("🚨 Failed to parse IBKR status page!") from error


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
    try:
        return await get_system_status()
    except RuntimeError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    status = asyncio.run(get_system_status())
    print(status)
