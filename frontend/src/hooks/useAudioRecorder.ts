import { useRef, useState } from "react";

export function useAudioRecorder() {
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const mimeTypeRef = useRef("audio/webm");

  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationFrameRef = useRef<number | null>(null);

  const isRecordingRef = useRef(false);

  const [isRecording, setIsRecording] = useState(false);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [mimeType, setMimeType] = useState("audio/webm");

  const stopVisualLoop = () => {
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }
  };

  const cleanupAudioResources = async () => {
    stopVisualLoop();

    if (audioContextRef.current) {
      try {
        await audioContextRef.current.close();
      } catch {}
      audioContextRef.current = null;
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    analyserRef.current = null;
    mediaRecorderRef.current = null;
    audioChunksRef.current = [];
    isRecordingRef.current = false;

    setIsRecording(false);
    setVolumeLevel(0);
  };

  const updateVolume = () => {
    const analyser = analyserRef.current;

    if (!analyser) {
      return;
    }

    const dataArray = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteFrequencyData(dataArray);

    let sum = 0;

    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }

    const average = sum / dataArray.length;
    const normalized = Math.min(100, Math.max(0, Math.round(average / 1.8)));

    setVolumeLevel(normalized);
    animationFrameRef.current = requestAnimationFrame(updateVolume);
  };

  const getSupportedMimeType = () => {
    if (typeof MediaRecorder === "undefined") {
      return "";
    }

    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      return "audio/webm;codecs=opus";
    }

    if (MediaRecorder.isTypeSupported("audio/webm")) {
      return "audio/webm";
    }

    if (MediaRecorder.isTypeSupported("audio/mp4")) {
      return "audio/mp4";
    }

    return "";
  };

  const startRecording = async () => {
    if (isRecordingRef.current) {
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    streamRef.current = stream;

    const supportedMimeType = getSupportedMimeType();
    mimeTypeRef.current = supportedMimeType || "audio/webm";
    setMimeType(mimeTypeRef.current);

    const mediaRecorder = supportedMimeType
      ? new MediaRecorder(stream, { mimeType: supportedMimeType })
      : new MediaRecorder(stream);

    mediaRecorderRef.current = mediaRecorder;
    audioChunksRef.current = [];

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunksRef.current.push(event.data);
      }
    };

    const AudioContextClass =
      window.AudioContext ||
      (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;

    if (AudioContextClass) {
      const audioContext = new AudioContextClass();
      audioContextRef.current = audioContext;

      if (audioContext.state === "suspended") {
        await audioContext.resume();
      }

      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();

      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.85;

      source.connect(analyser);
      analyserRef.current = analyser;

      updateVolume();
    }

    isRecordingRef.current = true;
    setIsRecording(true);
    setVolumeLevel(0);

    mediaRecorder.start();
  };

  const stopRecording = (): Promise<Blob | null> => {
    return new Promise((resolve) => {
      const mediaRecorder = mediaRecorderRef.current;

      if (!mediaRecorder || !isRecordingRef.current) {
        resolve(null);
        return;
      }

      mediaRecorder.onstop = async () => {
        const blob =
          audioChunksRef.current.length > 0
            ? new Blob(audioChunksRef.current, { type: mimeTypeRef.current })
            : null;

        await cleanupAudioResources();
        resolve(blob);
      };

      if (mediaRecorder.state !== "inactive") {
        mediaRecorder.stop();
      } else {
        void cleanupAudioResources().then(() => resolve(null));
      }
    });
  };

  return {
    isRecording,
    volumeLevel,
    mimeType,
    startRecording,
    stopRecording,
    cleanupAudioResources,
  };
}