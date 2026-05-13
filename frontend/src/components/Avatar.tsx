"use client";

import type { AvatarState, AvatarVariant } from "../types/api";

type Props = {
  state: AvatarState;
  variant?: AvatarVariant;
  size?: "phone" | "tv";
};

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
      }}
    >
      <video
        key={`${variant}-${state}`}
        src={videoSrc(variant, state)}
        autoPlay
        loop
        muted
        playsInline
        preload="auto"
        style={{
          width: "100%",
          height: "100%",
          objectFit: "contain",
          display: "block",
          background: "transparent",
        }}
      />
    </div>
  );
}