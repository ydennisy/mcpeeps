import os
import logging
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
- A local static server is running at http://localhost:9871 serving files
  from the swe-agent-output directory. 
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

if __name__ == "__main__":
    import uvicorn
    logger.info(f"SWE agent working directory: {WORKDIR}")
    logger.info(f"API Key available: {'Yes' if os.getenv('ANTHROPIC_API_KEY') else 'No'}")
    logger.info(f"Starting SWE agent API on port {int(os.getenv('PORT', '8000'))}")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
