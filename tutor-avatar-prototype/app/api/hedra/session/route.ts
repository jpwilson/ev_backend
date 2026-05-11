import { NextRequest, NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";
import { randomUUID } from "node:crypto";

export const runtime = "nodejs";

export async function POST(req: NextRequest) {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const wsUrl = process.env.LIVEKIT_URL;

  if (!apiKey || !apiSecret || !wsUrl) {
    return NextResponse.json(
      {
        error:
          "LIVEKIT_API_KEY / LIVEKIT_API_SECRET / LIVEKIT_URL not configured",
      },
      { status: 500 }
    );
  }

  const body = await req.json().catch(() => ({}));
  const subjectId: string = body?.subjectId || "general";
  const room = `tutor-${subjectId}-${randomUUID().slice(0, 8)}`;
  const identity = `student-${randomUUID().slice(0, 8)}`;

  const at = new AccessToken(apiKey, apiSecret, {
    identity,
    ttl: 60 * 30,
  });
  at.addGrant({
    room,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  });

  const token = await at.toJwt();

  return NextResponse.json({
    token,
    wsUrl,
    room,
    identity,
    subjectId,
    hedraCharacterId:
      body?.characterId || process.env.HEDRA_CHARACTER_ID || null,
  });
}
