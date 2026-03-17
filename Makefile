.PHONY: start run dashboard dev build stop restart clean

start:
	uv run uvicorn conwai.dashboard:app --host 0.0.0.0 --port 8000 --reload &
	cd frontend && npm run dev & @sleep 1
	uv run python main.py

run:
	uv run python main.py

dashboard:
	uv run uvicorn conwai.dashboard:app --host 0.0.0.0 --port 8000 --reload

dev:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

stop:
	pkill -f "python main.py" 2>/dev/null || true
	pkill -f "uvicorn conwai.dashboard" 2>/dev/null || true
	pkill -f "vite" 2>/dev/null || true

clean:
	rm -rf data/agents
	rm -f data/events.db data/events.db-wal data/events.db-shm
	: > data/sim.log
	: > handler_input.txt

restart: stop clean
	@sleep 1
	$(MAKE) start
