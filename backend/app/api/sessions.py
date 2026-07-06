from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from app.schemas.session import (
    CreateSessionResponse,
    JoinTvSessionRequest,
    JoinTvSessionResponse,
    QueueStatusResponse,
    SessionResponseStatus,
)
from app.schemas.voice import AvatarState, VoiceTarget
from app.services.event_manager import event_manager
from app.services.ip_access_service import is_connection_allowed, require_allowed_network
from app.services.session_manager import session_manager


router = APIRouter(prefix="/sessions", tags=["sessions"])


class UpdateSessionStateRequest(BaseModel):
    state: AvatarState
    target: VoiceTarget | None = None


@router.post("/phone", response_model=CreateSessionResponse)
def create_phone_session(request: Request):
    require_allowed_network(request)

    session = session_manager.create_session("phone")

    return CreateSessionResponse(
        session_id=session.id,
        kind=session.kind,
        state=session.state,
    )


@router.post("/tv", response_model=CreateSessionResponse)
def create_tv_session(request: Request):
    require_allowed_network(request)

    session = session_manager.create_session("tv")

    return CreateSessionResponse(
        session_id=session.id,
        kind=session.kind,
        state=session.state,
    )


@router.get("/{session_id}/response", response_model=SessionResponseStatus)
def get_session_response(
    request: Request,
    session_id: str,
    last_response_id: int = 0,
):
    require_allowed_network(request)

    try:
        response_status = session_manager.get_response_status(session_id, last_response_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji.")

    return SessionResponseStatus(**response_status)


@router.post("/{session_id}/state")
async def update_session_state(
    request: Request,
    session_id: str,
    payload: UpdateSessionStateRequest,
):
    require_allowed_network(request)

    session = session_manager.set_state(session_id, payload.state)

    if not session:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji.")

    await event_manager.broadcast(
        session_id,
        {
            "type": "state",
            "state": payload.state,
            "target": payload.target,
        },
    )

    return {
        "session_id": session_id,
        "state": payload.state,
    }


@router.post("/tv/{session_id}/join", response_model=JoinTvSessionResponse)
async def join_tv_session(
    request: Request,
    session_id: str,
    payload: JoinTvSessionRequest,
):
    require_allowed_network(request)

    try:
        tv_status = session_manager.join_tv_session(session_id, payload.client_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji TV.")

    await event_manager.broadcast(
        session_id,
        {
            "type": "queue_updated",
            "state": tv_status["state"],
            "active_client_id": tv_status["active_client_id"],
            "queue_length": tv_status["queue_length"],
        },
    )

    return JoinTvSessionResponse(
        session_id=session_id,
        client_id=payload.client_id,
        role=tv_status["role"],
        can_record=tv_status["can_record"],
        queue_position=tv_status["queue_position"],
        active_client_id=tv_status["active_client_id"],
    )


@router.get("/tv/{session_id}/status", response_model=QueueStatusResponse)
def get_tv_status(
    request: Request,
    session_id: str,
    client_id: str | None = None,
):
    require_allowed_network(request)

    try:
        tv_status = session_manager.get_client_status(session_id, client_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji TV.")

    return QueueStatusResponse(**tv_status)


@router.post("/tv/{session_id}/complete", response_model=QueueStatusResponse)
async def complete_tv_turn(
    request: Request,
    session_id: str,
):
    require_allowed_network(request)

    try:
        tv_status = session_manager.complete_tv_turn(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji TV.")

    await event_manager.broadcast(
        session_id,
        {
            "type": "turn_completed",
            "state": tv_status["state"],
            "active_client_id": tv_status["active_client_id"],
            "queue_length": tv_status["queue_length"],
        },
    )

    return QueueStatusResponse(**tv_status)


@router.websocket("/{session_id}/events")
async def session_events(session_id: str, websocket: WebSocket):
    if not is_connection_allowed(websocket):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await event_manager.connect(session_id, websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_manager.disconnect(session_id, websocket)