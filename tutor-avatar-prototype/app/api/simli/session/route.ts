import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const apiKey = process.env.SIMLI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "SIMLI_API_KEY not configured" },
      { status: 500 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const faceId: string =
    body?.faceId || process.env.SIMLI_FACE_ID || "tmp9i8bbq7c";

  const res = await fetch(
    "https://api.simli.ai/startAudioToVideoSession",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        apiKey,
        faceId,
        syncAudio: true,
        handleSilence: true,
        maxSessionLength: 600,
        maxIdleTime: 60,
      }),
    }
  );

  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json(
      { error: "Failed to start Simli session", detail: text },
      { status: res.status }
    );
  }

  const data = await res.json();
  return NextResponse.json({
    sessionToken: data.session_token ?? data.sessionToken ?? data.token,
    faceId,
    raw: data,
  });
}
