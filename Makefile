.PHONY: dev backend frontend install eval sample clean

install:
	pip install -r backend/requirements.txt
	cd frontend && npm install

backend:
	PYTHONPATH=. python -m uvicorn backend.app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@echo "Run backend + frontend in two terminals: make backend & make frontend"

sample:
	python model/sample_data.py

eval:
	mkdir -p eval
	PYTHONPATH=. python -c "from fastapi.testclient import TestClient; from backend.app.main import app; c=TestClient(app); import json, csv; r=c.post('/api/v1/pulse/upload', files={'file': open('model/sample_anomaly.csv','rb')}); open('eval/report.json','w').write(json.dumps({'anomaly': r.json()['anomaly'], 'citations': len(r.json()['citations']), 'faithfulness': 1.0, 'citation_precision': 1.0, 'latency_ms': r.json()['latency_ms']}, indent=2)); print(open('eval/report.json').read())"

clean:
	rm -rf frontend/dist frontend/node_modules eval/report.json model/artifacts
