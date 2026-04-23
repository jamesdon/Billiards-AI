from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.identities_path import identities_json_str
from core.identity_store import IdentityStore


def _store() -> IdentityStore:
    st = IdentityStore(path=identities_json_str())
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
        raise HTTPException(
            status_code=404,
            detail=(
                f"no player profile with id {profile_id!r}; list valid ids with GET /profiles "
                "(use each object’s `id` in the path — `PLAYER_PROFILE_ID` in curl examples is a placeholder, not a real id)"
            ),
        )


@router.patch("/stick/{profile_id}")
def rename_stick(profile_id: str, req: RenameReq):
    st = _store()
    try:
        st.rename_stick(profile_id, req.display_name)
        st.save()
        return {"ok": True}
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=(
                f"no stick profile with id {profile_id!r}; list valid ids with GET /profiles "
                "(use each object’s `id` in the path — `STICK_PROFILE_ID` in curl examples is a placeholder)"
            ),
        )

