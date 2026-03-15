.PHONY: start run dashboard stop restart clean

start:
	$(MAKE) dashboard &
	@sleep 1
	$(MAKE) run

run:
	uv run python main.py

dashboard:
	uv run uvicorn conwai.dashboard:app --host 0.0.0.0 --port 8000 --reload

stop:
	pkill -f "python main.py" 2>/dev/null || true
	pkill -f "uvicorn conwai.dashboard" 2>/dev/null || true

clean:
	rm -rf data/agents
	: > data/events.jsonl

restart: stop clean
	@sleep 1
	$(MAKE) start
