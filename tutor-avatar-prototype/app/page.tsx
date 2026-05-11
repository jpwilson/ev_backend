"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import SubjectGrid from "@/components/SubjectGrid";
import ProviderToggle, { type Provider } from "@/components/ProviderToggle";
import SimliAvatar, { type SimliAvatarHandle } from "@/components/SimliAvatar";
import HedraAvatar, { type HedraAvatarHandle } from "@/components/HedraAvatar";
import { RealtimeClient } from "@/lib/realtime-client";
import type { Subject } from "@/lib/subjects";

type Status = "idle" | "connecting" | "live" | "error";

export default function Page() {
  const [provider, setProvider] = useState<Provider>("simli");
  const [subject, setSubject] = useState<Subject | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [statusMsg, setStatusMsg] = useState<string>("");

  const rtRef = useRef<RealtimeClient | null>(null);
  const simliRef = useRef<SimliAvatarHandle | null>(null);
  const hedraRef = useRef<HedraAvatarHandle | null>(null);
  const tutorAudioElRef = useRef<HTMLAudioElement | null>(null);

  const sessionIdRef = useRef<string>(
    `s-${Math.random().toString(36).slice(2, 10)}`
  );

  const trace = useCallback(
    (event: string, payload: Record<string, unknown> = {}) => {
      fetch("/api/langfuse/trace", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: sessionIdRef.current,
          subjectId: subject?.id,
          provider,
          event,
          payload,
        }),
      }).catch(() => {});
    },
    [provider, subject]
  );

  const stopAll = useCallback(() => {
    rtRef.current?.close();
    rtRef.current = null;
    simliRef.current?.stop();
    hedraRef.current?.stop();
    setStatus("idle");
    setStatusMsg("");
  }, []);

  const startSession = useCallback(
    async (s: Subject) => {
      stopAll();
      setSubject(s);
      setStatus("connecting");
      setStatusMsg("Connecting to GPT Realtime…");
      trace("session.start", { subject: s.id, provider });

      try {
        const rt = new RealtimeClient({
          onConnected: () => {
            setStatus("live");
            setStatusMsg(`Live · ${s.name} · ${provider}`);
            rt.triggerGreeting(s.name);
          },
          onClosed: () => setStatus("idle"),
          onError: (e) => {
            setStatus("error");
            setStatusMsg(String(e));
          },
          onRemoteAudioTrack: (track) => {
            if (tutorAudioElRef.current) {
              tutorAudioElRef.current.srcObject = new MediaStream([track]);
            }
            if (provider === "simli") {
              simliRef.current?.attachAudioTrack(track);
            } else {
              hedraRef.current?.attachAudioTrack(track);
            }
          },
          onEvent: (ev) => {
            if (
              ev?.type === "response.done" ||
              ev?.type === "input_audio_buffer.speech_started"
            ) {
              trace(`oai.${ev.type}`, { id: ev.event_id });
            }
          },
        });
        rtRef.current = rt;
        await rt.connect(s.id);
      } catch (e) {
        setStatus("error");
        setStatusMsg((e as Error).message);
      }
    },
    [provider, stopAll, trace]
  );

  useEffect(() => {
    return () => stopAll();
  }, [stopAll]);

  return (
    <main className="min-h-screen p-6 max-w-6xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold">Tutor Avatar Prototype</h1>
          <p className="text-white/60 text-sm">
            GPT Realtime · Simli / Hedra avatar · pick a subject to begin
          </p>
        </div>
        <div className="flex items-center gap-3">
          <ProviderToggle
            value={provider}
            onChange={(p) => {
              setProvider(p);
              trace("provider.toggle", { to: p });
            }}
            disabled={status === "connecting"}
          />
          {status !== "idle" && (
            <button
              onClick={() => {
                trace("session.end");
                stopAll();
              }}
              className="px-3 py-1.5 text-sm rounded-full bg-red-500/80 hover:bg-red-500"
            >
              End session
            </button>
          )}
        </div>
      </header>

      <section className="grid md:grid-cols-[1fr_2fr] gap-6 mb-6">
        <div className="space-y-2">
          {provider === "simli" ? (
            <SimliAvatar
              ref={simliRef}
              active={status !== "idle"}
              onStatus={setStatusMsg}
            />
          ) : (
            <HedraAvatar
              ref={hedraRef}
              active={status !== "idle"}
              subjectId={subject?.id ?? null}
              onStatus={setStatusMsg}
            />
          )}
          <audio ref={tutorAudioElRef} autoPlay />
        </div>
        <div className="rounded-2xl border border-white/10 bg-panel p-4 text-sm">
          <div className="font-medium mb-1">
            {subject ? `${subject.emoji} ${subject.name}` : "Pick a subject"}
          </div>
          <div className="text-white/60">
            {subject?.blurb ??
              "Twenty subjects below. Click one to start a live tutoring session."}
          </div>
          <div className="mt-4 text-xs text-white/50">
            Status: <span className="text-white/80">{status}</span>
            {statusMsg && <> · {statusMsg}</>}
          </div>
        </div>
      </section>

      <section>
        <h2 className="text-sm uppercase tracking-wider text-white/50 mb-3">
          Subjects
        </h2>
        <SubjectGrid
          selectedId={subject?.id ?? null}
          onSelect={startSession}
          disabled={status === "connecting"}
        />
      </section>
    </main>
  );
}
