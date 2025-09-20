import os
import logging
import subprocess
import asyncio
from dotenv import load_dotenv; load_dotenv()

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.anthropic import AnthropicModel
from claude_code_sdk import query as cc_query, ClaudeCodeOptions
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default working directory now points to the swe-agent-output folder so the
# SWE agent creates and edits files that are immediately served by the
# reverse-proxied static server.
WORKDIR = Path(os.getenv("SWE_AGENT_CWD", "./swe-agent-output"))
WORKDIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are a Software Engineer.
    You are in a chat room with other humans & agents:
    - @ceo
    - @tester
    - @pm
    You can address them by using @, e.g @tester
    Otherwise you will be speaking to everyone.
    Everyone sees all messages.
    You will collaborate on a task to build a game given by the CEO.
    You will be given tasks by the @pm do not write code before you get them.

- Always acknowledge the user's request first with a brief, helpful response explaining what you're going to do.
- Then use the code_task tool to perform any coding work. You should use this once and provide the full details to implement this with a single tool call.
- After completing the coding work, provide a final summary of what was accomplished.
- A local static server is already running at http://localhost:9871 serving files
  from the swe-agent-output directory. Do not attempt to launch additional web
  servers. As you create or edit files in that directory, refresh the browser to
  see changes. When no files exist yet, the server shows a waiting page.
- Put all game code directly under the working directory (root: swe-agent-output).
  Create an index.html entry point at the root so the game loads at '/'.
