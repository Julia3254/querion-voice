"use client";

import { useEffect, useMemo, useRef } from "react";
import type { AvatarState, AvatarVariant } from "../types/api";

type Props = {
  state: AvatarState;
  variant?: AvatarVariant;
  size?: "phone" | "tv";
};

const avatarStates: AvatarState[] = [
  "waiting",
  "listening",
  "thinking",
  "speaking",
];

const fallbackState: Record<AvatarState, string> = {
  waiting: "waiting",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
};

function videoSrc(variant: AvatarVariant, state: AvatarState) {
  return `/avatar/${variant}/${fallbackState[state]}.mp4`;
}

export default function Avatar({
  state,
  variant = "phone",
  size = "phone",
}: Props) {
  const maxWidth = size === "tv" ? 620 : 320;

  const videoRefs = useRef<Partial<Record<AvatarState, HTMLVideoElement | null>>>(
    {}
  );

  const sources = useMemo(() => {
    return avatarStates.map((avatarState) => ({
      state: avatarState,
      src: videoSrc(variant, avatarState),
    }));
  }, [variant]);

  useEffect(() => {
    sources.forEach(({ state: avatarState }) => {
      const video = videoRefs.current[avatarState];

      if (!video) {
        return;
      }

      video.muted = true;
      video.playsInline = true;
      video.preload = "auto";
      video.load();
    });
  }, [sources]);

  useEffect(() => {
    avatarStates.forEach((avatarState) => {
      const video = videoRefs.current[avatarState];

      if (!video) {
        return;
      }

      if (avatarState === state) {
        video.currentTime = video.currentTime || 0;

        void video.play().catch(() => {
          // Smart TV może czasem blokować start video, ale muted zwykle działa.
        });
      } else {
        video.pause();
      }
    });
  }, [state]);

  return (
    <div
      style={{
        width: "100%",
        maxWidth,
        height: "100%",
        maxHeight: size === "tv" ? "76vh" : undefined,
        aspectRatio: "3 / 4",
        borderRadius: 0,
        overflow: "hidden",
        background: "transparent",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
      }}
    >
      {sources.map(({ state: avatarState, src }) => {
        const isActive = avatarState === state;

        return (
          <video
            key={`${variant}-${avatarState}`}
            ref={(element) => {
              videoRefs.current[avatarState] = element;
            }}
            src={src}
            autoPlay={isActive}
            loop
            muted
            playsInline
            preload="auto"
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "contain",
              display: "block",
              background: "transparent",
              opacity: isActive ? 1 : 0,
              transition: "opacity 160ms ease",
              pointerEvents: "none",
            }}
          />
        );
      })}
    </div>
  );
}