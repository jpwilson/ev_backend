"use client";

export type RealtimeSessionInfo = {
  client_secret: { value: string; expires_at: number };
  session_id: string;
  model: string;
  voice: string;
};

export type RealtimeHandlers = {
  onRemoteAudioTrack?: (track: MediaStreamTrack, stream: MediaStream) => void;
  onEvent?: (event: any) => void;
  onError?: (err: unknown) => void;
  onConnected?: () => void;
  onClosed?: () => void;
};

export class RealtimeClient {
  pc: RTCPeerConnection | null = null;
  dc: RTCDataChannel | null = null;
  micStream: MediaStream | null = null;
  session: RealtimeSessionInfo | null = null;
  handlers: RealtimeHandlers;

  constructor(handlers: RealtimeHandlers = {}) {
    this.handlers = handlers;
  }

  async connect(subjectId: string | null) {
    const sessRes = await fetch("/api/realtime/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ subjectId }),
    });
    if (!sessRes.ok) {
      throw new Error(`Realtime session failed: ${await sessRes.text()}`);
    }
    const session = (await sessRes.json()) as RealtimeSessionInfo;
    this.session = session;

    const pc = new RTCPeerConnection();
    this.pc = pc;

    pc.ontrack = (e) => {
      const [stream] = e.streams;
      this.handlers.onRemoteAudioTrack?.(e.track, stream);
    };

    pc.onconnectionstatechange = () => {
      if (pc.connectionState === "connected") this.handlers.onConnected?.();
      if (pc.connectionState === "closed" || pc.connectionState === "failed") {
        this.handlers.onClosed?.();
      }
    };

    const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.micStream = mic;
    for (const track of mic.getAudioTracks()) pc.addTrack(track, mic);

    pc.addTransceiver("audio", { direction: "recvonly" });

    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.onmessage = (m) => {
      try {
        this.handlers.onEvent?.(JSON.parse(m.data));
      } catch {
        // ignore
      }
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpRes = await fetch(
      `https://api.openai.com/v1/realtime?model=${encodeURIComponent(session.model)}`,
      {
        method: "POST",
        body: offer.sdp,
        headers: {
          Authorization: `Bearer ${session.client_secret.value}`,
          "Content-Type": "application/sdp",
        },
      }
    );
    if (!sdpRes.ok) {
      throw new Error(`Realtime SDP exchange failed: ${await sdpRes.text()}`);
    }
    const answer = { type: "answer" as const, sdp: await sdpRes.text() };
    await pc.setRemoteDescription(answer);
  }

  send(event: Record<string, unknown>) {
    if (this.dc?.readyState === "open") {
      this.dc.send(JSON.stringify(event));
    }
  }

  triggerGreeting(subjectName: string | null) {
    const text = subjectName
      ? `Greet the student warmly in one short sentence and ask what part of ${subjectName} they want to work on.`
      : `Greet the student warmly in one short sentence and ask what they want to learn.`;
    this.send({ type: "response.create", response: { instructions: text } });
  }

  close() {
    try {
      this.dc?.close();
    } catch {}
    try {
      this.pc?.close();
    } catch {}
    this.micStream?.getTracks().forEach((t) => t.stop());
    this.pc = null;
    this.dc = null;
    this.micStream = null;
  }
}
