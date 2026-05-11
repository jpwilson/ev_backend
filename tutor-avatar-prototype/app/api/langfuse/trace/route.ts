import { NextRequest, NextResponse } from "next/server";
import { getLangfuse } from "@/lib/langfuse";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const lf = getLangfuse();
  if (!lf) return NextResponse.json({ ok: true, traced: false });

  const body = await req.json().catch(() => ({}));
  const {
    sessionId,
    subjectId,
    provider,
    event,
    payload,
  } = body as {
    sessionId?: string;
    subjectId?: string;
    provider?: "simli" | "hedra";
    event?: string;
    payload?: Record<string, unknown>;
  };

  const trace = lf.trace({
    name: "tutor-session",
    sessionId,
    metadata: { subjectId, provider, event, ...payload },
  });
  trace.event({ name: event ?? "client-event", input: payload });
  await lf.flushAsync();

  return NextResponse.json({ ok: true, traced: true });
}
