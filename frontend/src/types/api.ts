export type AvatarState = "waiting" | "listening" | "thinking" | "speaking";

export type AvatarVariant = "phone" | "tv";

export type VoiceTarget = "phone" | "tv";

export type SessionKind = "phone" | "tv";

export type CreateSessionResponse = {
  session_id: string;
  kind: SessionKind;
  state: AvatarState;
};

export type JoinTvSessionResponse = {
  session_id: string;
  client_id: string;
  role: "active" | "queued";
  can_record: boolean;
  queue_position?: number | null;
  active_client_id?: string | null;
};

export type QueueStatusResponse = {
  session_id: string;
  state: AvatarState;
  active_client_id?: string | null;
  queue_length: number;
  queue_position?: number | null;
  can_record: boolean;
};

export type SessionResponseStatus = {
  session_id: string;
  state: AvatarState;
  response_id: number;
  answer_audio_url?: string | null;
  has_new_response: boolean;
};

export type VoiceResponse = {
  transcript?: string;
  answer_text?: string;
  answer_audio_url?: string | null;
  animation_state?: AvatarState;
  fallback_used?: boolean;
  sources?: string[];
  session_id?: string | null;
  target?: VoiceTarget;
  can_record?: boolean;
  queue_position?: number | null;
  message?: string | null;
};

export type SessionEvent =
  | {
      type: "state";
      state: AvatarState;
      target?: VoiceTarget;
    }
  | {
      type: "voice_response";
      state: AvatarState;
      target?: VoiceTarget;
      answer_audio_url?: string | null;
    }
  | {
      type: "turn_completed";
      state: AvatarState;
      active_client_id?: string | null;
      queue_length?: number;
    }
  | {
      type: "queue_updated";
      state: AvatarState;
      active_client_id?: string | null;
      queue_length?: number;
    };