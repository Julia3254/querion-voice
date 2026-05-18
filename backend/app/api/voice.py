from pathlib import Path
import uuid

from fastapi import APIRouter, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from app.schemas.voice import VoiceRequest, VoiceResponse, VoiceTarget
from app.services.chat_service import generate_answer
from app.services.event_manager import event_manager
from app.services.exclusion_service import check_exclusion
from app.services.fallback_service import get_fallback_response
from app.services.idle_service import choose_idle_phrase
from app.services.rag_service import get_context_for_question
from app.services.session_manager import session_manager
from app.services.speech_to_text_service import transcribe_audio
from app.services.text_to_speech_service import generate_speech

router = APIRouter(prefix="/voice", tags=["voice"])

UPLOAD_DIR = Path("app/temp/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def process_question(
    transcript: str,
    session_id: str | None = None,
    target: VoiceTarget = "phone",
) -> VoiceResponse:
    transcript = transcript.strip()

    if not transcript:
        message = "Nie usłyszałem pytania, spróbuj jeszcze raz."
        audio_url = generate_speech(message, target)

        return VoiceResponse(
            transcript="",
            answer_text=message,
            answer_audio_url=audio_url,
            animation_state="speaking" if audio_url else "waiting",
            fallback_used=True,
            sources=[],
            session_id=session_id,
            target=target,
        )

    print(f"VOICE TRANSCRIPT target={target} session_id={session_id}: {transcript!r}")

    exclusion_result = check_exclusion(transcript)

    if exclusion_result["blocked"]:
        print(f"VOICE EXCLUSION: {exclusion_result}")

        answer_text = exclusion_result.get("message") or get_fallback_response()
        audio_url = generate_speech(answer_text, target)

        return VoiceResponse(
            transcript=transcript,
            answer_text=answer_text,
            answer_audio_url=audio_url,
            animation_state="speaking" if audio_url else "waiting",
            fallback_used=True,
            sources=[],
            session_id=session_id,
            target=target,
        )

    rag_result = get_context_for_question(transcript)

    print(
        "VOICE RAG:",
        {
            "category": rag_result.get("category"),
            "has_context": rag_result.get("has_context"),
            "sources": rag_result.get("sources"),
        },
    )

    category = str(rag_result.get("category") or "general")
    has_context = bool(rag_result.get("has_context"))

    # Project bez RAG = odmowa, żeby nie zmyślać faktów o Querionie.
    # Ogólne pytania bez RAG = normalny model OpenAI.
    # Persona zależy od targetu:
    # - target="tv" -> Erion
    # - target="phone" -> Quera
    if not has_context and category == "project":
        answer_text = get_fallback_response()
        audio_url = generate_speech(answer_text, target)

        return VoiceResponse(
            transcript=transcript,
            answer_text=answer_text,
            answer_audio_url=audio_url,
            animation_state="speaking" if audio_url else "waiting",
            fallback_used=True,
            sources=[],
            session_id=session_id,
            target=target,
        )

    answer_text = generate_answer(
        transcript,
        str(rag_result.get("context") or ""),
        category=category,
        target=target,
    )

    audio_url = generate_speech(answer_text, target)

    print(
        "VOICE ANSWER:",
        {
            "target": target,
            "answer_text": answer_text,
            "audio_url": audio_url,
        },
    )

    return VoiceResponse(
        transcript=transcript,
        answer_text=answer_text,
        answer_audio_url=audio_url,
        animation_state="speaking" if audio_url else "waiting",
        fallback_used=False,
        sources=rag_result["sources"],
        session_id=session_id,
        target=target,
    )


async def _broadcast_state(
    session_id: str | None,
    state: str,
    extra: dict | None = None,
) -> None:
    if not session_id:
        return

    session_manager.set_state(session_id, state)  # type: ignore[arg-type]

    payload = {
        "type": "state",
        "state": state,
    }

    if extra:
        payload.update(extra)

    await event_manager.broadcast(session_id, payload)


async def _broadcast_voice_response(
    session_id: str | None,
    target: VoiceTarget,
    answer_audio_url: str | None,
) -> None:
    if not session_id:
        return

    state = "speaking" if answer_audio_url else "waiting"

    session_manager.set_state(session_id, state)  # type: ignore[arg-type]

    if hasattr(session_manager, "set_last_response"):
        session_manager.set_last_response(session_id, answer_audio_url)

    await event_manager.broadcast(
        session_id,
        {
            "type": "voice_response",
            "state": state,
            "target": target,
            "answer_audio_url": answer_audio_url,
        },
    )


@router.post("/idle", response_model=VoiceResponse)
async def handle_idle_voice(request: VoiceRequest):
    target = request.target or "tv"
    phrase = choose_idle_phrase(target)
    audio_url = await run_in_threadpool(generate_speech, phrase, target)

    if request.session_id:
        await _broadcast_state(
            request.session_id,
            "speaking" if audio_url else "waiting",
            {"target": target, "idle": True},
        )

    return VoiceResponse(
        transcript="",
        answer_text=phrase,
        answer_audio_url=audio_url,
        animation_state="speaking" if audio_url else "waiting",
        fallback_used=False,
        sources=["idle_phrases.json"],
        session_id=request.session_id,
        target=target,
    )


@router.post("/text", response_model=VoiceResponse)
async def handle_voice_text(request: VoiceRequest):
    target = request.target

    if request.session_id:
        await _broadcast_state(request.session_id, "thinking", {"target": target})

    result = await run_in_threadpool(
        process_question,
        request.text,
        request.session_id,
        target,
    )

    if request.session_id:
        await _broadcast_voice_response(
            request.session_id,
            target,
            result.answer_audio_url,
        )

    return result


@router.post("/audio", response_model=VoiceResponse)
async def handle_voice_audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    target: VoiceTarget = Form(default="phone"),
    client_id: str | None = Form(default=None),
):
    if target == "tv" and session_id:
        if not session_manager.can_client_record_on_tv(session_id, client_id):
            status = session_manager.get_client_status(session_id, client_id)

            return VoiceResponse(
                session_id=session_id,
                target=target,
                can_record=False,
                queue_position=status.get("queue_position"),
                animation_state=status.get("state", "waiting"),
                message="Jesteś w kolejce do rozmowy na TV.",
            )

        session_manager.mark_turn_started(session_id, client_id)

    filename = f"{uuid.uuid4()}_{file.filename or 'recording.webm'}"
    filepath = UPLOAD_DIR / filename

    try:
        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())

        if session_id:
            await _broadcast_state(session_id, "thinking", {"target": target})

        transcript = await run_in_threadpool(transcribe_audio, str(filepath))

        result = await run_in_threadpool(
            process_question,
            transcript,
            session_id,
            target,
        )

        if session_id:
            await _broadcast_voice_response(
                session_id,
                target,
                result.answer_audio_url,
            )

        return result

    except Exception as error:
        print("VOICE AUDIO ERROR:", repr(error))

        message = "Nie usłyszałem pytania, spróbuj jeszcze raz."
        audio_url = await run_in_threadpool(generate_speech, message, target)

        result = VoiceResponse(
            transcript="",
            answer_text=message,
            answer_audio_url=audio_url,
            animation_state="speaking" if audio_url else "waiting",
            fallback_used=True,
            sources=[],
            session_id=session_id,
            target=target,
        )

        if session_id:
            await _broadcast_voice_response(
                session_id,
                target,
                audio_url,
            )

        return result

    finally:
        if filepath.exists():
            filepath.unlink()