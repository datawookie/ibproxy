import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response

from ibproxy.main import app  # import your FastAPI app
from ibproxy.status import STATUS_COLOURS, get_system_status

HTML_TEMPLATE = """
<table cellpadding="1" cellspacing="1" width="95%" class="TableOutline">

<tbody><tr>
<td class="CellTitle" colspan="5">System Availability</td>
</tr>

<tr>
<td class="columnheader" width="40">Stat</td>
<td class="columnheader" width="75%">Message</td>
<td class="columnheader">Created/Updated</td>
</tr>


<tr class="odd">
<td class="centeritem" style="background-color:{bgcolor}">&nbsp;</td>
<td><strong>No problems</strong><br>No problems reported at this time.

</td>
<td class="centeritem">
2025/09/10<br>
2025/09/10
</td>
</tr>

</tbody></table>
"""


@pytest.mark.asyncio
@respx.mock
@pytest.mark.parametrize("colour_hex, expected", STATUS_COLOURS.items())
async def test_get_system_status(colour_hex, expected):
    from ibproxy.const import STATUS_URL

    html = HTML_TEMPLATE.format(bgcolor=colour_hex)
    respx.get(STATUS_URL).mock(return_value=Response(200, content=html))

    result = await get_system_status()
    assert result == expected


def test_status_endpoint(monkeypatch):
    from ibproxy import status as status_module
    from ibproxy.models import SystemStatus

    dummy_status = SystemStatus(label="Mock Status", colour="💚")

    async def mock_get_system_status():
        return dummy_status

    monkeypatch.setattr(status_module, "get_system_status", mock_get_system_status)

    client = TestClient(app)
    response = client.get("/status")
    assert response.status_code == 200
    assert response.json() == dummy_status.model_dump()
