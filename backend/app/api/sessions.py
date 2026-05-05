from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
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
from app.services.session_manager import session_manager

router = APIRouter(prefix="/sessions", tags=["sessions"])


class UpdateSessionStateRequest(BaseModel):
    state: AvatarState
    target: VoiceTarget | None = None


@router.post("/phone", response_model=CreateSessionResponse)
def create_phone_session():
    session = session_manager.create_session("phone")
    return CreateSessionResponse(
        session_id=session.id,
        kind=session.kind,
        state=session.state,
    )


@router.post("/tv", response_model=CreateSessionResponse)
def create_tv_session():
    session = session_manager.create_session("tv")
    return CreateSessionResponse(
        session_id=session.id,
        kind=session.kind,
        state=session.state,
    )


@router.get("/{session_id}/response", response_model=SessionResponseStatus)
def get_session_response(session_id: str, last_response_id: int = 0):
    try:
        status = session_manager.get_response_status(session_id, last_response_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji.")

    return SessionResponseStatus(**status)


@router.post("/{session_id}/state")
async def update_session_state(session_id: str, request: UpdateSessionStateRequest):
    session = session_manager.set_state(session_id, request.state)

    if not session:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji.")

    await event_manager.broadcast(
        session_id,
        {
            "type": "state",
            "state": request.state,
            "target": request.target,
        },
    )

    return {
        "session_id": session_id,
        "state": request.state,
    }


@router.post("/tv/{session_id}/join", response_model=JoinTvSessionResponse)
async def join_tv_session(session_id: str, request: JoinTvSessionRequest):
    try:
        status = session_manager.join_tv_session(session_id, request.client_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji TV.")

    await event_manager.broadcast(
        session_id,
        {
            "type": "queue_updated",
            "state": status["state"],
            "active_client_id": status["active_client_id"],
            "queue_length": status["queue_length"],
        },
    )

    return JoinTvSessionResponse(
        session_id=session_id,
        client_id=request.client_id,
        role=status["role"],
        can_record=status["can_record"],
        queue_position=status["queue_position"],
        active_client_id=status["active_client_id"],
    )


@router.get("/tv/{session_id}/status", response_model=QueueStatusResponse)
def get_tv_status(session_id: str, client_id: str | None = None):
    try:
        status = session_manager.get_client_status(session_id, client_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji TV.")

    return QueueStatusResponse(**status)


@router.post("/tv/{session_id}/complete", response_model=QueueStatusResponse)
async def complete_tv_turn(session_id: str):
    try:
        status = session_manager.complete_tv_turn(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Nie znaleziono sesji TV.")

    await event_manager.broadcast(
        session_id,
        {
            "type": "turn_completed",
            "state": status["state"],
            "active_client_id": status["active_client_id"],
            "queue_length": status["queue_length"],
        },
    )

    return QueueStatusResponse(**status)


@router.websocket("/{session_id}/events")
async def session_events(session_id: str, websocket: WebSocket):
    await event_manager.connect(session_id, websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_manager.disconnect(session_id, websocket)