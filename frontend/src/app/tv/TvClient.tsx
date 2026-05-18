"use client";

import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import Avatar from "../../components/Avatar";
import {
  backendAssetUrl,
  completeTvTurn,
  getIdleVoice,
  getSessionResponse,
  setSessionState,
} from "../../services/api";
import type { AvatarState } from "../../types/api";

type TvClientProps = {
  sessionId: string;
  initialState: AvatarState;
  pairingUrl: string;
  phoneUrl: string;
  setupError?: string;
};

type PendingAudio = {
  id: number;
  url: string;
};

export default function TvClient({
  sessionId,
  initialState,
  pairingUrl,
  phoneUrl,
  setupError = "",
}: TvClientProps) {
  const [avatarState, setAvatarState] = useState<AvatarState>(initialState);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [statusText, setStatusText] = useState("Gotowy do rozmowy.");
  const [pendingAudio, setPendingAudio] = useState<PendingAudio | null>(null);
  const [browserOrigin, setBrowserOrigin] = useState("");

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const lastPlayedResponseIdRef = useRef(0);
  const lastActivityAtRef = useRef(0);
  const idleRequestInFlightRef = useRef(false);
  const pendingAudioRef = useRef<PendingAudio | null>(null);
  const turnSafetyTimeoutRef = useRef<number | null>(null);
  const activeResponseRef = useRef<{
    id: number;
    isIdle: boolean;
  } | null>(null);

  const idleCooldownMs = 25000;

  // TV: po 35 sekundach awaryjnie kończy turę, żeby telefon nie wisiał.
  const tvTurnSafetyMs = 35000;

  // Idle/automatyczne zaczepki kończymy szybciej.
  const idleSafetyMs = 15000;

  useEffect(() => {
    pendingAudioRef.current = pendingAudio;
  }, [pendingAudio]);

  useEffect(() => {
    lastActivityAtRef.current = Date.now();
    setBrowserOrigin(window.location.origin);

    return () => {
      clearTurnSafetyTimeout();
      stopAudioPlayback();
    };
  }, []);

  const normalizeUrlToCurrentOrigin = (url: string) => {
    if (!url || !browserOrigin) {
      return url;
    }

    try {
      const parsedUrl = new URL(url);
      const currentOrigin = new URL(browserOrigin);

      parsedUrl.protocol = currentOrigin.protocol;
      parsedUrl.host = currentOrigin.host;

      return parsedUrl.toString();
    } catch {
      return url;
    }
  };

  const safePairingUrl = normalizeUrlToCurrentOrigin(pairingUrl);
  const safePhoneUrl = normalizeUrlToCurrentOrigin(phoneUrl);

  const clearTurnSafetyTimeout = () => {
    if (turnSafetyTimeoutRef.current) {
      window.clearTimeout(turnSafetyTimeoutRef.current);
      turnSafetyTimeoutRef.current = null;
    }
  };

  const stopAudioPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }

    isPlayingRef.current = false;
  };

  const finishResponse = async (
    sid: string,
    responseId: number,
    isIdle = false
  ) => {
    clearTurnSafetyTimeout();
    activeResponseRef.current = null;
    lastActivityAtRef.current = Date.now();

    if (!isIdle) {
      lastPlayedResponseIdRef.current = responseId;
      setPendingAudio(null);
      pendingAudioRef.current = null;
    }

    setAvatarState("waiting");
    setStatusText("Gotowy do rozmowy.");

    if (isIdle) {
      try {
        await setSessionState(sid, "waiting", "tv");
      } catch {}
      return;
    }

    try {
      await completeTvTurn(sid);
    } catch (error) {
      console.warn("Nie udało się zakończyć tury TV:", error);
    }
  };

  const forceFinishResponse = async (
    sid: string,
    responseId: number,
    isIdle = false
  ) => {
    console.warn("Awaryjne zakończenie tury TV:", {
      responseId,
      isIdle,
    });

    stopAudioPlayback();
    await finishResponse(sid, responseId, isIdle);
  };

  const scheduleTurnSafetyTimeout = (responseId: number, isIdle = false) => {
    clearTurnSafetyTimeout();

    activeResponseRef.current = {
      id: responseId,
      isIdle,
    };

    turnSafetyTimeoutRef.current = window.setTimeout(() => {
      const activeResponse = activeResponseRef.current;

      if (!activeResponse || activeResponse.id !== responseId) {
        return;
      }

      void forceFinishResponse(
        sessionId,
        activeResponse.id,
        activeResponse.isIdle
      );
    }, isIdle ? idleSafetyMs : tvTurnSafetyMs);
  };

  const playTvAudio = async (
    audioUrl: string,
    responseId: number,
    isIdle = false
  ) => {
    if (!sessionId || isPlayingRef.current) {
      return;
    }

    const resolvedAudioUrl = backendAssetUrl(audioUrl);

    if (!resolvedAudioUrl) {
      setAvatarState("waiting");
      setStatusText("Brak pliku audio.");

      if (!isIdle) {
        await finishResponse(sessionId, responseId, false);
      }

      return;
    }

    stopAudioPlayback();
    scheduleTurnSafetyTimeout(responseId, isIdle);

    const audio = new Audio(resolvedAudioUrl);
    audioRef.current = audio;
    isPlayingRef.current = true;

    lastActivityAtRef.current = Date.now();
    setAvatarState("speaking");
    setStatusText(isIdle ? "Gotowy do rozmowy." : "Odpowiedź jest odtwarzana.");

    audio.onplay = () => {
      setAvatarState("speaking");
      setStatusText(isIdle ? "Gotowy do rozmowy." : "Odpowiedź jest odtwarzana.");
    };

    audio.onended = () => {
      isPlayingRef.current = false;
      void finishResponse(sessionId, responseId, isIdle);
    };

    audio.onerror = () => {
      console.warn("Błąd odtwarzania audio na TV:", resolvedAudioUrl);

      isPlayingRef.current = false;
      setAvatarState("waiting");

      if (!isIdle) {
        const nextPendingAudio = { id: responseId, url: audioUrl };
        setPendingAudio(nextPendingAudio);
        pendingAudioRef.current = nextPendingAudio;
        setStatusText("Odpowiedź gotowa. Kliknij „Odtwórz odpowiedź” na TV.");
        scheduleTurnSafetyTimeout(responseId, false);
      } else {
        void finishResponse(sessionId, responseId, true);
      }
    };

    try {
      await audio.play();
    } catch (error) {
      console.warn("Autoplay zablokowany:", error);

      isPlayingRef.current = false;
      setAvatarState("waiting");

      if (!isIdle) {
        const nextPendingAudio = { id: responseId, url: audioUrl };
        setPendingAudio(nextPendingAudio);
        pendingAudioRef.current = nextPendingAudio;
        setStatusText("Kliknij „Odtwórz odpowiedź” na TV.");
        scheduleTurnSafetyTimeout(responseId, false);
      } else {
        void finishResponse(sessionId, responseId, true);
      }
    }
  };

  const handleEnableSound = async () => {
    setSoundEnabled(true);
    setStatusText("Dźwięk TV włączony.");

    const audioToPlay = pendingAudioRef.current;

    if (audioToPlay) {
      setPendingAudio(null);
      pendingAudioRef.current = null;
      await playTvAudio(audioToPlay.url, audioToPlay.id);
    }
  };

  const handlePlayPending = async () => {
    const audioToPlay = pendingAudioRef.current;

    if (!audioToPlay) {
      return;
    }

    setSoundEnabled(true);
    setPendingAudio(null);
    pendingAudioRef.current = null;

    await playTvAudio(audioToPlay.url, audioToPlay.id);
  };

  useEffect(() => {
    if (!sessionId) {
      return;
    }

    let cancelled = false;

    const interval = window.setInterval(async () => {
      if (cancelled || isPlayingRef.current) {
        return;
      }

      try {
        const status = await getSessionResponse(
          sessionId,
          lastPlayedResponseIdRef.current
        );

        if (cancelled) {
          return;
        }

        if (!status.has_new_response) {
          if (status.state === "listening") {
            setAvatarState("listening");
            setStatusText("Pytanie jest nagrywane.");
          } else if (status.state === "thinking") {
            setAvatarState("thinking");
            setStatusText("Odpowiedź jest przygotowywana.");
          } else if (status.state === "waiting") {
            setAvatarState("waiting");
            setStatusText("Gotowy do rozmowy.");
          }
        }

        if (
          status.has_new_response &&
          status.answer_audio_url &&
          status.response_id > lastPlayedResponseIdRef.current
        ) {
          if (pendingAudioRef.current?.id === status.response_id) {
            return;
          }

          if (!soundEnabled) {
            const nextPendingAudio = {
              id: status.response_id,
              url: status.answer_audio_url,
            };

            setPendingAudio(nextPendingAudio);
            pendingAudioRef.current = nextPendingAudio;
            setAvatarState("waiting");
            setStatusText(
              "Odpowiedź gotowa. Kliknij „Włącz dźwięk i odtwórz odpowiedź” na TV."
            );
            scheduleTurnSafetyTimeout(status.response_id, false);
            return;
          }

          await playTvAudio(status.answer_audio_url, status.response_id);
        }
      } catch (error) {
        console.warn("TV polling error:", error);
      }
    }, 900);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [sessionId, soundEnabled]);

  useEffect(() => {
    if (!sessionId || !soundEnabled) {
      return;
    }

    let cancelled = false;

    const interval = window.setInterval(async () => {
      if (
        cancelled ||
        isPlayingRef.current ||
        pendingAudioRef.current ||
        avatarState !== "waiting" ||
        idleRequestInFlightRef.current
      ) {
        return;
      }

      const now = Date.now();

      if (now - lastActivityAtRef.current < idleCooldownMs) {
        return;
      }

      try {
        idleRequestInFlightRef.current = true;
        lastActivityAtRef.current = now;

        const result = await getIdleVoice({
          sessionId,
          target: "tv",
        });

        if (cancelled || !result.answer_audio_url) {
          return;
        }

        await playTvAudio(result.answer_audio_url, -1, true);
      } catch (error) {
        console.warn("TV idle error:", error);
      } finally {
        idleRequestInFlightRef.current = false;
      }
    }, 3000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [sessionId, soundEnabled, avatarState]);

  const renderQr = (value: string, size: number) => {
    if (!value) {
      return (
        <div
          style={{
            width: size,
            height: size,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            textAlign: "center",
            color: "#6b7280",
            fontSize: 12,
            padding: 8,
            boxSizing: "border-box",
          }}
        >
          {setupError || "Tworzenie QR..."}
        </div>
      );
    }

    return <QRCodeSVG value={value} size={size} marginSize={1} />;
  };

  const showSoundOverlay = !soundEnabled || Boolean(pendingAudio);

  return (
    <main
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw",
        height: "100svh",
        overflow: "hidden",
        background:
          "radial-gradient(circle at 88% 28%, rgba(255, 74, 28, 0.42), transparent 34%), radial-gradient(circle at 95% 90%, rgba(255, 28, 45, 0.24), transparent 42%), radial-gradient(circle at 15% 15%, rgba(255, 255, 255, 0.06), transparent 28%), linear-gradient(135deg, #0B0B12 0%, #151016 42%, #2A0D08 72%, #5A160B 100%)",
        color: "#ffffff",
        fontFamily: "Arial, sans-serif",
        boxSizing: "border-box",
        padding: "12px 22px 18px",
      }}
    >
      <style jsx global>{`
        html,
        body {
          overflow: hidden !important;
          background: #0b0b12 !important;
        }
      `}</style>

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

      {showSoundOverlay && (
        <div
          style={{
            position: "absolute",
            inset: 0,
            zIndex: 20,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: 24,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              width: "min(680px, 90vw)",
              borderRadius: 34,
              border: "1px solid rgba(255, 255, 255, 0.18)",
              background: "rgba(10, 10, 18, 0.78)",
              boxShadow: "0 30px 90px rgba(0, 0, 0, 0.48)",
              backdropFilter: "blur(22px)",
              padding: "30px 34px",
              textAlign: "center",
              pointerEvents: "auto",
            }}
          >
            <div
              style={{
                marginBottom: 10,
                fontSize: 13,
                fontWeight: 900,
                letterSpacing: "0.34em",
                color: "rgba(255, 255, 255, 0.5)",
                textTransform: "uppercase",
              }}
            >
              Dźwięk TV
            </div>

            <h2
              style={{
                margin: 0,
                fontSize: "clamp(30px, 4vw, 54px)",
                fontWeight: 950,
                letterSpacing: "-0.045em",
                lineHeight: 1,
                color: "#ffffff",
              }}
            >
              {pendingAudio ? "Odpowiedź jest gotowa" : "Włącz dźwięk na TV"}
            </h2>

            <p
              style={{
                margin: "14px auto 22px",
                maxWidth: 520,
                fontSize: "clamp(16px, 1.6vw, 22px)",
                lineHeight: 1.35,
                color: "rgba(255, 255, 255, 0.72)",
                fontWeight: 700,
              }}
            >
              {pendingAudio
                ? "Kliknij przycisk, żeby odtworzyć odpowiedź Eriona na ekranie TV."
                : "Przeglądarka wymaga kliknięcia na TV, zanim pozwoli odtwarzać głos."}
            </p>

            <button
              type="button"
              onClick={pendingAudio ? handlePlayPending : handleEnableSound}
              style={{
                border: "none",
                borderRadius: 999,
                padding: "18px 30px",
                background:
                  "linear-gradient(135deg, #ff4a1c 0%, #ff1c2d 100%)",
                color: "#ffffff",
                fontSize: "clamp(18px, 2vw, 26px)",
                fontWeight: 950,
                cursor: "pointer",
                whiteSpace: "nowrap",
                boxShadow: "0 18px 45px rgba(255, 56, 28, 0.38)",
              }}
            >
              {pendingAudio
                ? soundEnabled
                  ? "Odtwórz odpowiedź"
                  : "Włącz dźwięk i odtwórz odpowiedź"
                : "Włącz dźwięk"}
            </button>

            <div
              style={{
                marginTop: 16,
                fontSize: 14,
                lineHeight: 1.35,
                color: "rgba(255, 255, 255, 0.52)",
                fontWeight: 700,
              }}
            >
              Jeśli nikt nie kliknie, aplikacja awaryjnie odblokuje telefon po
              chwili.
            </div>
          </div>
        </div>
      )}

      <div
        style={{
          position: "relative",
          zIndex: 1,
          width: "100%",
          height: "100%",
          maxWidth: 1360,
          margin: "0 auto",
          display: "grid",
          gridTemplateRows: "auto minmax(0, 1fr) auto",
          gap: 10,
          alignItems: "stretch",
          filter: showSoundOverlay ? "blur(1px)" : "none",
        }}
      >
        <header
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            alignItems: "center",
            gap: 18,
            minHeight: 86,
          }}
        >
          <div>
            <div
              style={{
                marginBottom: 4,
                fontSize: "clamp(12px, 1vw, 15px)",
                fontWeight: 900,
                letterSpacing: "0.38em",
                color: "rgba(255, 255, 255, 0.48)",
                textTransform: "uppercase",
              }}
            >
              Model głosowy AI
            </div>

            <h1
              style={{
                margin: 0,
                fontSize: "clamp(34px, 4vw, 64px)",
                fontWeight: 950,
                letterSpacing: "-0.045em",
                lineHeight: 0.95,
                color: "#ffffff",
                textShadow: "0 12px 34px rgba(0, 0, 0, 0.35)",
              }}
            >
              Porozmawiaj z Erionem
            </h1>
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            {!soundEnabled && (
              <button
                type="button"
                onClick={handleEnableSound}
                style={{
                  border: "1px solid rgba(255, 255, 255, 0.25)",
                  borderRadius: 999,
                  padding: "10px 16px",
                  background: "rgba(255, 255, 255, 0.14)",
                  color: "#ffffff",
                  fontSize: 13,
                  fontWeight: 800,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  boxShadow: "0 12px 30px rgba(0, 0, 0, 0.25)",
                  backdropFilter: "blur(14px)",
                }}
              >
                Włącz dźwięk
              </button>
            )}

            {pendingAudio && (
              <button
                type="button"
                onClick={handlePlayPending}
                style={{
                  border: "none",
                  borderRadius: 999,
                  padding: "10px 16px",
                  background:
                    "linear-gradient(135deg, #ff4a1c 0%, #ff1c2d 100%)",
                  color: "#ffffff",
                  fontSize: 13,
                  fontWeight: 800,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  boxShadow: "0 12px 30px rgba(255, 56, 28, 0.35)",
                }}
              >
                Odtwórz odpowiedź
              </button>
            )}
          </div>
        </header>

        <section
          style={{
            minHeight: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
            background: "transparent",
          }}
        >
          <div
            style={{
              width: "min(76vw, 860px)",
              height: "100%",
              maxHeight: "calc(100svh - 300px)",
              minHeight: 250,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "transparent",
              borderRadius: 0,
              boxShadow: "none",
            }}
          >
            <Avatar state={avatarState} variant="tv" size="tv" />
          </div>
        </section>

        <footer
          style={{
            minHeight: 160,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 18,
            alignItems: "stretch",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto",
              alignItems: "center",
              gap: 18,
              padding: "18px 22px",
              borderRadius: 28,
              border: "1px solid rgba(255, 255, 255, 0.14)",
              background: "rgba(255, 255, 255, 0.075)",
              boxShadow: "0 18px 45px rgba(0, 0, 0, 0.24)",
              backdropFilter: "blur(18px)",
            }}
          >
            <div>
              <div
                style={{
                  marginBottom: 6,
                  fontSize: 12,
                  fontWeight: 900,
                  letterSpacing: "0.32em",
                  color: "rgba(255, 255, 255, 0.48)",
                  textTransform: "uppercase",
                }}
              >
                Mikrofon w telefonie
              </div>

              <h2
                style={{
                  margin: 0,
                  fontSize: "clamp(24px, 2.35vw, 40px)",
                  fontWeight: 950,
                  letterSpacing: "-0.04em",
                  lineHeight: 1.02,
                  color: "#ffffff",
                }}
              >
                Porozmawiaj
                <br />z Erionem
              </h2>

              <p
                style={{
                  margin: "8px 0 0",
                  fontSize: "clamp(13px, 1.1vw, 17px)",
                  fontWeight: 700,
                  lineHeight: 1.25,
                  color: "rgba(255, 255, 255, 0.66)",
                }}
              >
                Zeskanuj QR i użyj telefonu jako mikrofonu.
              </p>
            </div>

            <div
              style={{
                width: 118,
                height: 118,
                borderRadius: 18,
                background: "#ffffff",
                boxShadow: "0 18px 45px rgba(0, 0, 0, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {renderQr(safePairingUrl, 92)}
            </div>
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto",
              alignItems: "center",
              gap: 18,
              padding: "18px 22px",
              borderRadius: 28,
              border: "1px solid rgba(255, 255, 255, 0.14)",
              background: "rgba(255, 255, 255, 0.075)",
              boxShadow: "0 18px 45px rgba(0, 0, 0, 0.24)",
              backdropFilter: "blur(18px)",
            }}
          >
            <div>
              <div
                style={{
                  marginBottom: 6,
                  fontSize: 12,
                  fontWeight: 900,
                  letterSpacing: "0.32em",
                  color: "rgba(255, 255, 255, 0.48)",
                  textTransform: "uppercase",
                }}
              >
                Wersja mobilna
              </div>

              <h2
                style={{
                  margin: 0,
                  fontSize: "clamp(24px, 2.35vw, 40px)",
                  fontWeight: 950,
                  letterSpacing: "-0.04em",
                  lineHeight: 1.02,
                  color: "#ffffff",
                }}
              >
                Zabierz Querę
                <br />
                ze sobą
              </h2>

              <p
                style={{
                  margin: "8px 0 0",
                  fontSize: "clamp(13px, 1.1vw, 17px)",
                  fontWeight: 700,
                  lineHeight: 1.25,
                  color: "rgba(255, 255, 255, 0.66)",
                }}
              >
                Zeskanuj QR i przejdź do wersji na telefon.
              </p>
            </div>

            <div
              style={{
                width: 118,
                height: 118,
                borderRadius: 18,
                background: "#ffffff",
                boxShadow: "0 18px 45px rgba(0, 0, 0, 0.3)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {renderQr(safePhoneUrl, 92)}
            </div>
          </div>
        </footer>
      </div>
    </main>
  );
}