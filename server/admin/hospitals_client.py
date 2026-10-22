"""
Module 1 owns the hospitals table. Module 7 never touches it directly —
it asks over HTTP, using the SAME bearer token the browser sent to us, so
Module 1 enforces its own super_admin check too (defense in depth: even if
this service's dependency were misconfigured, Module 1 still says no).
"""
import os

import httpx

AUTH_API_URL = os.environ.get("FEDMED_AUTH_API_URL", "http://localhost:8001")


async def list_hospitals(bearer_token: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{AUTH_API_URL}/hospitals",
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()


async def set_hospital_status(hospital_id: str, is_active: bool, bearer_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{AUTH_API_URL}/hospitals/{hospital_id}",
            json={"is_active": is_active},
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=5.0,
        )
        resp.raise_for_status()
        return resp.json()
