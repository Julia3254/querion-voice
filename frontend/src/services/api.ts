import type {
  AvatarState,
  CreateSessionResponse,
  JoinTvSessionResponse,
  QueueStatusResponse,
  SessionEvent,
  SessionResponseStatus,
  VoiceResponse,
  VoiceTarget,
} from "../types/api";

function cleanBaseUrl(url: string) {
  return url.trim().replace(/\/$/, "");
}

export function apiBaseUrl() {
  const envUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (envUrl && envUrl.trim()) {
    return cleanBaseUrl(envUrl);
  }

  return "/api/backend";
}

function wsBaseUrl() {
  const envUrl = process.env.NEXT_PUBLIC_WS_BASE_URL;

  if (envUrl && envUrl.trim()) {
    return cleanBaseUrl(envUrl);
  }

  if (typeof window === "undefined") {
    return "ws://127.0.0.1:8000";
  }

  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${window.location.hostname}:8000`;
}

function apiUrl(path: string) {
  return `${apiBaseUrl()}${path}`;
}

async function fetchJson<T>(
  path: string,
  init: RequestInit = {},
  errorMessage: string
): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 20000);

  try {
    const url = apiUrl(path);

    console.log("API request:", url);

    const response = await fetch(url, {
      ...init,
      cache: "no-store",
      signal: controller.signal,
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || errorMessage);
    }

    return response.json();
  } finally {
    clearTimeout(timeout);
  }
}

function createSafeClientId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }

  if (
    typeof crypto !== "undefined" &&
    typeof crypto.getRandomValues === "function"
  ) {
    const values = new Uint32Array(4);
    crypto.getRandomValues(values);

    return Array.from(values)
      .map((value) => value.toString(16))
      .join("-");
  }

  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function getClientId(): string {
  if (typeof window === "undefined") {
    return "server";
  }

  const key = "voice-avatar-client-id";
  const existing = window.localStorage.getItem(key);

  if (existing) {
    return existing;
  }

  const created = createSafeClientId();
  window.localStorage.setItem(key, created);

  return created;
}

export async function createPhoneSession(): Promise<CreateSessionResponse> {
  return fetchJson<CreateSessionResponse>(
    "/sessions/phone",
    { method: "POST" },
    "Nie udało się utworzyć sesji telefonu."
  );
}

export async function createTvSession(): Promise<CreateSessionResponse> {
  return fetchJson<CreateSessionResponse>(
    "/sessions/tv",
    { method: "POST" },
    "Nie udało się utworzyć sesji TV."
  );
}

export async function joinTvSession(
  sessionId: string,
  clientId: string
): Promise<JoinTvSessionResponse> {
  return fetchJson<JoinTvSessionResponse>(
    `/sessions/tv/${sessionId}/join`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId }),
    },
    "Nie udało się połączyć z TV."
  );
}

export async function getTvStatus(
  sessionId: string,
  clientId?: string
): Promise<QueueStatusResponse> {
  const path = clientId
    ? `/sessions/tv/${sessionId}/status?client_id=${encodeURIComponent(
        clientId
      )}`
    : `/sessions/tv/${sessionId}/status`;

  return fetchJson<QueueStatusResponse>(
    path,
    { method: "GET" },
    "Nie udało się pobrać statusu TV."
  );
}

export async function getSessionResponse(
  sessionId: string,
  lastResponseId: number
): Promise<SessionResponseStatus> {
  return fetchJson<SessionResponseStatus>(
    `/sessions/${sessionId}/response?last_response_id=${lastResponseId}`,
    { method: "GET" },
    "Nie udało się pobrać odpowiedzi sesji."
  );
}

export async function completeTvTurn(
  sessionId: string
): Promise<QueueStatusResponse> {
  return fetchJson<QueueStatusResponse>(
    `/sessions/tv/${sessionId}/complete`,
    { method: "POST" },
    "Nie udało się zakończyć tury TV."
  );
}

export async function setSessionState(
  sessionId: string,
  state: AvatarState,
  target?: VoiceTarget
): Promise<void> {
  await fetchJson<{ session_id: string; state: AvatarState }>(
    `/sessions/${sessionId}/state`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ state, target }),
    },
    "Nie udało się zmienić stanu sesji."
  );
}

export async function sendVoiceAudio(
  audioBlob: Blob,
  options: {
    mimeType?: string;
    sessionId?: string | null;
    target?: VoiceTarget;
    clientId?: string | null;
  } = {}
): Promise<VoiceResponse> {
  const formData = new FormData();

  const mimeType = options.mimeType ?? audioBlob.type;

  let filename = "recording.webm";

  if (mimeType?.includes("mp4")) {
    filename = "recording.mp4";
  }

  if (mimeType?.includes("mpeg")) {
    filename = "recording.mp3";
  }

  formData.append("file", audioBlob, filename);

  if (options.sessionId) {
    formData.append("session_id", options.sessionId);
  }

  if (options.target) {
    formData.append("target", options.target);
  }

  if (options.clientId) {
    formData.append("client_id", options.clientId);
  }

  const response = await fetch(apiUrl("/voice/audio"), {
    method: "POST",
    body: formData,
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Błąd podczas wysyłania audio.");
  }

  return response.json();
}

export async function getIdleVoice(
  options: { sessionId?: string | null; target?: VoiceTarget } = {}
): Promise<VoiceResponse> {
  return fetchJson<VoiceResponse>(
    "/voice/idle",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "idle",
        session_id: options.sessionId ?? null,
        target: options.target ?? "tv",
      }),
    },
    "Nie udało się pobrać zwrotu idle."
  );
}

export function backendAssetUrl(url: string | null | undefined): string | null {
  if (!url) {
    return null;
  }

  if (url.startsWith("http")) {
    return url;
  }

  if (url.startsWith("/")) {
    return `${apiBaseUrl()}${url}`;
  }

  return url;
}

export function buildAudioSrc(result: VoiceResponse): string | null {
  return backendAssetUrl(result.answer_audio_url);
}

export function connectSessionEvents(
  sessionId: string,
  onEvent: (event: SessionEvent) => void
): WebSocket {
  const socket = new WebSocket(`${wsBaseUrl()}/sessions/${sessionId}/events`);

  socket.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as SessionEvent);
    } catch {
      // Ignorujemy niepoprawne eventy.
    }
  };

  socket.onopen = () => {
    const interval = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      } else {
        window.clearInterval(interval);
      }
    }, 20000);
  };

  socket.onerror = (error) => {
    console.warn("Session WebSocket error", error);
  };

  return socket;
}