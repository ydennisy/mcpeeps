from __future__ import annotations

from typing import TYPE_CHECKING

from dotenv import load_dotenv
from pydantic_ai import Agent, RunContext

from browser_use import Agent as BrowserUseAgent
from browser_use import BrowserProfile, BrowserSession, ChatOpenAI

if TYPE_CHECKING:  # pragma: no cover - hints only
    from browser_use.agent.views import AgentHistoryList

load_dotenv()

SYSTEM_PROMPT = """
You are a game tester.
You are in a chat room with other humans & agents:
- CEO
- swe-agent
You can address them by using @, e.g @swe-agent
Otherwise you will be speaking to everyone.
Everyone sees all messages.
You will collaborate on a task to build a game given by the CEO.

You can launch a full browser via the `test_game_in_browser` tool. Use it to visit a URL, play the game hands-on, and report
observations about gameplay, bugs, and player experience. Summarize what you learn for the team.

The game is always running on localhost:9871
"""


def _format_browser_history(history: "AgentHistoryList") -> str:
    lines: list[str] = []

    final_result = history.final_result()
    if final_result:
        lines.append(f"Final result: {final_result}")

    errors = [error for error in history.errors() if error]
    if errors:
        lines.append("Errors encountered:")
        lines.extend(f"- {error}" for error in errors)

    visited_urls: list[str] = []
    for url in history.urls():
        if url and url not in visited_urls:
            visited_urls.append(url)
    if visited_urls:
        lines.append("Visited URLs:")
        lines.extend(f"- {url}" for url in visited_urls)

    step_limit = 5
    step_notes_added = False
    for step_index, item in enumerate(history.history[:step_limit], start=1):
        step_notes: list[str] = []
        for result in item.result:
            note = (result.extracted_content or result.long_term_memory or "").strip()
            if note:
                step_notes.append(note)
            elif result.error:
                step_notes.append(f"Error: {result.error.strip()}")
        if step_notes:
            if not step_notes_added:
                lines.append("Step highlights:")
                step_notes_added = True
            lines.append(f"Step {step_index}:")
            lines.extend(f"  - {note}" for note in step_notes)

    if len(history.history) > step_limit:
        lines.append(f"... ({len(history.history) - step_limit} additional steps omitted)")

    if not lines:
        lines.append("The browser agent completed without textual output.")

    return "\n".join(lines)


agent = Agent('openai:gpt-4.1', instructions=SYSTEM_PROMPT)


@agent.tool
async def test_game_in_browser(
    _ctx: RunContext[None],
    url: str,
    objective: str | None = None,
    max_steps: int = 40,
) -> str:
    """Play a web-hosted game via browser-use and summarize the findings."""

    focus = (
        objective.strip()
        if objective
        else "Play the game long enough to verify the main mechanics, responsiveness, and failure conditions."
    )

    task_description = (
        f"Visit {url} and actively test the game by playing it. {focus} "
        "Capture any bugs or usability issues you encounter and finish with a concise DONE summary."
    )

    browser_session: BrowserSession | None = None
    browser_agent: BrowserUseAgent | None = None
    history: "AgentHistoryList" | None = None
    error_message: str | None = None

    try:
        profile = BrowserProfile(headless=False, keep_alive=False)
        browser_session = BrowserSession(browser_profile=profile)
        llm = ChatOpenAI(model='gpt-4.1-mini')
        browser_agent = BrowserUseAgent(
            task=task_description,
            llm=llm,
            browser_session=browser_session,
            directly_open_url=True,
            extend_system_message=(
                "Focus on hands-on gameplay verification. Document the controls you try, note crashes or glitches, and end with"
                " a clear DONE summary for the team."
            ),
        )

        history = await browser_agent.run(max_steps=max_steps)
    except Exception as exc:  # pragma: no cover - runtime safeguard
        error_message = f"Browser-based testing failed: {exc}"
    finally:
        if browser_agent is not None:
            try:
                await browser_agent.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
        elif browser_session is not None:
            try:
                await browser_session.kill()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    if error_message is not None:
        return error_message

    if history is None:
        return "Browser-based testing completed without any history output."

    return _format_browser_history(history)


app = agent.to_a2a()
