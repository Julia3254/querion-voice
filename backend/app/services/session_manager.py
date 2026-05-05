from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Literal, Optional
from uuid import uuid4

from app.schemas.voice import AvatarState

SessionKind = Literal["phone", "tv"]


@dataclass
class Session:
    id: str
    kind: SessionKind
    state: AvatarState = "waiting"
    active_client_id: Optional[str] = None
    queue: list[str] = field(default_factory=list)
    busy: bool = False

    response_id: int = 0
    answer_audio_url: Optional[str] = None


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def create_session(self, kind: SessionKind) -> Session:
        with self._lock:
            session = Session(id=str(uuid4()), kind=kind)
            self._sessions[session.id] = session
            return session

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def set_state(
        self,
        session_id: str,
        state: AvatarState,
        busy: Optional[bool] = None,
    ) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                return None

            session.state = state

            if busy is not None:
                session.busy = busy

            return session

    def set_last_response(
        self,
        session_id: str,
        answer_audio_url: Optional[str],
    ) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                return None

            session.response_id += 1
            session.answer_audio_url = answer_audio_url
            session.state = "speaking" if answer_audio_url else "waiting"

            return session

    def get_response_status(
        self,
        session_id: str,
        last_response_id: int = 0,
    ) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                raise KeyError("Session not found")

            has_new_response = session.response_id > last_response_id

            return {
                "session_id": session.id,
                "state": session.state,
                "response_id": session.response_id,
                "answer_audio_url": session.answer_audio_url if has_new_response else None,
                "has_new_response": has_new_response,
            }

    def join_tv_session(self, session_id: str, client_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session or session.kind != "tv":
                raise KeyError("TV session not found")

            if session.active_client_id == client_id:
                return self._status_for_client(session, client_id)

            if client_id in session.queue:
                return self._status_for_client(session, client_id)

            if session.active_client_id is None and not session.busy:
                session.active_client_id = client_id
            else:
                session.queue.append(client_id)

            return self._status_for_client(session, client_id)

    def get_client_status(
        self,
        session_id: str,
        client_id: Optional[str] = None,
    ) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                raise KeyError("Session not found")

            return self._status_for_client(session, client_id)

    def can_client_record_on_tv(
        self,
        session_id: str,
        client_id: Optional[str],
    ) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session or session.kind != "tv" or not client_id:
                return False

            return session.active_client_id == client_id and not session.busy

    def mark_turn_started(
        self,
        session_id: str,
        client_id: Optional[str],
    ) -> Optional[Session]:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session:
                return None

            if session.kind == "tv" and session.active_client_id != client_id:
                return None

            session.busy = True
            session.state = "thinking"

            return session

    def complete_tv_turn(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session or session.kind != "tv":
                raise KeyError("TV session not found")

            session.busy = False
            session.state = "waiting"

            if session.queue:
                session.active_client_id = session.queue.pop(0)

            return self._status_for_client(session, session.active_client_id)

    def _status_for_client(
        self,
        session: Session,
        client_id: Optional[str],
    ) -> dict:
        position: Optional[int] = None
        can_record = False
        role = "queued"

        if client_id and session.active_client_id == client_id:
            role = "active"
            can_record = not session.busy
        elif client_id and client_id in session.queue:
            position = session.queue.index(client_id) + 1

        return {
            "session_id": session.id,
            "state": session.state,
            "active_client_id": session.active_client_id,
            "queue_length": len(session.queue),
            "queue_position": position,
            "can_record": can_record,
            "role": role,
        }


session_manager = SessionManager()