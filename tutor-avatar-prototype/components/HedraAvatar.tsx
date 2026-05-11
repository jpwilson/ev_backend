"use client";

import { useEffect, useImperativeHandle, useRef, forwardRef, useState } from "react";
import {
  Room,
  RoomEvent,
  RemoteParticipant,
  RemoteTrack,
  RemoteTrackPublication,
  Track,
  LocalAudioTrack,
} from "livekit-client";

export type HedraAvatarHandle = {
  attachAudioTrack: (track: MediaStreamTrack) => void;
  stop: () => void;
};

type Props = {
  active: boolean;
  subjectId: string | null;
  onStatus?: (status: string) => void;
};

const HedraAvatar = forwardRef<HedraAvatarHandle, Props>(function HedraAvatar(
  { active, subjectId, onStatus },
  ref
) {
  const videoElRef = useRef<HTMLVideoElement | null>(null);
  const audioElRef = useRef<HTMLAudioElement | null>(null);
  const roomRef = useRef<Room | null>(null);
  const [agentWaiting, setAgentWaiting] = useState(true);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;

    (async () => {
      onStatus?.("Requesting LiveKit token…");
      const res = await fetch("/api/hedra/session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subjectId }),
      });
      if (!res.ok) {
        onStatus?.(`Hedra session error: ${await res.text()}`);
        return;
      }
      const { token, wsUrl, room: roomName } = await res.json();
      if (cancelled) return;

      const room = new Room({ adaptiveStream: true, dynacast: true });
      roomRef.current = room;

      room.on(RoomEvent.TrackSubscribed, (
        track: RemoteTrack,
        _pub: RemoteTrackPublication,
        participant: RemoteParticipant
      ) => {
        if (participant.identity.startsWith("hedra")) setAgentWaiting(false);
        if (track.kind === Track.Kind.Video && videoElRef.current) {
          track.attach(videoElRef.current);
        }
        if (track.kind === Track.Kind.Audio && audioElRef.current) {
          track.attach(audioElRef.current);
        }
      });

      room.on(RoomEvent.Disconnected, () => onStatus?.("LiveKit disconnected"));

      await room.connect(wsUrl, token);
      onStatus?.(`LiveKit joined: ${roomName}`);
    })();

    return () => {
      cancelled = true;
      roomRef.current?.disconnect().catch(() => {});
      roomRef.current = null;
    };
  }, [active, subjectId, onStatus]);

  useImperativeHandle(
    ref,
    () => ({
      async attachAudioTrack(track: MediaStreamTrack) {
        const room = roomRef.current;
        if (!room) return;
        const lkTrack = new LocalAudioTrack(track);
        await room.localParticipant.publishTrack(lkTrack, {
          name: "tutor-audio",
          source: Track.Source.Microphone,
        });
      },
      stop() {
        roomRef.current?.disconnect().catch(() => {});
      },
    }),
    []
  );

  return (
    <div className="relative w-full aspect-square bg-black rounded-2xl overflow-hidden border border-white/10">
      <video
        ref={videoElRef}
        autoPlay
        playsInline
        className="w-full h-full object-cover"
      />
      <audio ref={audioElRef} autoPlay />
      {agentWaiting && (
        <div className="absolute inset-0 flex items-center justify-center text-white/70 text-sm bg-black/40 text-center px-6">
          Waiting for Hedra agent worker to join the LiveKit room…
          <br />
          (run <code className="mx-1">python worker/hedra_agent.py dev</code>)
        </div>
      )}
      <div className="absolute bottom-2 left-2 px-2 py-1 text-xs bg-black/60 rounded">
        Hedra (3D · LiveKit)
      </div>
    </div>
  );
});

export default HedraAvatar;
