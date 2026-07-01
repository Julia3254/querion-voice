"use client";

import { useMemo } from "react";
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

const fallbackState: Record<AvatarState, AvatarState> = {
  waiting: "waiting",
  listening: "listening",
  thinking: "thinking",
  speaking: "speaking",
};

function avatarSrc(variant: AvatarVariant, state: AvatarState) {
  return `/avatar/${variant}/${fallbackState[state]}.webp`;
}

export default function Avatar({
  state,
  variant = "phone",
  size = "phone",
}: Props) {
  const maxWidth = size === "tv" ? 620 : 320;

  const sources = useMemo(() => {
    return avatarStates.map((avatarState) => ({
      state: avatarState,
      src: avatarSrc(variant, avatarState),
    }));
  }, [variant]);

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        maxWidth,
        aspectRatio: "1 / 1",
      }}
    >
      {sources.map(({ state: avatarState, src }) => {
        const isActive = avatarState === state;

        return (
          <img
            key={avatarState}
            src={src}
            alt=""
            aria-hidden="true"
            draggable={false}
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "contain",
              display: "block",
              opacity: isActive ? 1 : 0,
              transition: "opacity 160ms ease",
              pointerEvents: "none",
              userSelect: "none",
            }}
          />
        );
      })}
    </div>
  );
}