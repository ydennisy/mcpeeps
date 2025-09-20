dev:
	PYTHONPATH=src uv run uvicorn coordinator_app:api --host 0.0.0.0 --port 8000 --reload

test:
	curl -X POST http://localhost:8000/ \
		-H "Content-Type: application/json" \
		-d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{"role":"user","parts":[{"kind":"text","text":"hi all"}],"contextId":"room-1","kind":"message","messageId":"test-123"},"configuration":{"blocking":false,"acceptedOutputModes":["text"]}}}'

.PHONY: dev test
