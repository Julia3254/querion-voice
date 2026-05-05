from typing import Literal, Optional
from pydantic import BaseModel

from app.schemas.voice import AvatarState

SessionKind = Literal["phone", "tv"]
ClientRole = Literal["active", "queued"]


class CreateSessionResponse(BaseModel):
    session_id: str
    kind: SessionKind
    state: AvatarState


class JoinTvSessionRequest(BaseModel):
    client_id: str


class JoinTvSessionResponse(BaseModel):
    session_id: str
    client_id: str
    role: ClientRole
    can_record: bool
    queue_position: Optional[int] = None
    active_client_id: Optional[str] = None


class QueueStatusResponse(BaseModel):
    session_id: str
    state: AvatarState
    active_client_id: Optional[str] = None
    queue_length: int = 0
    queue_position: Optional[int] = None
    can_record: bool = False


class SessionResponseStatus(BaseModel):
    session_id: str
    state: AvatarState
    response_id: int = 0
    answer_audio_url: Optional[str] = None
    has_new_response: bool = False