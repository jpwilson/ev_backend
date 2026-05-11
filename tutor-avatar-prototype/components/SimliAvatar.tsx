"use client";

import { useEffect, useImperativeHandle, useRef, forwardRef } from "react";
// @ts-expect-error - simli-client ships its own minimal types
import { SimliClient } from "simli-client";

export type SimliAvatarHandle = {
  attachAudioTrack: (track: MediaStreamTrack) => void;
  stop: () => void;
};

type Props = {
  active: boolean;
  onStatus?: (status: string) => void;
};

const SimliAvatar = forwardRef<SimliAvatarHandle, Props>(function SimliAvatar(
  { active, onStatus },
  ref
) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const clientRef = useRef<any>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    (async () => {
      onStatus?.("Requesting Simli session…");
      const res = await fetch("/api/simli/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        onStatus?.(`Simli session error: ${await res.text()}`);
        return;
      }
      const { sessionToken } = await res.json();
      if (cancelled) return;

      const client = new SimliClient();
      clientRef.current = client;
      client.Initialize({
        apiKey: sessionToken,
        faceID: undefined,
        handleSilence: true,
        videoRef: videoRef.current,
        audioRef: audioRef.current,
      });
      await client.start();
      onStatus?.("Simli connected");
    })();

    return () => {
      cancelled = true;
      try {
        clientRef.current?.close?.();
      } catch {}
      clientRef.current = null;
      processorRef.current?.disconnect();
      processorRef.current = null;
      audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
    };
  }, [active, onStatus]);

  useImperativeHandle(
    ref,
    () => ({
      attachAudioTrack(track: MediaStreamTrack) {
        const client = clientRef.current;
        if (!client) return;

        const stream = new MediaStream([track]);
        const ctx = new AudioContext({ sampleRate: 16000 });
        audioCtxRef.current = ctx;
        const src = ctx.createMediaStreamSource(stream);
        const proc = ctx.createScriptProcessor(2048, 1, 1);
        processorRef.current = proc;
        src.connect(proc);
        proc.connect(ctx.destination);

        proc.onaudioprocess = (e) => {
          const input = e.inputBuffer.getChannelData(0);
          const pcm = new Int16Array(input.length);
          for (let i = 0; i < input.length; i++) {
            const s = Math.max(-1, Math.min(1, input[i]));
            pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }
          try {
            client.sendAudioData?.(new Uint8Array(pcm.buffer));
          } catch {
            // ignore until ready
          }
        };
      },
      stop() {
        try {
          clientRef.current?.close?.();
        } catch {}
      },
    }),
    []
  );

  return (
    <div className="relative w-full aspect-square bg-black rounded-2xl overflow-hidden border border-white/10">
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        className="w-full h-full object-cover"
      />
      <audio ref={audioRef} autoPlay />
      <div className="absolute bottom-2 left-2 px-2 py-1 text-xs bg-black/60 rounded">
        Simli (2D)
      </div>
    </div>
  );
});

export default SimliAvatar;
