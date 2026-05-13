"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Avatar from "../../components/Avatar";
import VoiceWave from "../../components/VoiceWave";
import { useAudioRecorder } from "../../hooks/useAudioRecorder";
import {
  buildAudioSrc,
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

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isRecordingTurnRef = useRef(false);

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
      setStatusText(
        "Połączono z TV. Kliknij przycisk, powiedz pytanie i kliknij drugi raz, żeby wysłać."
      );
    } else if (status.queue_position) {
      setStatusText(`Jesteś w kolejce. Twoje miejsce: ${status.queue_position}.`);
    } else {
      setStatusText("Erion odpowiada. Poczekaj chwilę.");
    }
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

      stopAudioPlayback();
      void cleanupAudioResources();
    };
  }, [isTvMicMode, tvSessionId]);

  const startTurn = async () => {
    if (isRecordingTurnRef.current || isProcessing || !canRecord || !sessionId) {
      return;
    }

    isRecordingTurnRef.current = true;
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

      setStatusText("Nie udało się włączyć mikrofonu. Upewnij się, że strona działa po HTTPS.");
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
        setStatusText("Odpowiedź Eriona odtworzy się na TV.");
        setAvatarState("waiting");

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

  const buttonColor = isRecording
    ? "#dc2626"
    : isProcessing || !canRecord
    ? "#b9b9b9"
    : "#2d6a4f";

  if (isTvMicMode) {
    return (
      <main
        style={{
          minHeight: "100vh",
          background: "#f5f5f5",
          color: "#111827",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: 24,
          boxSizing: "border-box",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 420,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 24,
            textAlign: "center",
          }}
        >
          <div>
            <h1
              style={{
                fontSize: 34,
                margin: 0,
                fontWeight: 800,
              }}
            >
              Mikrofon TV
            </h1>

            <p
              style={{
                margin: "10px 0 0",
                fontSize: 17,
                lineHeight: 1.4,
                color: "#4b5563",
              }}
            >
              Ten telefon działa jako mikrofon do rozmowy z Erionem na ekranie TV.
              Odpowiedź pojawi się głosowo na TV.
            </p>
          </div>

          <div
            style={{
              width: 118,
              height: 118,
              borderRadius: "50%",
              background: isRecording ? "#dc2626" : canRecord ? "#111827" : "#d1d5db",
              color: "#ffffff",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 48,
              boxShadow: isRecording
                ? "0 0 0 14px rgba(220, 38, 38, 0.18)"
                : "0 20px 45px rgba(15, 23, 42, 0.18)",
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
              borderRadius: 18,
              border: "none",
              cursor:
                isProcessing || !canRecord || !sessionId ? "not-allowed" : "pointer",
              background: buttonColor,
              color: "#fff",
              minWidth: 280,
              fontWeight: 800,
              touchAction: "manipulation",
              userSelect: "none",
              WebkitUserSelect: "none",
            }}
          >
            {buttonLabel}
          </button>

          <p
            style={{
              minHeight: 52,
              maxWidth: 360,
              margin: 0,
              fontSize: 18,
              lineHeight: 1.4,
              color: connectionError ? "#b91c1c" : "#111827",
            }}
          >
            {connectionError || statusText}
          </p>

          {queuePosition && !canRecord && (
            <div
              style={{
                padding: "12px 16px",
                borderRadius: 16,
                background: "#fef3c7",
                color: "#92400e",
                fontWeight: 700,
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
    <main
      style={{
        minHeight: "100vh",
        background: "#f5f5f5",
        color: "#111827",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        boxSizing: "border-box",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        style={{
          width: "100%",
          maxWidth: 520,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 18,
          textAlign: "center",
        }}
      >
        <h1 style={{ fontSize: 30, margin: 0, fontWeight: 800 }}>{pageTitle}</h1>

        <Avatar state={avatarState} variant="phone" size="phone" />

        <VoiceWave visible={isRecording} volumeLevel={volumeLevel} />

        <button
          type="button"
          disabled={isProcessing || !canRecord || !sessionId}
          onClick={handleMainButtonClick}
          style={{
            padding: "18px 28px",
            fontSize: 22,
            borderRadius: 18,
            border: "none",
            cursor:
              isProcessing || !canRecord || !sessionId ? "not-allowed" : "pointer",
            background: buttonColor,
            color: "#fff",
            minWidth: 280,
            fontWeight: 800,
            touchAction: "manipulation",
            userSelect: "none",
            WebkitUserSelect: "none",
          }}
        >
          {buttonLabel}
        </button>

        {pendingAudioSrc && (
          <button
            type="button"
            onClick={handlePlayPendingAudio}
            style={{
              border: "none",
              borderRadius: 999,
              padding: "14px 22px",
              background: "#111827",
              color: "#ffffff",
              fontSize: 18,
              fontWeight: 800,
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
            color: connectionError ? "#b91c1c" : "#111827",
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