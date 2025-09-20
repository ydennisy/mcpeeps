# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the main coordinator
```bash
uv run uvicorn coordinator.src.coordinator_app.app:api --reload --port 8080
```

### Running individual agents
```bash
# SWE Agent (Software Engineer)
cd agents/swe-agent && uv run python main.py

# Game Tester Agent
cd agents/game-tester && uv run python main.py

# Product Manager Agent
cd agents/product-manager && uv run python main.py
```

### Running the game server
```bash
# Start game server with ngrok tunneling (default port 8000)
uv run python game-server/run_server.py

# Run without ngrok (local only)
uv run python game-server/run_server.py --no-ngrok

# Custom port and options
uv run python game-server/run_server.py --port 9000 --open-browser
```

### Package management
The project uses `uv` for dependency management with a workspace structure defined in the root `pyproject.toml`.

## Architecture Overview

This is a multi-agent system for collaborative game development with the following main components:

### Coordinator (`coordinator/`)
- **FastAPI application** that orchestrates conversations between multiple AI agents
- **Agent registry** (`registry.py`) - manages available agents and their endpoints
- **Real-time communication** (`agent_comm.py`) - handles message passing between agents via FastA2A protocol
- **Background task processing** - manages multi-round conversations with cancellation support
- **Web UI** (`ui.py`) - provides interface for triggering agent conversations and viewing results

### Agents (`agents/`)
Each agent is a specialized AI with distinct capabilities:

- **SWE Agent** (`swe-agent/`) - Software engineer that uses Claude Code SDK to perform coding tasks
  - Integrates with Claude Code for file operations, bash commands, and code generation
  - Uses port 9871 for web servers by default
  - Working directory: `./game-server` by default (configurable via `SWE_AGENT_CWD`)

- **Game Tester** (`game-tester/`) - Uses browser automation (browser-use) to test games
  - Can launch headless or headed browsers to interact with web-based games
  - Provides detailed testing reports including gameplay verification and bug detection

- **Product Manager** (`product-manager/`) - Handles product planning and requirements

### Game Server (`game-server/`)
- **Static file server** with ngrok tunneling capabilities for external access
- **Iframe-embeddable** content with appropriate headers for cross-origin embedding
- **Hot reload** - serves files directly without build step, changes appear on refresh

## Communication Protocol

Agents communicate using the **FastA2A protocol** (Fast Agent-to-Agent):
- **JSON-RPC 2.0** based messaging over HTTP
- **Task-based workflow** with states: submitted → working → completed/failed
- **Message threading** with context IDs for conversation continuity
- **Background processing** with real-time status updates

## Key Environment Variables

- `ANTHROPIC_API_KEY` - Required for Claude integration in SWE agent
- `SWE_AGENT_CWD` - Working directory for SWE agent operations
- `PORT` - Server port for individual agents (default varies by agent)
- `NGROK_AUTHTOKEN` - For ngrok tunneling in game server

## Agent Coordination Flow

1. **User submits request** via coordinator web UI
2. **Coordinator broadcasts** message to all registered agents simultaneously
3. **Agents process** tasks and submit responses back to coordinator
4. **Multi-round conversation** - agents can respond to each other's messages
5. **Real-time updates** - conversation status available via `/conversation-status` endpoint
6. **Cancellation support** - conversations can be stopped mid-execution

## Working with the SWE Agent

The SWE agent is the primary code-writing component:
- Always acknowledges requests first, then uses `code_task` tool for implementation
- Uses Claude Code SDK with configurable permission modes: 'ask', 'acceptEdits', 'rejectEdits'
- Has access to standard Claude Code tools: read, write, edit, bash, grep, glob, webFetch, webSearch
- Creates web servers on port 9871 and uses `start_server` tool to launch and verify
