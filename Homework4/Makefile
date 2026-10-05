SHELL := /bin/bash
.SHELLFLAGS := -o pipefail -c
PYTHON ?= .venv/bin/python
LOG := reports/hw04/RUN_LOG.txt
STAMP = echo -e "\n===== $$(date '+%Y-%m-%d %H:%M:%S') $@ =====" | tee -a $(LOG)

.PHONY: init-db create-user backend seed explain measure rag verify-hw04 report

init-db:
	@$(STAMP); $(PYTHON) scripts/init_db.py 2>&1 | tee -a $(LOG)

create-user:
	$(PYTHON) scripts/init_db.py --create-user

backend:
	PYTHONPATH=.:.. $(PYTHON) -m uvicorn backend.app.main:app --port 8486 --reload  # backend/ lives at the repo root since HW5

seed:
	@$(STAMP); $(PYTHON) scripts/seed_n1.py --reset 2>&1 | tee -a $(LOG)

explain:
	@$(STAMP); $(PYTHON) scripts/explain_index.py 2>&1 | tee -a $(LOG)

measure:
	@$(STAMP); $(PYTHON) scripts/measure_n1.py 2>&1 | tee -a $(LOG)

rag:
	@$(STAMP); $(PYTHON) rag.py 2>&1 | tee -a $(LOG)

verify-hw04:
	@$(STAMP); $(PYTHON) scripts/verify_hw04.py 2>&1 | tee -a $(LOG)

report:
	python3 scripts/render_report.py
