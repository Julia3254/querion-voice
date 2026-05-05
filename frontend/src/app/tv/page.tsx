import { headers } from "next/headers";
import TvClient from "./TvClient";
import type { AvatarState } from "../../types/api";

export const dynamic = "force-dynamic";

type TvSessionResponse = {
  session_id: string;
  kind: string;
  state: AvatarState;
};

type TvPageData = {
  sessionId: string;
  initialState: AvatarState;
  pairingUrl: string;
  phoneUrl: string;
  setupError?: string;
};

function cleanUrl(url: string) {
  return url.trim().replace(/\/$/, "");
}

function getBackendBaseUrl() {
  const backendUrl = process.env.BACKEND_URL;

  if (backendUrl && backendUrl.trim()) {
    return cleanUrl(backendUrl);
  }

  const publicApiUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (
    publicApiUrl &&
    publicApiUrl.trim() &&
    publicApiUrl.startsWith("http")
  ) {
    return cleanUrl(publicApiUrl);
  }

  return "http://127.0.0.1:8000";
}

async function getPublicOrigin() {
  const envUrl = process.env.NEXT_PUBLIC_PUBLIC_APP_URL;

  if (envUrl && envUrl.trim()) {
    return cleanUrl(envUrl);
  }

  const headerStore = await headers();
  const host = headerStore.get("host") ?? "localhost:3000";
  const protocol = headerStore.get("x-forwarded-proto") ?? "http";

  return `${protocol}://${host}`;
}

async function createTvSessionOnServer(): Promise<TvSessionResponse> {
  const backendBaseUrl = getBackendBaseUrl();

  const response = await fetch(`${backendBaseUrl}/sessions/tv`, {
    method: "POST",
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Nie udało się utworzyć sesji TV.");
  }

  return response.json();
}

async function getTvPageData(): Promise<TvPageData> {
  const publicOrigin = await getPublicOrigin();
  const phoneUrl = `${publicOrigin}/phone`;

  try {
    const session = await createTvSessionOnServer();

    const pairingUrl = `${phoneUrl}?tvSessionId=${encodeURIComponent(
      session.session_id
    )}`;

    return {
      sessionId: session.session_id,
      initialState: session.state,
      pairingUrl,
      phoneUrl,
    };
  } catch (error) {
    console.error("Nie udało się utworzyć sesji TV:", error);

    return {
      sessionId: "",
      initialState: "waiting",
      pairingUrl: "",
      phoneUrl,
      setupError:
        "Nie mogę utworzyć sesji TV. Sprawdź, czy backend działa na porcie 8000.",
    };
  }
}

export default async function TvPage() {
  const data = await getTvPageData();

  return (
    <TvClient
      sessionId={data.sessionId}
      initialState={data.initialState}
      pairingUrl={data.pairingUrl}
      phoneUrl={data.phoneUrl}
      setupError={data.setupError}
    />
  );
}