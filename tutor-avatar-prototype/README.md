# Tutor Avatar Prototype

Real-time AI tutoring avatar. Click a subject, talk to it.

Stack:
- **GPT Realtime** (OpenAI) — voice in, voice out, reasoning
- **Simli** (2D) or **Hedra** (3D, via LiveKit) — lip-synced talking avatar
- **Next.js 15 / React 19 / TypeScript / Tailwind** — UI + server routes
- **Langfuse** (optional) — session/event tracing

This folder is fully self-contained. Move/delete it without touching the rest of the repo.

---

## Architecture

```
 Browser  ── mic ──▶ GPT Realtime (WebRTC)
    ▲                       │
    │                       ▼  tutor audio track
    │                  ┌─────────────┐
    │ video/audio ◀────┤  Simli      │  (in-browser SDK)
    │                  └─────────────┘
    │                  ┌─────────────┐
    │ video/audio ◀────┤  Hedra      │  (LiveKit room + Python worker)
    │                  └─────────────┘
```

The OpenAI Realtime WebRTC connection is owned by the browser. The remote audio
track from OpenAI is forked two ways: it plays directly to the user, and it
also gets handed to whichever avatar provider is active for lip-sync.

For **Simli**, the SDK runs in-browser — no extra process.
For **Hedra**, the browser publishes the tutor audio into a LiveKit room, and a
separate Python worker (`worker/hedra_agent.py`) joins the same room as the
Hedra avatar agent and renders the video.

---

## Setup

### 1. Install deps

```bash
cd tutor-avatar-prototype
npm install
```

### 2. Configure env

```bash
cp .env.local.example .env.local
```

Fill in:

| Var | Required for | Where to get it |
| --- | --- | --- |
| `OPENAI_API_KEY` | Realtime brain | platform.openai.com |
| `OPENAI_REALTIME_MODEL` | Realtime brain | default `gpt-realtime` is fine |
| `SIMLI_API_KEY` | Simli avatar | simli.com dashboard |
| `SIMLI_FACE_ID` | Simli avatar | pick from docs, or upload your own |
| `LIVEKIT_URL` / `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` | Hedra | cloud.livekit.io |
| `HEDRA_API_KEY` / `HEDRA_CHARACTER_ID` | Hedra worker | hedra.com |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | tracing (optional) | langfuse.com |

### 3. Run the web app

```bash
npm run dev
# http://localhost:3000
```

### 4. (Hedra only) Run the avatar worker

In a second terminal:

```bash
cd tutor-avatar-prototype/worker
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python hedra_agent.py dev
```

The worker auto-joins any room created by the Next.js app and renders the Hedra
avatar into it. If you don't run the worker, the Hedra panel will show a
"waiting for agent" overlay.

---

## Usage

1. Open `http://localhost:3000`.
2. Choose **Simli** or **Hedra** (top right).
3. Click any of the 20 subject buttons.
4. The browser will ask for mic access, then connect to GPT Realtime and the
   avatar in parallel. You should see the avatar speak a short greeting.
5. Talk. Interrupt. Switch subjects. Click **End session** to disconnect.

---

## Cost guardrails

The proposal calls for a $5–$10/session cap during testing. There's no
single platform-wide limit you can set — apply them per-vendor:

- **OpenAI**: set a monthly cap in *Billing → Usage limits* (e.g., $50).
- **Simli**: dashboard *Settings → Spend limit*.
- **Hedra**: dashboard *Billing → Usage cap*.
- **LiveKit**: dashboard *Project settings → Bandwidth alerts*.

The app also limits each Simli session to 600 s and 60 s idle (see
`app/api/simli/session/route.ts`).

---

## Tracing (Langfuse)

If you set `LANGFUSE_PUBLIC_KEY` + `LANGFUSE_SECRET_KEY`, the client pings
`/api/langfuse/trace` on lifecycle events (`session.start`,
`provider.toggle`, `oai.response.done`, etc.) so you get a per-session timeline.
Leave the keys blank to disable.
