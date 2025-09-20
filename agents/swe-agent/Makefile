dev:
	@set -e; \
	mkdir -p swe-agent-output; \
	echo "Starting game server on http://localhost:9871 serving ./swe-agent-output"; \
	uv run python ../../game-server/run_server.py --port 9871 --directory ./swe-agent-output --no-ngrok & \
	GS_PID=$$!; \
	echo "Game server PID: $$GS_PID"; \
	trap 'echo "Stopping game server ($$GS_PID)…"; kill $$GS_PID 2>/dev/null || true' EXIT; \
	uv run uvicorn main:app --host 0.0.0.0 --port 8002 --reload

test:
	@echo "Creating Tetris game with agent..."
	@START_TIME=$$(date +%s); \
	TASK_ID=$$(curl -s -X POST http://localhost:8002/ \
		-H "Content-Type: application/json" \
		-d '{"jsonrpc": "2.0", "method": "message/send", "params": {"message": {"role": "user", "kind": "message", "parts": [{"kind": "text", "text": "Create a complete web-based Tetris game and serve it locally. Requirements: 1) Create HTML, CSS, and JavaScript files for a fully functional Tetris game with proper mechanics (falling blocks, rotation, line clearing, scoring), 2) Start a local web server to serve the game, 3) Provide the localhost URL where I can access and play the game. Make sure to test that the game works properly and is accessible via the web browser."}], "messageId": "tetris-$(shell date +%s)"}}, "id": 1}' \
		| jq -r '.result.id' 2>/dev/null); \
	echo "Task ID: $$TASK_ID (started at $$(date))"; \
	echo ""; \
	LAST_MSG_COUNT=1; \
	while true; do \
		RESPONSE=$$(curl -s -X POST http://localhost:8002/ \
			-H "Content-Type: application/json" \
			-d "{\"jsonrpc\": \"2.0\", \"method\": \"tasks/get\", \"params\": {\"id\": \"$$TASK_ID\"}, \"id\": 2}" 2>/dev/null); \
		STATUS=$$(echo "$$RESPONSE" | jq -r '.result.status.state' 2>/dev/null || echo "unknown"); \
		MSG_COUNT=$$(echo "$$RESPONSE" | jq '.result.history | length' 2>/dev/null || echo "0"); \
		if [ "$$MSG_COUNT" -gt "$$LAST_MSG_COUNT" ] 2>/dev/null; then \
			echo "$$RESPONSE" | jq -r ".result.history[$$LAST_MSG_COUNT:] | .[] | select(.role == \"agent\") | \"🤖 Agent: \" + (.parts[0].text // \"[processing...]\")" 2>/dev/null; \
			LAST_MSG_COUNT=$$MSG_COUNT; \
			echo ""; \
		fi; \
		if [ "$$STATUS" = "completed" ] || [ "$$STATUS" = "failed" ]; then \
			END_TIME=$$(date +%s); \
			DURATION=$$((END_TIME - START_TIME)); \
			echo "✅ Task $$STATUS in $${DURATION}s at $$(date)"; \
			break; \
		fi; \
		echo "Status: $$STATUS..."; \
		sleep 3; \
	done

.PHONY: dev test
