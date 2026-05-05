type VoiceWaveProps = {
  volumeLevel: number;
  visible: boolean;
};

export default function VoiceWave({ volumeLevel, visible }: VoiceWaveProps) {
  const bars = [0.45, 0.7, 1, 0.8, 0.55, 0.95, 0.65, 0.85];

  return (
    <div
      style={{
        height: 44,
        display: "flex",
        alignItems: "end",
        justifyContent: "center",
        gap: 6,
        opacity: visible ? 1 : 0.35,
        transition: "opacity 0.15s ease",
      }}
    >
      {bars.map((multiplier, index) => {
        const height = visible
          ? Math.max(8, Math.min(40, 8 + volumeLevel * 0.35 * multiplier))
          : 8;

        return (
          <div
            key={index}
            style={{
              width: 8,
              height,
              borderRadius: 999,
              background: "#1f1f1f",
              transition: "height 0.06s linear",
            }}
          />
        );
      })}
    </div>
  );
}