- Use relative URLs for assets (./, /) so the game works behind ngrok.
- Avoid dev servers/build steps; output static assets only (HTML/CSS/JS/images).
- Do not change the working directory or write files outside it unless asked.
- Keep responses concise and focused on task completion.
"""

MODEL = AnthropicModel(model_name="claude-sonnet-4-20250514")

agent = Agent(MODEL, instructions=SYSTEM_PROMPT)

@agent.tool
async def code_task(ctx, prompt: str, permission_mode: str | None = None) -> str:
    """
    Ask Claude Code to perform coding work inside the agent repo.
    `permission_mode`: 'ask' | 'acceptEdits' | 'rejectEdits' (default 'acceptEdits').
    """
    logger.info(f"code_task called with prompt: {prompt}")
    logger.info(f"Working directory: {WORKDIR}")
    logger.info(f"Directory exists: {WORKDIR.exists()}")

    mode = permission_mode or "acceptEdits"
    logger.info(f"Permission mode: {mode}")

    try:
        # Ensure directory exists before calling Claude Code SDK
        WORKDIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created/verified directory: {WORKDIR}")

        options = ClaudeCodeOptions(
            system_prompt=SYSTEM_PROMPT,
            cwd=WORKDIR,
            permission_mode=mode,
            allowed_tools=[
                "read", "write", "edit", "multiEdit", "glob", "grep",
                "bash", "webFetch", "webSearch",
            ],
        )
        logger.info("ClaudeCodeOptions created successfully")

        out_lines: list[str] = []
        logger.info("Starting cc_query...")

        async for msg in cc_query(prompt=prompt, options=options):
            logger.info(f"Received message type: {type(msg)}")
            if isinstance(msg, dict):
                parts = msg.get("content") or []
                for p in parts:
                    if isinstance(p, dict) and p.get("type") == "text":
                        text = p.get("text", "")
                        out_lines.append(text)
                        logger.info(f"Added text: {text[:50]}...")
            else:
                logger.info(f"Non-dict message: {str(msg)[:50]}...")
                out_lines.append(str(msg))

        result = "\n".join(out_lines).strip() or "(no textual output; edits may have been applied)"
        logger.info(f"code_task completed. Result length: {len(result)}")
        logger.info(f"Files in WORKDIR after task: {list(WORKDIR.glob('*')) if WORKDIR.exists() else 'Directory not found'}")
        return result

    except Exception as e:
        logger.error(f"Error in code_task: {e}", exc_info=True)
        return f"Error: {str(e)}"

# ASGI (A2A)
app = agent.to_a2a()

# --- Static game server management (works both with `python main.py` and `uvicorn main:app`) ---
import signal
import sys

STATIC_SERVER_PORT = 9871
_STATIC_PROC: subprocess.Popen[str] | None = None


def _launch_static_server() -> subprocess.Popen[str] | None:
    global _STATIC_PROC
    try:
        # Avoid double-start if already running
        if _STATIC_PROC and _STATIC_PROC.poll() is None:
            logger.info("Static server already running; skipping launch.")
            return _STATIC_PROC

        repo_root = Path(__file__).resolve().parents[2]
        game_server_script = repo_root / "game-server" / "run_server.py"
        if not game_server_script.exists():
            logger.warning(f"game-server/run_server.py not found at {game_server_script}")
            return None

        # Ensure output directory exists so the file server starts cleanly
        WORKDIR.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(game_server_script),
            "--port",
            str(STATIC_SERVER_PORT),
            "--directory",
            str(WORKDIR.resolve()),
            # Force local-only to avoid requiring ngrok; server still serves locally
            "--no-ngrok",
        ]
        # Keep it simple: serve locally without ngrok
        logger.info(
            f"Starting static server (local only); port={STATIC_SERVER_PORT}; dir={WORKDIR.resolve()}"
        )
        logger.info(f"Launching static server: {' '.join(cmd)}")
        _STATIC_PROC = subprocess.Popen(
            cmd,
            stdout=None,
            stderr=None,
            text=True,
        )
        logger.info(
            f"Static server started (PID: {_STATIC_PROC.pid}) at http://localhost:{STATIC_SERVER_PORT}/"
        )

        # Non-fatal probe
        try:
            import urllib.request

            with urllib.request.urlopen(
                f"http://127.0.0.1:{STATIC_SERVER_PORT}/", timeout=5
            ) as resp:
                status = getattr(resp, "status", None) or getattr(resp, "code", None) or 0
                logger.info(f"Static server HTTP check status: {status}")
        except Exception as e:
            logger.warning(f"Static server verification failed: {e}")

        return _STATIC_PROC
    except Exception as e:
        logger.error(f"Failed to launch static server: {e}", exc_info=True)
        return None


def _stop_static_server() -> None:
    global _STATIC_PROC
    if _STATIC_PROC and _STATIC_PROC.poll() is None:
        try:
            _STATIC_PROC.send_signal(signal.SIGINT)
        except Exception:
            pass
        try:
            _STATIC_PROC.wait(timeout=2)
        except Exception:
            try:
                _STATIC_PROC.terminate()
            except Exception:
                pass
    _STATIC_PROC = None


# Import-time safety: ensure server is running even if startup hooks aren't supported
def _static_server_running() -> bool:
    try:
        import urllib.request
        with urllib.request.urlopen(f"http://127.0.0.1:{STATIC_SERVER_PORT}/", timeout=0.5) as resp:
            return (getattr(resp, "status", None) or getattr(resp, "code", None) or 0) < 500
    except Exception:
        return False


# Do not auto-launch at import time; Makefile handles game server in dev.
logger.info("Static server launch deferred to app startup or Makefile.")


# Hook into FastAPI lifespan so `uvicorn main:app --reload` also starts the server
try:
    @app.on_event("startup")
    async def _on_startup() -> None:
        logger.info("App startup: ensuring static game server is running…")
        if not _static_server_running():
            _launch_static_server()
        else:
            logger.info("Static server already running; skipping launch.")

    @app.on_event("shutdown")
    async def _on_shutdown() -> None:
        logger.info("App shutdown: stopping static game server…")
        _stop_static_server()
except Exception:
    # If the returned object does not support events, just skip.
    pass

if __name__ == "__main__":
    import uvicorn
    logger.info(f"SWE agent working directory: {WORKDIR}")
    logger.info(f"API Key available: {'Yes' if os.getenv('ANTHROPIC_API_KEY') else 'No'}")

    # Ensure the static game server is running when invoked directly.
    if not _static_server_running():
        _launch_static_server()

    logger.info(f"Starting SWE agent API on port {int(os.getenv('PORT', '8000'))}")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
