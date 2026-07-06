"use client";

import { useEffect, useState } from "react";

import { WIFI_ACCESS_DENIED_EVENT, apiBaseUrl } from "../services/api";

type AccessStatus = {
  enabled?: boolean;
  allowed?: boolean;
  client_ip?: string | null;
  allowed_cidrs?: string[];
};

const DEFAULT_MESSAGE = "Aby korzystać z aplikacji, połącz się z WiFi Quera.";

export default function WifiAccessPopup() {
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [clientIp, setClientIp] = useState<string | null>(null);
  const [isChecking, setIsChecking] = useState(false);

  const checkAccessStatus = async () => {
    try {
      setIsChecking(true);

      const response = await fetch(`${apiBaseUrl()}/access/status`, {
        method: "GET",
        cache: "no-store",
      });

      if (!response.ok) {
        return;
      }

      const data = (await response.json()) as AccessStatus;

      if (data.enabled && !data.allowed) {
        setClientIp(data.client_ip ?? null);
        setMessage(DEFAULT_MESSAGE);
        setVisible(true);
        return;
      }

      if (data.enabled && data.allowed) {
        setVisible(false);
      }
    } catch {
    } finally {
      setIsChecking(false);
    }
  };

  useEffect(() => {
    const showPopup = (event: Event) => {
      const customEvent = event as CustomEvent<{ message?: string }>;

      setMessage(customEvent.detail?.message || DEFAULT_MESSAGE);
      setVisible(true);
    };

    window.addEventListener(WIFI_ACCESS_DENIED_EVENT, showPopup as EventListener);

    void checkAccessStatus();

    return () => {
      window.removeEventListener(
        WIFI_ACCESS_DENIED_EVENT,
        showPopup as EventListener,
      );
    };
  }, []);

  if (!visible) {
    return null;
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 99999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 20,
        background: "rgba(0, 0, 0, 0.72)",
        backdropFilter: "blur(10px)",
        fontFamily: "Arial, sans-serif",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="wifi-access-title"
        style={{
          width: "100%",
          maxWidth: 420,
          borderRadius: 28,
          padding: "28px 24px",
          background:
            "linear-gradient(135deg, rgba(20, 20, 28, 0.98), rgba(66, 22, 14, 0.98))",
          color: "#ffffff",
          border: "1px solid rgba(255, 255, 255, 0.18)",
          boxShadow: "0 24px 80px rgba(0, 0, 0, 0.45)",
          textAlign: "center",
        }}
      >
        <div
          style={{
            width: 62,
            height: 62,
            margin: "0 auto 18px",
            borderRadius: "50%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(255, 74, 28, 0.18)",
            border: "1px solid rgba(255, 74, 28, 0.45)",
            fontSize: 30,
          }}
        >
          WiFi
        </div>

        <h2
          id="wifi-access-title"
          style={{
            margin: "0 0 12px",
            fontSize: 24,
            lineHeight: 1.2,
            fontWeight: 900,
          }}
        >
          Połącz się z WiFi Quera
        </h2>

        <p
          style={{
            margin: "0 0 18px",
            fontSize: 16,
            lineHeight: 1.5,
            color: "rgba(255, 255, 255, 0.86)",
          }}
        >
          {message}
        </p>

        {clientIp && (
          <p
            style={{
              margin: "0 0 18px",
              fontSize: 12,
              lineHeight: 1.4,
              color: "rgba(255, 255, 255, 0.56)",
              wordBreak: "break-word",
            }}
          >
            Wykryte IP: {clientIp}
          </p>
        )}

        <button
          type="button"
          onClick={() => void checkAccessStatus()}
          disabled={isChecking}
          style={{
            width: "100%",
            border: 0,
            borderRadius: 999,
            padding: "15px 18px",
            background: isChecking
              ? "rgba(255, 255, 255, 0.22)"
              : "linear-gradient(135deg, #ff4a1c 0%, #ff1c2d 100%)",
            color: "#ffffff",
            fontSize: 16,
            fontWeight: 900,
            cursor: isChecking ? "default" : "pointer",
            boxShadow: "0 14px 34px rgba(255, 28, 45, 0.28)",
          }}
        >
          {isChecking ? "Sprawdzam..." : "Sprawdź ponownie"}
        </button>

        <p
          style={{
            margin: "14px 0 0",
            fontSize: 12,
            lineHeight: 1.4,
            color: "rgba(255, 255, 255, 0.55)",
          }}
        >
          Po połączeniu z WiFi Quera kliknij „Sprawdź ponownie”.
        </p>
      </div>
    </div>
  );
}