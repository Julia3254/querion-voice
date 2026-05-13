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

export default function TvClient({
  sessionId,
  initialState,
  pairingUrl,
  phoneUrl,
  setupError = "",
}: TvClientProps) {
  const [avatarState, setAvatarState] = useState<AvatarState>(initialState);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [, setStatusText] = useState("Gotowy do rozmowy.");
  const [pendingAudio, setPendingAudio] = useState<{
    id: number;
    url: string;
  } | null>(null);

  const [browserOrigin, setBrowserOrigin] = useState("");

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const lastPlayedResponseIdRef = useRef(0);
  const lastActivityAtRef = useRef(0);
  const idleRequestInFlightRef = useRef(false);
  const idleCooldownMs = 25000;

  useEffect(() => {
    lastActivityAtRef.current = Date.now();
    setBrowserOrigin(window.location.origin);
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
    lastActivityAtRef.current = Date.now();

    if (!isIdle) {
      lastPlayedResponseIdRef.current = responseId;
      setPendingAudio(null);
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
      return;
    }

    stopAudioPlayback();

    const audio = new Audio(resolvedAudioUrl);
    audioRef.current = audio;
    isPlayingRef.current = true;

    lastActivityAtRef.current = Date.now();
    setAvatarState("speaking");
    setStatusText(
      isIdle ? "Erion zaprasza do rozmowy..." : "Erion odpowiada..."
    );

    audio.onplay = () => {
      setAvatarState("speaking");
      setStatusText(
        isIdle ? "Erion zaprasza do rozmowy..." : "Erion odpowiada..."
      );
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
        setPendingAudio({ id: responseId, url: audioUrl });
        setStatusText("Odpowiedź gotowa. Kliknij „Odtwórz odpowiedź”.");
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
        setPendingAudio({ id: responseId, url: audioUrl });
        setStatusText("Kliknij „Odtwórz odpowiedź”.");
      } else {
        void finishResponse(sessionId, responseId, true);
      }
    }
  };

  const handleEnableSound = async () => {
    setSoundEnabled(true);
    setStatusText("Dźwięk TV włączony.");

    if (pendingAudio) {
      await playTvAudio(pendingAudio.url, pendingAudio.id);
    }
  };

  const handlePlayPending = async () => {
    if (!pendingAudio) {
      return;
    }

    setSoundEnabled(true);
    await playTvAudio(pendingAudio.url, pendingAudio.id);
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
            setStatusText("Erion słucha...");
          } else if (status.state === "thinking") {
            setAvatarState("thinking");
            setStatusText("Erion myśli...");
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
          if (!soundEnabled) {
            setPendingAudio({
              id: status.response_id,
              url: status.answer_audio_url,
            });
            setAvatarState("speaking");
            setStatusText("Odpowiedź gotowa. Kliknij „Odtwórz odpowiedź”.");
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
      stopAudioPlayback();
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
        pendingAudio ||
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
  }, [sessionId, soundEnabled, avatarState, pendingAudio]);

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

  return (
    <main
      style={{
        position: "fixed",
        inset: 0,
        width: "100vw",
        height: "100svh",
        overflow: "hidden",
        background: "#f5f5f5",
        color: "#0f172a",
        fontFamily: "Arial, sans-serif",
        boxSizing: "border-box",
        padding: "10px 18px 14px",
      }}
    >
      <style jsx global>{`
        html,
        body {
          overflow: hidden !important;
          background: #f5f5f5 !important;
        }
      `}</style>

      <div
        style={{
          width: "100%",
          height: "100%",
          maxWidth: 1360,
          margin: "0 auto",
          display: "grid",
          gridTemplateRows: "auto minmax(0, 1fr) auto",
          gap: 8,
          alignItems: "stretch",
        }}
      >
        <header
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto auto",
            alignItems: "center",
            gap: 18,
            minHeight: 132,
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "auto auto",
              alignItems: "center",
              justifyContent: "center",
              gap: 18,
            }}
          >
            <div style={{ textAlign: "right" }}>
              <h1
                style={{
                  margin: 0,
                  fontSize: "clamp(30px, 3.2vw, 54px)",
                  fontWeight: 900,
                  letterSpacing: "-0.035em",
                  lineHeight: 1.02,
                }}
              >
                Porozmawiaj z Erionem!
              </h1>

              <div
                style={{
                  marginTop: 8,
                  fontSize: "clamp(15px, 1.45vw, 23px)",
                  fontWeight: 700,
                  lineHeight: 1.15,
                }}
              >
                Zeskanuj i użyj telefonu
                <br />
                jako mikrofonu
              </div>
            </div>

            <div
              style={{
                width: 112,
                height: 112,
                borderRadius: 16,
                background: "#ffffff",
                boxShadow: "0 8px 24px rgba(15, 23, 42, 0.09)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {renderQr(safePairingUrl, 88)}
            </div>
          </div>

          <div style={{ flex: 1 }} />

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
              flexWrap: "wrap",
            }}
          >
            <button
              type="button"
              onClick={handleEnableSound}
              style={{
                border: "none",
                borderRadius: 999,
                padding: "9px 14px",
                background: soundEnabled ? "#4caf50" : "#111827",
                color: "#ffffff",
                fontSize: 13,
                fontWeight: 800,
                cursor: "pointer",
                whiteSpace: "nowrap",
              }}
            >
              {soundEnabled ? "Dźwięk włączony" : "Włącz dźwięk"}
            </button>

            {pendingAudio && (
              <button
                type="button"
                onClick={handlePlayPending}
                style={{
                  border: "none",
                  borderRadius: 999,
                  padding: "9px 14px",
                  background: "#2563eb",
                  color: "#ffffff",
                  fontSize: 13,
                  fontWeight: 800,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
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
              width: "min(74vw, 820px)",
              height: "100%",
              maxHeight: "calc(100svh - 310px)",
              minHeight: 260,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "transparent",
              borderRadius: 0,
              boxShadow: "none",
            }}
          >
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                background: "transparent",
              }}
            >
              <Avatar state={avatarState} variant="tv" size="tv" />
            </div>
          </div>
        </section>

        <footer
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: 138,
            borderTop: "1px solid #d4d4d8",
            paddingTop: 10,
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "auto auto",
              alignItems: "center",
              gap: 18,
            }}
          >
            <h2
              style={{
                margin: 0,
                fontSize: "clamp(24px, 2.5vw, 44px)",
                fontWeight: 900,
                letterSpacing: "-0.035em",
                lineHeight: 1.05,
                textAlign: "right",
              }}
            >
              Zabierz Querę ze sobą
              <br />
              na spacer
            </h2>

            <div
              style={{
                width: 118,
                height: 118,
                borderRadius: 16,
                background: "#ffffff",
                boxShadow: "0 8px 24px rgba(15, 23, 42, 0.09)",
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