"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Avatar from "../../components/Avatar";
import VoiceWave from "../../components/VoiceWave";
import { useAudioRecorder } from "../../hooks/useAudioRecorder";
import {
  buildAudioSrc,
  completeTvTurn,
  createPhoneSession,
  getClientId,
  getTvStatus,
  joinTvSession,
  sendVoiceAudio,
  setSessionState,
} from "../../services/api";
import type { AvatarState, VoiceTarget } from "../../types/api";

function PhonePageContent() {
  const params = useSearchParams();
  const tvSessionId = params.get("tvSessionId") ?? params.get("tv") ?? "";

  const isTvMicMode = Boolean(tvSessionId);
  const mode: VoiceTarget = isTvMicMode ? "tv" : "phone";

  const [clientId, setClientId] = useState("");
  const [sessionId, setSessionId] = useState("");
  const [avatarState, setAvatarState] = useState<AvatarState>("waiting");
  const [isProcessing, setIsProcessing] = useState(false);
  const [canRecord, setCanRecord] = useState(false);
  const [queuePosition, setQueuePosition] = useState<number | null>(null);
  const [statusText, setStatusText] = useState("Łączenie...");
  const [connectionError, setConnectionError] = useState("");
  const [pendingAudioSrc, setPendingAudioSrc] = useState<string | null>(null);
  const [showTvUnlock, setShowTvUnlock] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isRecordingTurnRef = useRef(false);
  const isWaitingForTvResponseRef = useRef(false);
  const tvSafetyTimeoutRef = useRef<number | null>(null);
  const tvUnlockButtonTimeoutRef = useRef<number | null>(null);

  const {
    isRecording,
    volumeLevel,
    mimeType,
    startRecording,
    stopRecording,
    cleanupAudioResources,
  } = useAudioRecorder();

  const pageTitle = useMemo(() => {
    return isTvMicMode ? "Mikrofon TV" : "Zabierz Querę ze sobą";
  }, [isTvMicMode]);

  const clearTvTimers = () => {
    if (tvSafetyTimeoutRef.current) {
      window.clearTimeout(tvSafetyTimeoutRef.current);
      tvSafetyTimeoutRef.current = null;
    }

    if (tvUnlockButtonTimeoutRef.current) {
      window.clearTimeout(tvUnlockButtonTimeoutRef.current);
      tvUnlockButtonTimeoutRef.current = null;
    }
  };

  const stopAudioPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }
  };

  const playAudioFromSrc = async (src: string) => {
    stopAudioPlayback();

    const audio = new Audio(src);
    audioRef.current = audio;

    audio.onplay = () => {
      setAvatarState("speaking");
      setStatusText("Quera odpowiada głosowo...");
    };

    audio.onended = () => {
      setAvatarState("waiting");
      setStatusText("Kliknij przycisk, żeby zadać kolejne pytanie.");
      setPendingAudioSrc(null);
    };

    audio.onerror = () => {
      setAvatarState("waiting");
      setPendingAudioSrc(src);
      setStatusText("Nie udało się odtworzyć audio. Kliknij „Odtwórz odpowiedź”.");
    };

    try {
      await audio.play();
    } catch {
      setAvatarState("waiting");
      setPendingAudioSrc(src);
      setStatusText("Kliknij „Odtwórz odpowiedź”, żeby usłyszeć odpowiedź.");
    }
  };

  const handlePlayPendingAudio = async () => {
    if (!pendingAudioSrc) {
      return;
    }

    await playAudioFromSrc(pendingAudioSrc);
  };

  const refreshTvStatus = async (sid: string, cid: string) => {
    const status = await getTvStatus(sid, cid);

    setCanRecord(status.can_record);
    setQueuePosition(status.queue_position ?? null);

    if (status.can_record) {
      clearTvTimers();
      isWaitingForTvResponseRef.current = false;
      setShowTvUnlock(false);
      setStatusText(
        "Połączono z TV. Kliknij przycisk, powiedz pytanie i kliknij drugi raz, żeby wysłać."
      );
    } else if (status.queue_position != null) {
      clearTvTimers();
      isWaitingForTvResponseRef.current = false;
      setShowTvUnlock(false);
      setStatusText(`Jesteś w kolejce. Twoje miejsce: ${status.queue_position}.`);
    } else {
      setStatusText("Erion odpowiada. Poczekaj chwilę.");
    }
  };

  const unlockTvTurn = async (sid = sessionId, cid = clientId) => {
    if (!sid) {
      return;
    }

    clearTvTimers();
    isWaitingForTvResponseRef.current = false;
    setShowTvUnlock(false);

    try {
      await completeTvTurn(sid);
    } catch (error) {
      console.warn("Nie udało się awaryjnie zakończyć tury TV:", error);

      try {
        await setSessionState(sid, "waiting", "tv");
      } catch {}
    }

    setIsProcessing(false);
    setAvatarState("waiting");
    setCanRecord(true);
    setQueuePosition(null);
    setStatusText("Możesz zadać kolejne pytanie.");

    if (sid && cid) {
      window.setTimeout(() => {
        void refreshTvStatus(sid, cid).catch(() => {});
      }, 700);
    }
  };

  const scheduleTvSafetyUnlock = (sid: string, cid: string) => {
    clearTvTimers();

    isWaitingForTvResponseRef.current = true;
    setShowTvUnlock(false);

    // Po 15 sekundach pokazujemy ręczny przycisk odblokowania.
    tvUnlockButtonTimeoutRef.current = window.setTimeout(() => {
      if (isWaitingForTvResponseRef.current) {
        setShowTvUnlock(true);
      }
    }, 15000);

    // Po 35 sekundach telefon sam awaryjnie odblokuje turę.
    tvSafetyTimeoutRef.current = window.setTimeout(() => {
      if (isWaitingForTvResponseRef.current) {
        void unlockTvTurn(sid, cid);
      }
    }, 35000);
  };

  useEffect(() => {
    let cancelled = false;
    let statusInterval: number | null = null;

    const setup = async () => {
      try {
        setConnectionError("");
        setStatusText("Łączenie...");

        const cid = getClientId();
        setClientId(cid);

        if (isTvMicMode) {
          const join = await joinTvSession(tvSessionId, cid);

          if (cancelled) {
            return;
          }

          setSessionId(tvSessionId);
          setCanRecord(join.can_record);
          setQueuePosition(join.queue_position ?? null);

          if (join.can_record) {
            setStatusText(
              "Połączono z TV. Kliknij przycisk, powiedz pytanie i kliknij drugi raz, żeby wysłać."
            );
          } else {
            setStatusText(
              `Jesteś w kolejce. Twoje miejsce: ${join.queue_position ?? 1}.`
            );
          }

          statusInterval = window.setInterval(() => {
            void refreshTvStatus(tvSessionId, cid).catch((error) => {
              console.warn("TV status refresh error:", error);
            });
          }, 2000);

          return;
        }

        const session = await createPhoneSession();

        if (cancelled) {
          return;
        }

        setSessionId(session.session_id);
        setCanRecord(true);
        setStatusText(
          "Kliknij przycisk, powiedz pytanie i kliknij drugi raz, żeby wysłać."
        );
      } catch (error) {
        console.error("PHONE setup error", error);

        if (cancelled) {
          return;
        }

        setCanRecord(false);
        setConnectionError(
          "Nie udało się połączyć. Sprawdź, czy backend działa na porcie 8000."
        );
        setStatusText("Nie udało się połączyć.");
      }
    };

    void setup();

    return () => {
      cancelled = true;

      if (statusInterval) {
        window.clearInterval(statusInterval);
      }

      clearTvTimers();
      stopAudioPlayback();
      void cleanupAudioResources();
    };
  }, [isTvMicMode, tvSessionId]);

  const startTurn = async () => {
    if (isRecordingTurnRef.current || isProcessing || !canRecord || !sessionId) {
      return;
    }

    isRecordingTurnRef.current = true;
    isWaitingForTvResponseRef.current = false;
    clearTvTimers();
    setShowTvUnlock(false);
    stopAudioPlayback();
    setPendingAudioSrc(null);

    try {
      setAvatarState("listening");
      setStatusText(
        isTvMicMode
          ? "Mów do telefonu. Kliknij drugi raz, żeby wysłać pytanie do Eriona."
          : "Mów teraz. Kliknij drugi raz, żeby wysłać."
      );

      if (isTvMicMode) {
        void setSessionState(sessionId, "listening", "tv").catch((error) => {
          console.warn("Nie udało się ustawić stanu listening na TV", error);
        });
      }

      await startRecording();
    } catch (error) {
      console.error("Start recording error", error);

      isRecordingTurnRef.current = false;
      setAvatarState("waiting");

      if (isTvMicMode) {
        void setSessionState(sessionId, "waiting", "tv").catch(() => {});
      }

      setStatusText(
        "Nie udało się włączyć mikrofonu. Upewnij się, że strona działa po HTTPS."
      );
    }
  };

  const stopTurnAndSend = async () => {
    if (!isRecordingTurnRef.current || isProcessing) {
      return;
    }

    isRecordingTurnRef.current = false;

    const blob = await stopRecording();

    if (!blob) {
      setAvatarState("waiting");

      if (isTvMicMode && sessionId) {
        void setSessionState(sessionId, "waiting", "tv").catch(() => {});
      }

      setStatusText("Nie nagrałem pytania. Spróbuj jeszcze raz.");
      return;
    }

    try {
      setIsProcessing(true);
      setAvatarState("thinking");
      setStatusText(isTvMicMode ? "Erion myśli..." : "Quera myśli...");

      if (isTvMicMode) {
        void setSessionState(sessionId, "thinking", "tv").catch(() => {});
      }

      const result = await sendVoiceAudio(blob, {
        mimeType,
        sessionId,
        target: mode,
        clientId,
      });

      if (!result.can_record && result.queue_position) {
        setCanRecord(false);
        setQueuePosition(result.queue_position ?? null);
        setAvatarState("waiting");
        setStatusText(
          `Jesteś w kolejce. Twoje miejsce: ${result.queue_position ?? 1}.`
        );
        return;
      }

      if (isTvMicMode) {
        setCanRecord(false);
        setQueuePosition(null);
        setStatusText("Odpowiedź Eriona odtworzy się na TV. Poczekaj chwilę.");
        setAvatarState("waiting");

        scheduleTvSafetyUnlock(sessionId, clientId);

        window.setTimeout(() => {
          void refreshTvStatus(sessionId, clientId).catch(() => {});
        }, 2500);

        return;
      }

      const src = buildAudioSrc(result);

      if (src) {
        await playAudioFromSrc(src);
      } else {
        setAvatarState("waiting");
        setStatusText("Nie udało się wygenerować głosu odpowiedzi.");
      }
    } catch (error) {
      console.error("Send voice error", error);

      clearTvTimers();
      isWaitingForTvResponseRef.current = false;
      setShowTvUnlock(false);
      setAvatarState("waiting");
      setStatusText("Wystąpił błąd. Spróbuj jeszcze raz.");

      if (isTvMicMode && sessionId) {
        void setSessionState(sessionId, "waiting", "tv").catch(() => {});
      }
    } finally {
      setIsProcessing(false);
    }
  };

  const handleMainButtonClick = async () => {
    if (isProcessing || !canRecord || !sessionId) {
      return;
    }

    if (isRecordingTurnRef.current || isRecording) {
      await stopTurnAndSend();
      return;
    }

    await startTurn();
  };

  const buttonLabel = isRecording
    ? "Wyślij pytanie"
    : isProcessing
    ? "Przetwarzanie..."
    : canRecord
    ? "Kliknij i mów"
    : queuePosition
    ? `Kolejka: ${queuePosition}`
    : "Poczekaj";

  const buttonBackground = isRecording
    ? "linear-gradient(135deg, #dc2626 0%, #ff1c2d 100%)"
    : isProcessing || !canRecord
    ? "rgba(255, 255, 255, 0.24)"
    : "linear-gradient(135deg, #ff4a1c 0%, #ff1c2d 100%)";

  const screenBackground =
    "radial-gradient(circle at 88% 24%, rgba(255, 74, 28, 0.46), transparent 34%), radial-gradient(circle at 95% 92%, rgba(255, 28, 45, 0.24), transparent 42%), radial-gradient(circle at 15% 14%, rgba(255, 255, 255, 0.07), transparent 28%), linear-gradient(135deg, #0B0B12 0%, #151016 42%, #2A0D08 72%, #5A160B 100%)";

  const cardStyle = {
    width: "100%",
    maxWidth: 430,
    minHeight: isTvMicMode ? "calc(100svh - 48px)" : "auto",
    display: "flex",
    flexDirection: "column" as const,
    alignItems: "center",
    justifyContent: "center",
    gap: 22,
    textAlign: "center" as const,
    padding: "30px 22px",
    borderRadius: 32,
    border: "1px solid rgba(255, 255, 255, 0.14)",
    background: "rgba(255, 255, 255, 0.075)",
    boxShadow: "0 24px 60px rgba(0, 0, 0, 0.35)",
    backdropFilter: "blur(18px)",
    boxSizing: "border-box" as const,
  };

  const mainStyle = {
    minHeight: "100svh",
    background: screenBackground,
    color: "#ffffff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 20,
    boxSizing: "border-box" as const,
    fontFamily: "Arial, sans-serif",
    position: "relative" as const,
    overflow: "hidden",
  };

  const dotsLayer = (
    <div
      aria-hidden="true"
      style={{
        position: "absolute",
        inset: 0,
        backgroundImage:
          "radial-gradient(rgba(255, 255, 255, 0.12) 1px, transparent 1px)",
        backgroundSize: "14px 14px",
        opacity: 0.22,
        pointerEvents: "none",
      }}
    />
  );

  if (isTvMicMode) {
    return (
      <main style={mainStyle}>
        {dotsLayer}

        <div
          style={{
            position: "relative",
            zIndex: 1,
            ...cardStyle,
          }}
        >
          <div>
            <div
              style={{
                marginBottom: 8,
                fontSize: 12,
                fontWeight: 900,
                letterSpacing: "0.34em",
                color: "rgba(255, 255, 255, 0.48)",
                textTransform: "uppercase",
              }}
            >
              Model głosowy AI
            </div>

            <h1
              style={{
                fontSize: 36,
                margin: 0,
                fontWeight: 950,
                letterSpacing: "-0.045em",
                lineHeight: 0.95,
                color: "#ffffff",
              }}
            >
              Mikrofon TV
            </h1>

            <p
              style={{
                margin: "12px 0 0",
                fontSize: 16,
                lineHeight: 1.4,
                color: "rgba(255, 255, 255, 0.72)",
              }}
            >
              Ten telefon działa jako mikrofon do rozmowy z Erionem na ekranie
              TV. Odpowiedź pojawi się głosowo na TV.
            </p>
          </div>

          <div
            style={{
              width: 122,
              height: 122,
              borderRadius: "50%",
              background: isRecording
                ? "linear-gradient(135deg, #dc2626 0%, #ff1c2d 100%)"
                : canRecord
                ? "linear-gradient(135deg, rgba(255, 74, 28, 0.95), rgba(255, 28, 45, 0.95))"
                : "rgba(255, 255, 255, 0.18)",
              color: "#ffffff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 50,
              boxShadow: isRecording
                ? "0 0 0 14px rgba(255, 28, 45, 0.18), 0 22px 50px rgba(0, 0, 0, 0.35)"
                : "0 22px 50px rgba(0, 0, 0, 0.35)",
            }}
          >
            🎙️
          </div>

          <VoiceWave visible={isRecording} volumeLevel={volumeLevel} />

          <button
            type="button"
            disabled={isProcessing || !canRecord || !sessionId}
            onClick={handleMainButtonClick}
            style={{
              padding: "18px 28px",
              fontSize: 22,
              borderRadius: 20,
              border: "1px solid rgba(255, 255, 255, 0.18)",
              cursor:
                isProcessing || !canRecord || !sessionId
                  ? "not-allowed"
                  : "pointer",
              background: buttonBackground,
              color: "#fff",
              minWidth: 280,
              fontWeight: 900,
              touchAction: "manipulation",
              userSelect: "none",
              WebkitUserSelect: "none",
              boxShadow:
                isProcessing || !canRecord
                  ? "none"
                  : "0 16px 36px rgba(255, 56, 28, 0.32)",
              opacity: isProcessing || !canRecord || !sessionId ? 0.72 : 1,
            }}
          >
            {buttonLabel}
          </button>

          {showTvUnlock && (
            <button
              type="button"
              onClick={() => void unlockTvTurn()}
              style={{
                border: "1px solid rgba(255, 255, 255, 0.2)",
                borderRadius: 999,
                padding: "13px 18px",
                background: "rgba(255, 255, 255, 0.13)",
                color: "#ffffff",
                fontSize: 15,
                fontWeight: 900,
                boxShadow: "0 12px 30px rgba(0, 0, 0, 0.22)",
              }}
            >
              Odblokuj i zadaj kolejne pytanie
            </button>
          )}

          <p
            style={{
              minHeight: 52,
              maxWidth: 360,
              margin: 0,
              fontSize: 17,
              lineHeight: 1.4,
              color: connectionError ? "#fecaca" : "rgba(255, 255, 255, 0.82)",
              fontWeight: 700,
            }}
          >
            {connectionError || statusText}
          </p>

          {queuePosition && !canRecord && (
            <div
              style={{
                padding: "12px 16px",
                borderRadius: 16,
                background: "rgba(255, 255, 255, 0.12)",
                color: "#ffffff",
                fontWeight: 800,
                border: "1px solid rgba(255, 255, 255, 0.16)",
              }}
            >
              Twoje miejsce w kolejce: {queuePosition}
            </div>
          )}
        </div>
      </main>
    );
  }

  return (
    <main style={mainStyle}>
      {dotsLayer}

      <div
        style={{
          position: "relative",
          zIndex: 1,
          ...cardStyle,
          maxWidth: 520,
        }}
      >
        <div>
          <div
            style={{
              marginBottom: 8,
              fontSize: 12,
              fontWeight: 900,
              letterSpacing: "0.34em",
              color: "rgba(255, 255, 255, 0.48)",
              textTransform: "uppercase",
            }}
          >
            Wersja mobilna
          </div>

          <h1
            style={{
              fontSize: 32,
              margin: 0,
              fontWeight: 950,
              letterSpacing: "-0.04em",
              color: "#ffffff",
            }}
          >
            {pageTitle}
          </h1>
        </div>

        <Avatar state={avatarState} variant="phone" size="phone" />

        <VoiceWave visible={isRecording} volumeLevel={volumeLevel} />

        <button
          type="button"
          disabled={isProcessing || !canRecord || !sessionId}
          onClick={handleMainButtonClick}
          style={{
            padding: "18px 28px",
            fontSize: 22,
            borderRadius: 20,
            border: "1px solid rgba(255, 255, 255, 0.18)",
            cursor:
              isProcessing || !canRecord || !sessionId
                ? "not-allowed"
                : "pointer",
            background: buttonBackground,
            color: "#fff",
            minWidth: 280,
            fontWeight: 900,
            touchAction: "manipulation",
            userSelect: "none",
            WebkitUserSelect: "none",
            boxShadow:
              isProcessing || !canRecord
                ? "none"
                : "0 16px 36px rgba(255, 56, 28, 0.32)",
            opacity: isProcessing || !canRecord || !sessionId ? 0.72 : 1,
          }}
        >
          {buttonLabel}
        </button>

        {pendingAudioSrc && (
          <button
            type="button"
            onClick={handlePlayPendingAudio}
            style={{
              border: "1px solid rgba(255, 255, 255, 0.2)",
              borderRadius: 999,
              padding: "14px 22px",
              background: "rgba(255, 255, 255, 0.13)",
              color: "#ffffff",
              fontSize: 18,
              fontWeight: 900,
            }}
          >
            Odtwórz odpowiedź
          </button>
        )}

        <p
          style={{
            minHeight: 48,
            maxWidth: 360,
            margin: 0,
            fontSize: 16,
            lineHeight: 1.4,
            color: connectionError ? "#fecaca" : "rgba(255, 255, 255, 0.82)",
            fontWeight: 700,
          }}
        >
          {connectionError || statusText}
        </p>
      </div>
    </main>
  );
}

export default function PhonePage() {
  return (
    <Suspense fallback={null}>
      <PhonePageContent />
    </Suspense>
  );
}