from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.health import router as health_router
from app.api.voice import router as voice_router
from app.api.sessions import router as sessions_router

app = FastAPI(title="Voice Avatar V2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

audio_dir = Path("app/temp/audio_responses")
audio_dir.mkdir(parents=True, exist_ok=True)

app.mount("/audio", StaticFiles(directory=str(audio_dir)), name="audio")

app.include_router(health_router)
app.include_router(voice_router)
app.include_router(sessions_router)
