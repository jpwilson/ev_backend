import { NextRequest, NextResponse } from "next/server";
import { buildTutorInstructions, DEFAULT_VOICE } from "@/lib/prompts";
import { getSubject } from "@/lib/subjects";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY not configured" },
      { status: 500 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const subjectId: string | undefined = body?.subjectId;
  const subject = getSubject(subjectId);

  const model = process.env.OPENAI_REALTIME_MODEL || "gpt-realtime";
  const voice = body?.voice || process.env.OPENAI_REALTIME_VOICE || DEFAULT_VOICE;
  const instructions = buildTutorInstructions(subject);

  const res = await fetch("https://api.openai.com/v1/realtime/sessions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      voice,
      instructions,
      modalities: ["audio", "text"],
      turn_detection: { type: "server_vad" },
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json(
      { error: "Failed to create Realtime session", detail: text },
      { status: res.status }
    );
  }

  const data = await res.json();
  return NextResponse.json({
    client_secret: data.client_secret,
    session_id: data.id,
    model,
    voice,
    subject: subject?.id ?? null,
  });
}
