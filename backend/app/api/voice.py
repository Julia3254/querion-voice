import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.schemas.voice import VoiceRequest, VoiceResponse, VoiceTarget
from app.services.chat_service import generate_answer
from app.services.event_manager import event_manager
from app.services.exclusion_service import check_exclusion
from app.services.fallback_service import get_fallback_response
from app.services.idle_service import choose_idle_phrase
from app.services.ip_access_service import require_allowed_network
from app.services.rag_service import get_context_for_question
from app.services.session_manager import session_manager
from app.services.speech_to_text_service import transcribe_audio
from app.services.text_to_speech_service import generate_speech


router = APIRouter(prefix="/voice", tags=["voice"])

UPLOAD_DIR = Path("app/temp/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def limit_answer_for_voice(answer_text: str) -> str:
    text = " ".join((answer_text or "").split())
    max_chars = int(getattr(settings, "VOICE_MAX_ANSWER_CHARS", 220))

    if len(text) <= max_chars:
        return text

    shortened = text[:max_chars].rsplit(" ", 1)[0].strip(" ,;:-")
    sentence_end = max(
        shortened.rfind("."),
        shortened.rfind("!"),
        shortened.rfind("?"),
    )

    if sentence_end >= 80:
        shortened = shortened[: sentence_end + 1]

    if not shortened.endswith((".", "!", "?")):
        shortened += "."

    return shortened


def generate_speech_with_timing(answer_text: str, target: VoiceTarget) -> str | None:
    tts_start = time.perf_counter()
    audio_url = generate_speech(answer_text, target)

    print(f"VOICE TTS_TIME={time.perf_counter() - tts_start:.2f}s")

    return audio_url


def process_question(
    transcript: str,
    session_id: str | None = None,
    target: VoiceTarget = "phone",
) -> VoiceResponse:
    total_start = time.perf_counter()
    transcript = transcript.strip()

    if not transcript:
        message = "Nie usłyszałem pytania, spróbuj jeszcze raz."
        message = limit_answer_for_voice(message)
        audio_url = generate_speech_with_timing(message, target)

        print(f"VOICE TOTAL_PROCESS_TIME={time.perf_counter() - total_start:.2f}s")

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
        answer_text = limit_answer_for_voice(answer_text)
        audio_url = generate_speech_with_timing(answer_text, target)

        print(f"VOICE TOTAL_PROCESS_TIME={time.perf_counter() - total_start:.2f}s")

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

    rag_start = time.perf_counter()
    rag_result = get_context_for_question(transcript)

    print(f"VOICE RAG_TIME={time.perf_counter() - rag_start:.2f}s")
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

    if not has_context and category == "project":
        answer_text = get_fallback_response()
        answer_text = limit_answer_for_voice(answer_text)
        audio_url = generate_speech_with_timing(answer_text, target)

        print(f"VOICE TOTAL_PROCESS_TIME={time.perf_counter() - total_start:.2f}s")

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

    answer_start = time.perf_counter()
    answer_text = generate_answer(
        transcript,
        str(rag_result.get("context") or ""),
        category=category,
        target=target,
    )

    print(f"VOICE OPENAI_TIME={time.perf_counter() - answer_start:.2f}s")

    original_answer_length = len(answer_text or "")
    answer_text = limit_answer_for_voice(answer_text)

    if len(answer_text) != original_answer_length:
        print(
            "VOICE ANSWER_LIMITED:",
            {
                "original_chars": original_answer_length,
                "limited_chars": len(answer_text),
            },
        )

    audio_url = generate_speech_with_timing(answer_text, target)

    print(
        "VOICE ANSWER:",
        {
            "target": target,
            "answer_chars": len(answer_text),
            "answer_text": answer_text,
            "audio_url": audio_url,
        },
    )
    print(f"VOICE TOTAL_PROCESS_TIME={time.perf_counter() - total_start:.2f}s")

    return VoiceResponse(
        transcript=transcript,
        answer_text=answer_text,
        answer_audio_url=audio_url,
        animation_state="speaking" if audio_url else "waiting",
        fallback_used=False,
        sources=rag_result.get("sources", []),
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

    session_manager.set_state(session_id, state)

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
    session_manager.set_state(session_id, state)

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
async def handle_idle_voice(http_request: Request, request: VoiceRequest):
    require_allowed_network(http_request)

    total_start = time.perf_counter()
    target = request.target or "tv"
    phrase = choose_idle_phrase(target)
    phrase = limit_answer_for_voice(phrase)

    audio_url = await run_in_threadpool(
        generate_speech_with_timing,
        phrase,
        target,
    )

    if request.session_id:
        await _broadcast_state(
            request.session_id,
            "speaking" if audio_url else "waiting",
            {"target": target, "idle": True},
        )

    print(f"VOICE IDLE_TOTAL_TIME={time.perf_counter() - total_start:.2f}s")

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
async def handle_voice_text(http_request: Request, request: VoiceRequest):
    require_allowed_network(http_request)

    total_start = time.perf_counter()
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

    print(f"VOICE TEXT_ENDPOINT_TOTAL_TIME={time.perf_counter() - total_start:.2f}s")

    return result


@router.post("/audio", response_model=VoiceResponse)
async def handle_voice_audio(
    http_request: Request,
    file: UploadFile = File(...),
    session_id: str | None = Form(default=None),
    target: VoiceTarget = Form(default="phone"),
    client_id: str | None = Form(default=None),
):
    require_allowed_network(http_request)

    total_start = time.perf_counter()

    if target == "tv" and session_id:
        if not session_manager.can_client_record_on_tv(session_id, client_id):
            tv_status = session_manager.get_client_status(session_id, client_id)

            print(f"VOICE AUDIO_REJECTED_TOTAL_TIME={time.perf_counter() - total_start:.2f}s")

            return VoiceResponse(
                session_id=session_id,
                target=target,
                can_record=False,
                queue_position=tv_status.get("queue_position"),
                animation_state=tv_status.get("state", "waiting"),
                message="Jesteś w kolejce do rozmowy na TV.",
            )

        session_manager.mark_turn_started(session_id, client_id)

    filename = f"{uuid.uuid4()}_{file.filename or 'recording.webm'}"
    filepath = UPLOAD_DIR / filename

    try:
        upload_start = time.perf_counter()

        with open(filepath, "wb") as buffer:
            buffer.write(await file.read())

        print(
            "VOICE UPLOAD:",
            {
                "filename": filename,
                "size_bytes": filepath.stat().st_size if filepath.exists() else None,
                "upload_time": round(time.perf_counter() - upload_start, 2),
            },
        )

        if session_id:
            await _broadcast_state(session_id, "thinking", {"target": target})

        stt_start = time.perf_counter()
        transcript = await run_in_threadpool(transcribe_audio, str(filepath))

        print(f"VOICE STT_TIME={time.perf_counter() - stt_start:.2f}s")

        process_start = time.perf_counter()
        result = await run_in_threadpool(
            process_question,
            transcript,
            session_id,
            target,
        )

        print(f"VOICE PROCESS_THREAD_TIME={time.perf_counter() - process_start:.2f}s")

        if session_id:
            await _broadcast_voice_response(
                session_id,
                target,
                result.answer_audio_url,
            )

        print(f"VOICE AUDIO_ENDPOINT_TOTAL_TIME={time.perf_counter() - total_start:.2f}s")

        return result

    except Exception as error:
        print("VOICE AUDIO ERROR:", repr(error))

        message = "Nie usłyszałem pytania, spróbuj jeszcze raz."
        message = limit_answer_for_voice(message)

        audio_url = await run_in_threadpool(
            generate_speech_with_timing,
            message,
            target,
        )

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

        print(f"VOICE AUDIO_ERROR_TOTAL_TIME={time.perf_counter() - total_start:.2f}s")

        return result

    finally:
        if filepath.exists():
            filepath.unlink()