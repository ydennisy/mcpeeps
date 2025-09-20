dev:
	uv run uvicorn main:app --host 0.0.0.0 --port 8002 --reload

test:
	@echo "Testing agent..."
	@START_TIME=$$(date +%s); \
	TASK_ID=$$(curl -s -X POST http://localhost:8002/ \
		-H "Content-Type: application/json" \
		-d '{"jsonrpc": "2.0", "method": "message/send", "params": {"message": {"role": "user", "kind": "message", "parts": [{"kind": "text", "text": "create a file called test.txt"}], "messageId": "test-$(shell date +%s)"}}, "id": 1}' \
		| jq -r '.result.id'); \
	echo "Task ID: $$TASK_ID (started at $$(date))"; \
	while true; do \
		STATUS=$$(curl -s -X POST http://localhost:8002/ \
			-H "Content-Type: application/json" \
			-d "{\"jsonrpc\": \"2.0\", \"method\": \"tasks/get\", \"params\": {\"id\": \"$$TASK_ID\"}, \"id\": 2}" \
			| jq -r '.result.status.state'); \
		if [ "$$STATUS" = "completed" ] || [ "$$STATUS" = "failed" ]; then \
			END_TIME=$$(date +%s); \
			DURATION=$$((END_TIME - START_TIME)); \
			echo "✅ Task $$STATUS in $${DURATION}s at $$(date)"; \
			break; \
		fi; \
		echo "Status: $$STATUS..."; \
		sleep 1; \
	done

.PHONY: dev test
