from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.identity_store import IdentityStore


def _store() -> IdentityStore:
    path = os.environ.get("BILLIARDS_IDENTITIES_PATH", "./identities.json")
    st = IdentityStore(path=path)
    st.load()
    return st


router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.get("")
def list_profiles():
    st = _store()
    return {
        "players": [asdict(p) for p in st.players.values()],
        "sticks": [asdict(s) for s in st.sticks.values()],
    }


class RenameReq(BaseModel):
    display_name: str


@router.patch("/player/{profile_id}")
def rename_player(profile_id: str, req: RenameReq):
    st = _store()
    try:
        st.rename_player(profile_id, req.display_name)
        st.save()
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="player profile not found")


@router.patch("/stick/{profile_id}")
def rename_stick(profile_id: str, req: RenameReq):
    st = _store()
    try:
        st.rename_stick(profile_id, req.display_name)
        st.save()
        return {"ok": True}
    except KeyError:
        raise HTTPException(status_code=404, detail="stick profile not found")

