from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from time import monotonic
from typing import Literal, Optional
from uuid import uuid4

from app.schemas.voice import AvatarState

SessionKind = Literal["phone", "tv"]

# Ostateczne zabezpieczenie backendu.
# Jeśli TV/frontend nie zakończy tury, backend odblokuje sesję po 60 sekundach.
TV_BUSY_TIMEOUT_SECONDS = 60


@dataclass
class Session:
    id: str
    kind: SessionKind
    state: AvatarState = "waiting"
    active_client_id: Optional[str] = None
    queue: list[str] = field(default_factory=list)
    busy: bool = False
    busy_started_at: Optional[float] = None

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
            session = self._sessions.get(session_id)

            if session:
                self._release_stale_busy_locked(session)

            return session

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

            self._release_stale_busy_locked(session)

            session.state = state

            if busy is not None:
                session.busy = busy
                session.busy_started_at = monotonic() if busy else None

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

            self._release_stale_busy_locked(session)

            session.response_id += 1
            session.answer_audio_url = answer_audio_url
            session.state = "speaking" if answer_audio_url else "waiting"

            if session.kind == "tv":
                if answer_audio_url:
                    # Od tego momentu TV ma czas na odtworzenie odpowiedzi.
                    # Jeśli tego nie zrobi, backend awaryjnie odblokuje turę.
                    session.busy = True
                    session.busy_started_at = monotonic()
                else:
                    session.busy = False
                    session.busy_started_at = None
            elif not answer_audio_url:
                session.busy = False
                session.busy_started_at = None

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

            self._release_stale_busy_locked(session)

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

            self._release_stale_busy_locked(session)

            if session.active_client_id == client_id:
                return self._status_for_client(session, client_id)

            if client_id in session.queue:
                session.queue.remove(client_id)

            if not session.busy:
                session.active_client_id = client_id
                session.queue.clear()
            else:
                if client_id != session.active_client_id and client_id not in session.queue:
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

            self._release_stale_busy_locked(session)

            if (
                session.kind == "tv"
                and client_id
                and not session.busy
                and session.active_client_id
                and session.active_client_id != client_id
                and client_id in session.queue
            ):
                session.queue.remove(client_id)
                session.active_client_id = client_id
                session.queue.clear()

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

            self._release_stale_busy_locked(session)

            if not session.busy and session.active_client_id != client_id:
                session.active_client_id = client_id
                session.queue = [item for item in session.queue if item != client_id]

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

            self._release_stale_busy_locked(session)

            if session.kind == "tv" and session.active_client_id != client_id:
                return None

            session.busy = True
            session.busy_started_at = monotonic()
            session.state = "thinking"

            return session

    def complete_tv_turn(self, session_id: str) -> dict:
        with self._lock:
            session = self._sessions.get(session_id)

            if not session or session.kind != "tv":
                raise KeyError("TV session not found")

            self._complete_tv_turn_locked(session)

            return self._status_for_client(session, session.active_client_id)

    def _complete_tv_turn_locked(self, session: Session) -> None:
        session.busy = False
        session.busy_started_at = None
        session.state = "waiting"

        # Czyścimy stare audio, żeby po odświeżeniu TV nie próbował grać starej odpowiedzi.
        session.answer_audio_url = None

        if session.queue:
            session.active_client_id = session.queue.pop(0)

    def _release_stale_busy_locked(self, session: Session) -> None:
        if session.kind != "tv":
            return

        if not session.busy or session.busy_started_at is None:
            return

        elapsed = monotonic() - session.busy_started_at

        if elapsed < TV_BUSY_TIMEOUT_SECONDS:
            return

        print(
            f"[session_manager] Awaryjne odblokowanie sesji TV {session.id} "
            f"po {elapsed:.1f}s."
        )

        self._complete_tv_turn_locked(session)

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