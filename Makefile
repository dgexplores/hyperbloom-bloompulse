.PHONY: install backend frontend test eval sample corpus clean

VENV := .venv
PY := $(VENV)/bin/python

install:
	uv venv --python 3.12 $(VENV)
	uv pip install --python $(PY) -r requirements-dev.txt
	cd frontend && npm install

backend:
	PYTHONPATH=. $(PY) -m uvicorn backend.app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

test:
	PYTHONPATH=. $(PY) -m pytest tests/ -q

eval:
	PYTHONPATH=. RATE_LIMIT_PER_MINUTE=0 $(PY) eval/run_eval.py

sample:
	PYTHONPATH=. $(PY) model/sample_data.py

corpus:
	PYTHONPATH=. $(PY) corpus/build_manifest.py

clean:
	rm -rf frontend/dist frontend/node_modules $(VENV) .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
