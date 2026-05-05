from typing import List, Literal, Optional
from pydantic import BaseModel, Field

AvatarState = Literal["waiting", "listening", "thinking", "speaking"]
VoiceTarget = Literal["phone", "tv"]


class VoiceRequest(BaseModel):
    text: str
    session_id: Optional[str] = None
    target: VoiceTarget = "phone"
    client_id: Optional[str] = None


class VoiceResponse(BaseModel):
    # Te pola są potrzebne technicznie dla backendu i debugowania.
    # Frontend NIE pokazuje transkrypcji ani tekstu odpowiedzi użytkownikowi.
    transcript: str = ""
    answer_text: str = ""
    answer_audio_url: Optional[str] = None
    animation_state: AvatarState = "waiting"
    fallback_used: bool = False
    sources: List[str] = Field(default_factory=list)
    session_id: Optional[str] = None
    target: VoiceTarget = "phone"
    can_record: bool = True
    queue_position: Optional[int] = None
    message: Optional[str] = None
