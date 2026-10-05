# DATA 260 shared application (HW5 onward). Run every target from the repo root.
SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON ?= .venv/bin/python
LOG := reports/hw05/RUN_LOG.txt
# Section header in RUN_LOG.txt, also echoed so terminal screenshots show the name.
STAMP = echo -e "\n===== $$(date '+%Y-%m-%d %H:%M:%S') $@ (Kavan Siddesh) =====" | tee -a $(LOG)

.PHONY: install migrate create-user backend frontend inspect-meals inspect-domain mcp-calls contracts \
        retry-demo retry-experiment test safety-demo agent-scenarios verify-hw05 report

install:
	python3 -m venv .venv
	$(PYTHON) -m pip install -r requirements.txt
	cd frontend && npm install

migrate:
	@$(STAMP); $(PYTHON) scripts/migrate_hw05.py 2>&1 | tee -a $(LOG)

create-user:
	$(PYTHON) scripts/create_user.py

backend:
	$(PYTHON) -m uvicorn backend.app.main:app --port 8486 --reload

frontend:
	cd frontend && npm run dev

# MCP Inspector (opens a browser tab). mcp dev runs the server through uv.
inspect-meals:
	.venv/bin/mcp dev mcp_servers/meals_server.py

inspect-domain:
	.venv/bin/mcp dev mcp_servers/domain_server.py

mcp-calls:
	@$(STAMP); $(PYTHON) scripts/mcp_calls.py 2>/dev/null | tee -a $(LOG)

contracts:
	@$(STAMP); $(PYTHON) scripts/write_tool_contracts.py 2>&1 | tee -a $(LOG)

retry-demo:
	@$(STAMP); $(PYTHON) scripts/demo_retry.py 2>/dev/null | tee -a $(LOG)

retry-experiment:
	@$(STAMP); $(PYTHON) scripts/run_retry_experiment.py 2>/dev/null | tee -a $(LOG)

test:
	@$(STAMP); $(PYTHON) tests/run_offline_tests.py 2>/dev/null | tee -a $(LOG)

safety-demo:
	@$(STAMP); $(PYTHON) scripts/demo_safety.py 2>/dev/null | tee -a $(LOG)

agent-scenarios:
	@$(STAMP); $(PYTHON) scripts/run_agent_scenarios.py 2>/dev/null | tee -a $(LOG)

verify-hw05:
	@$(STAMP); $(PYTHON) scripts/verify_hw05.py 2>/dev/null | tee -a $(LOG)

report:
	$(PYTHON) scripts/render_report_hw05.py
