"use client";

type PushToTalkButtonProps = {
  onPressStart: () => void;
  onPressEnd: () => void;
  disabled?: boolean;
  isRecording?: boolean;
  label?: string;
};

export default function PushToTalkButton({
  onPressStart,
  onPressEnd,
  disabled = false,
  isRecording = false,
  label,
}: PushToTalkButtonProps) {
  return (
    <button
      type="button"
      disabled={disabled}
      onMouseDown={(e) => {
        e.preventDefault();
        if (!disabled) onPressStart();
      }}
      onMouseUp={(e) => {
        e.preventDefault();
        onPressEnd();
      }}
      onMouseLeave={(e) => {
        e.preventDefault();
        onPressEnd();
      }}
      onTouchStart={(e) => {
        e.preventDefault();
        if (!disabled) onPressStart();
      }}
      onTouchEnd={(e) => {
        e.preventDefault();
        onPressEnd();
      }}
      onTouchCancel={(e) => {
        e.preventDefault();
        onPressEnd();
      }}
      onContextMenu={(e) => e.preventDefault()}
      style={{
        padding: "18px 28px",
        fontSize: 19,
        borderRadius: 18,
        border: "none",
        cursor: disabled ? "not-allowed" : "pointer",
        background: disabled ? "#b9b9b9" : isRecording ? "#1f7a4f" : "#2d6a4f",
        color: "#fff",
        minWidth: 280,
        fontWeight: 700,
        touchAction: "none",
        userSelect: "none",
        WebkitUserSelect: "none",
      }}
    >
      {label ?? (isRecording ? "Mów teraz..." : "Przytrzymaj, aby mówić")}
    </button>
  );
}
