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

WORKDIR = Path(os.getenv("SWE_AGENT_CWD", "./swe-agent-output")).resolve()
WORKDIR.mkdir(parents=True, exist_ok=True)

SYSTEM_PROMPT = """You are a Software Engineer.
    You are in a chat room with other humans & agents:
    - CEO
    - game-tester
    You can address them by using @, e.g @game-tester
    Otherwise you will be speaking to everyone.
    Everyone sees all messages.
    You will collaborate on a task to build a game given by the CEO.

- Always acknowledge the user's request first with a brief, helpful response explaining what you're going to do.
- Then use the code_task tool to perform any coding work. You should use this once and provide the full details to implement this with a single tool call.
- After completing the coding work, provide a final summary of what was accomplished.
- When creating web servers, always use port 9871 specifically.
- After creating all the files, use the start_server tool to launch the local server.
- This tool will start the server in the background and verify it's accessible.
- The tool will return the localhost URL for accessing the application.
- After the start_server tool completes successfully, provide a brief final confirmation and conclude the conversation.
- Keep responses concise and focused on task completion.
"""

MODEL = AnthropicModel(model_name="claude-3-5-sonnet-20240620")

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

@agent.tool
async def start_server(ctx, port: int = 9871) -> str:
    """
    Start the Python server on the specified port and return the localhost URL.
    """
    logger.info(f"Starting server on port {port}")

    try:
        # Start the Python server in background
        server_process = subprocess.Popen(
            ['python3', 'server.py'],
            cwd=WORKDIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        logger.info(f"Started server process (PID: {server_process.pid})")

        # Give server a moment to start
        await asyncio.sleep(2)

        # Test if server is responding
        try:
            import requests
            test_response = requests.get(f'http://localhost:{port}', timeout=5)
            if test_response.status_code == 200:
                logger.info(f"Server is responding on port {port}")
                return f"✅ Server started successfully and verified!\n🏠 Local: http://localhost:{port}\n\n🎮 Tetris game is now accessible and ready to play at http://localhost:{port}\n\n✅ Task completed successfully - game is live and accessible!"
            else:
                return f"⚠️ Server started but returned status {test_response.status_code}. Check http://localhost:{port}"
        except requests.exceptions.RequestException as test_error:
            logger.warning(f"Could not verify server response: {test_error}")
            return f"✅ Server started (PID: {server_process.pid})!\n🏠 Local: http://localhost:{port}\n\n🎮 Game should be accessible at http://localhost:{port}\n\n✅ Task completed - server is running in background!"

    except Exception as e:
        logger.error(f"Error starting server: {e}", exc_info=True)
        return f"❌ Error starting server: {str(e)}"

# ASGI (A2A)
app = agent.to_a2a()

if __name__ == "__main__":
    import uvicorn
    logger.info(f"SWE agent working directory: {WORKDIR}")
    logger.info(f"API Key available: {'Yes' if os.getenv('ANTHROPIC_API_KEY') else 'No'}")
    logger.info(f"Starting server on port {int(os.getenv('PORT', '8000'))}")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
