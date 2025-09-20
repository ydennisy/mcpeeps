import os
import logging
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

SYSTEM_PROMPT = """You are a Senior Software Engineer.

- You must use the coding_task tool to perform any coding work.
- You must verify that the code that you write is working correctly.
"""

MODEL = AnthropicModel(model_name="claude-3-5-sonnet-20240620")

agent = Agent(MODEL, instructions=SYSTEM_PROMPT)

@agent.tool
async def code_task(ctx, prompt: str, permission_mode: str | None = None) -> str:
    """
    Ask Claude Code to perform coding work inside the agent repo.
    `permission_mode`: 'ask' | 'acceptEdits' | 'rejectEdits' (default 'acceptEdits').
    """
    logger.info(f"code_task called with prompt: {prompt[:100]}...")
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
    logger.info(f"Starting server on port {int(os.getenv('PORT', '8000'))}")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
