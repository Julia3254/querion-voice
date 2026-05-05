"use client";

import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import Avatar from "../../components/Avatar";
import {
  backendAssetUrl,
  completeTvTurn,
  getSessionResponse,
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

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const isPlayingRef = useRef(false);
  const lastPlayedResponseIdRef = useRef(0);

  const stopAudioPlayback = () => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.currentTime = 0;
      audioRef.current = null;
    }

    isPlayingRef.current = false;
  };

  const finishResponse = async (sid: string, responseId: number) => {
    lastPlayedResponseIdRef.current = responseId;
    setPendingAudio(null);
    setAvatarState("waiting");
    setStatusText("Gotowy do rozmowy.");

    try {
      await completeTvTurn(sid);
    } catch (error) {
      console.warn("Nie udało się zakończyć tury TV:", error);
    }
  };

  const playTvAudio = async (audioUrl: string, responseId: number) => {
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

    setAvatarState("speaking");
    setStatusText("Quera odpowiada...");

    audio.onplay = () => {
      setAvatarState("speaking");
      setStatusText("Quera odpowiada...");
    };

    audio.onended = () => {
      isPlayingRef.current = false;
      void finishResponse(sessionId, responseId);
    };

    audio.onerror = () => {
      console.warn("Błąd odtwarzania audio na TV:", resolvedAudioUrl);

      isPlayingRef.current = false;
      setAvatarState("waiting");
      setPendingAudio({ id: responseId, url: audioUrl });
      setStatusText("Odpowiedź gotowa. Kliknij „Odtwórz odpowiedź”.");
    };

    try {
      await audio.play();
    } catch (error) {
      console.warn("Autoplay zablokowany:", error);

      isPlayingRef.current = false;
      setAvatarState("waiting");
      setPendingAudio({ id: responseId, url: audioUrl });
      setStatusText("Kliknij „Odtwórz odpowiedź”.");
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
            setStatusText("Słucham...");
          } else if (status.state === "thinking") {
            setAvatarState("thinking");
            setStatusText("Myślę...");
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
            gridTemplateColumns: "1fr auto 1fr",
            alignItems: "center",
            gap: 12,
            minHeight: 132,
          }}
        >
          <div />

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "auto auto",
              alignItems: "center",
              justifyContent: "center",
              gap: 18,
            }}
          >
            <div
              style={{
                textAlign: "right",
              }}
            >
              <h1
                style={{
                  margin: 0,
                  fontSize: "clamp(30px, 3.2vw, 54px)",
                  fontWeight: 900,
                  letterSpacing: "-0.035em",
                  lineHeight: 1.02,
                }}
              >
                Porozmawiaj z Querą!
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
              {renderQr(pairingUrl, 88)}
            </div>
          </div>

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
                background: soundEnabled ? "#16a34a" : "#111827",
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
          }}
        >
          <div
            style={{
              width: "min(72vw, 760px)",
              height: "100%",
              maxHeight: "calc(100svh - 310px)",
              minHeight: 260,
              borderRadius: 28,
              overflow: "hidden",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "#ffffff",
            }}
          >
            <div
              style={{
                width: "100%",
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
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
              Zabierz Eriona ze sobą
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
              {renderQr(phoneUrl, 92)}
            </div>
          </div>
        </footer>
      </div>
    </main>
  );
}