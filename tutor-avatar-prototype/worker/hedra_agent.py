"""
Hedra avatar worker for the tutor prototype.

This is a LiveKit Agents worker that:
  1. Joins the LiveKit room created by the Next.js app.
  2. Subscribes to the student's published audio track (which is actually the
     GPT Realtime tutor's voice, piped through from the browser).
  3. Renders a Hedra avatar that lip-syncs to that audio and republishes
     video + audio back into the room.

Run:
  pip install -r requirements.txt
  python worker/hedra_agent.py dev

Required env vars (mirrors ../.env.local):
  LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
  HEDRA_API_KEY, HEDRA_CHARACTER_ID
"""

import os
import logging
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentSession, JobContext, WorkerOptions, cli

# `livekit-plugins-hedra` provides the Hedra avatar plugin.
# If you don't have it yet:  pip install livekit-plugins-hedra
try:
    from livekit.plugins import hedra
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "livekit-plugins-hedra is not installed. "
        "Run: pip install livekit-plugins-hedra"
    ) from e

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env.local"))
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hedra-worker")


async def entrypoint(ctx: JobContext):
    log.info("hedra worker joining room=%s", ctx.room.name)
    await ctx.connect()

    avatar = hedra.AvatarSession(
        avatar_id=os.environ["HEDRA_CHARACTER_ID"],
        api_key=os.environ["HEDRA_API_KEY"],
    )

    # AgentSession here is a passthrough: we don't run an LLM in the worker.
    # The browser already pipes GPT Realtime audio in as a published track,
    # so Hedra just lip-syncs whatever audio it receives.
    session = AgentSession()
    await avatar.start(session, room=ctx.room)
    await session.start(room=ctx.room)

    log.info("hedra avatar is live in room=%s", ctx.room.name)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
