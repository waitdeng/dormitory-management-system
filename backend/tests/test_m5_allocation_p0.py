"""M5 P0 — visual bed allocation consistency (real MySQL).

Covers AGENTS.md M5 P0 可视化分床:
  - free / reserved / occupied / maintenance / disabled display flags
  - free bed can enter allocation flow (create → reserve → confirm)
  - concurrent same-bed allocation: exactly one succeeds
  - occupied / reserved / disabled beds cannot be allocated
  - vacant counts match DB
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient

from tests.helpers_m2 import admin_headers
from tests.helpers_m3 import make_dorm, make_employee
from tests.helpers_m4 import (
    checkin_employee,
)


async def _emp(client, headers, suffix: str = "") -> dict:
    return await make_employee(client, headers, suffix=suffix)


@pytest.mark.asyncio
async def test_p0_room_cards_show_all_bed_states(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=4)
    beds = dorm["beds"]
    emp = await _emp(client, admin, "RC")

    await checkin_employee(client, admin, emp["id"], beds[0]["id"])
    # reserve bed1
    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={
                "employee_id": (await _emp(client, admin, "RS"))["id"],
                "application_type": "new",
            },
        )
    ).json()
    await client.post(f"/api/v1/checkin-applications/{app['id']}/approve", headers=admin, json={})
    await client.post(
        f"/api/v1/checkin-applications/{app['id']}/reserve",
        headers=admin,
        json={"bed_id": beds[1]["id"]},
    )
    await client.post(f"/api/v1/beds/{beds[2]['id']}/maintenance", headers=admin, json={})
    await client.post(f"/api/v1/beds/{beds[3]['id']}/disable", headers=admin, json={})

    cards = await client.get(
        f"/api/v1/floors/{dorm['floor']['id']}/room-cards", headers=admin
    )
    assert cards.status_code == 200, cards.text
    room = next(c for c in cards.json() if c["id"] == dorm["room"]["id"])
    by_id = {b["id"]: b for b in room["beds"]}

    assert by_id[beds[0]["id"]]["occupied"] is True
    assert by_id[beds[0]["id"]]["available"] is False
    assert by_id[beds[0]["id"]]["occupant"] is not None
    assert by_id[beds[1]["id"]]["reserved"] is True
    assert by_id[beds[1]["id"]]["available"] is False
    assert by_id[beds[2]["id"]]["operational_status"] == "maintenance"
    assert by_id[beds[3]["id"]]["operational_status"] == "disabled"
    assert room["occupied_count"] == 1
    assert room["reserved_count"] == 1


@pytest.mark.asyncio
async def test_p0_allocate_free_bed_via_flow(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    emp = await _emp(client, admin, "AL")
    bed = dorm["beds"][0]

    cards = (
        await client.get(
            f"/api/v1/floors/{dorm['floor']['id']}/room-cards", headers=admin
        )
    ).json()
    room = cards[0]
    assert room["beds"][0]["available"] is True

    await checkin_employee(client, admin, emp["id"], bed["id"])

    cards2 = (
        await client.get(
            f"/api/v1/floors/{dorm['floor']['id']}/room-cards", headers=admin
        )
    ).json()
    assert cards2[0]["beds"][0]["available"] is False
    assert cards2[0]["beds"][0]["occupied"] is True


@pytest.mark.asyncio
async def test_p0_concurrent_same_bed_only_one_success(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=1)
    bed = dorm["beds"][0]
    emp1 = await _emp(client, admin, "C1")
    emp2 = await _emp(client, admin, "C2")

    app1 = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp1["id"], "application_type": "new"},
        )
    ).json()
    app2 = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp2["id"], "application_type": "new"},
        )
    ).json()
    for app_id in (app1["id"], app2["id"]):
        await client.post(
            f"/api/v1/checkin-applications/{app_id}/approve", headers=admin, json={}
        )

    r1, r2 = await asyncio.gather(
        client.post(
            f"/api/v1/checkin-applications/{app1['id']}/reserve",
            headers=admin,
            json={"bed_id": bed["id"]},
        ),
        client.post(
            f"/api/v1/checkin-applications/{app2['id']}/reserve",
            headers=admin,
            json={"bed_id": bed["id"]},
        ),
    )
    codes = sorted([r1.status_code, r2.status_code])
    assert codes[0] == 200, (r1.status_code, r1.text, r2.status_code, r2.text)
    assert codes[1] == 409, (r1.status_code, r2.status_code)

    # only one active reservation / accommodation path
    cards = (
        await client.get(f"/api/v1/floors/{dorm['floor']['id']}/room-cards", headers=admin)
    ).json()
    bed_card = cards[0]["beds"][0]
    assert bed_card["reserved"] or bed_card["occupied"]
    assert bed_card["available"] is False


@pytest.mark.asyncio
async def test_p0_cannot_allocate_taken_or_disabled_bed(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=2)
    b0, b1 = dorm["beds"]
    emp0 = await _emp(client, admin, "T0")
    await checkin_employee(client, admin, emp0["id"], b0["id"])
    await client.post(f"/api/v1/beds/{b1['id']}/disable", headers=admin, json={})

    emp1 = await _emp(client, admin, "T1")
    emp2 = await _emp(client, admin, "T2")

    # occupied bed
    app = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp1["id"], "application_type": "new"},
        )
    ).json()
    await client.post(f"/api/v1/checkin-applications/{app['id']}/approve", headers=admin, json={})
    r = await client.post(
        f"/api/v1/checkin-applications/{app['id']}/reserve",
        headers=admin,
        json={"bed_id": b0["id"]},
    )
    assert r.status_code == 409, r.text

    # disabled bed
    app2 = (
        await client.post(
            "/api/v1/checkin-applications",
            headers=admin,
            json={"employee_id": emp2["id"], "application_type": "new"},
        )
    ).json()
    await client.post(f"/api/v1/checkin-applications/{app2['id']}/approve", headers=admin, json={})
    r = await client.post(
        f"/api/v1/checkin-applications/{app2['id']}/reserve",
        headers=admin,
        json={"bed_id": b1["id"]},
    )
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_p0_vacant_count_matches_db(client: AsyncClient):
    admin = await admin_headers(client)
    dorm = await make_dorm(client, admin, capacity=3)
    beds = dorm["beds"]
    emp = await _emp(client, admin, "V")
    await checkin_employee(client, admin, emp["id"], beds[0]["id"])

    cards = (
        await client.get(f"/api/v1/floors/{dorm['floor']['id']}/room-cards", headers=admin)
    ).json()
    room = cards[0]
    assert room["available_count"] == 2

    vacant = (
        await client.get(
            f"/api/v1/reports/vacant-beds?building_id={dorm['building']['id']}",
            headers=admin,
        )
    ).json()
    vacant_ids = {i["bed_id"] for i in vacant["items"] if i["room_id"] == dorm["room"]["id"]}
    assert vacant_ids == {beds[1]["id"], beds[2]["id"]}
    assert room["available_count"] == len(vacant_ids)
