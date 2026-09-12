setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

run:
	PORT_BASE=8986 .venv/bin/python -m user_management_app.main

verify-hw02:
	COMMIT_HASH=$$(git rev-parse HEAD 2>/dev/null || echo local-uncommitted) .venv/bin/python scripts/verify_hw02.py

experiments:
	.venv/bin/python scripts/run_graph_experiments.py
