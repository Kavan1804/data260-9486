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

# ---------- HW6 (MongoDB document API, chat memory, memory cost, file memory) ----------
LOG6 := reports/hw06/RUN_LOG.txt
STAMP6 = mkdir -p reports/hw06/raw; echo -e "\n===== $$(date '+%Y-%m-%d %H:%M:%S') $@ (Kavan Siddesh) =====" | tee -a $(LOG6)
# Professor's compose file (container study_assistant_mongo, port 27017). Not modified.
MONGO_COMPOSE := Homework6/long-term-memory/docker-compose.yml
HW6 := Homework6/scripts

.PHONY: mongo-up mongo-down mongo-shell test-hw6 test-hw6-live chat-demo experiments experiments-sweep \
        experiments-compress score-probes memory-cost consolidation-demo agent-md-check agent-md-generate \
        file-memory-chat verify-hw06 report-hw06

mongo-up:
	docker compose -f $(MONGO_COMPOSE) up -d
	docker compose -f $(MONGO_COMPOSE) ps

mongo-down:
	docker compose -f $(MONGO_COMPOSE) down

mongo-shell:
	docker exec -it study_assistant_mongo mongosh s9486_doc

test-hw6:
	@$(STAMP6); $(PYTHON) Homework6/tests/run_hw6_tests.py 2>/dev/null | tee -a $(LOG6)

test-hw6-live:
	@$(STAMP6); $(PYTHON) Homework6/tests/run_hw6_tests.py --live 2>/dev/null | tee -a $(LOG6)

chat-demo:
	@$(STAMP6); $(PYTHON) $(HW6)/chat_demo.py 2>&1 | tee -a $(LOG6)

experiments:
	@$(STAMP6); $(PYTHON) $(HW6)/run_memory_experiments.py 2>&1 | tee -a $(LOG6)

experiments-sweep:
	@$(STAMP6); $(PYTHON) $(HW6)/run_memory_experiments.py --settings n4 n12 n30 2>&1 | tee -a $(LOG6)

experiments-compress:
	@$(STAMP6); $(PYTHON) $(HW6)/run_memory_experiments.py --settings compress 2>&1 | tee -a $(LOG6)

score-probes:
	@$(STAMP6); $(PYTHON) $(HW6)/score_probes.py 2>&1 | tee -a $(LOG6)

memory-cost:
	@$(STAMP6); $(PYTHON) $(HW6)/memory_cost.py 2>&1 | tee -a $(LOG6)

consolidation-demo:
	@$(STAMP6); $(PYTHON) $(HW6)/consolidation_demo.py 2>&1 | tee -a $(LOG6)

agent-md-check:
	@$(STAMP6); $(PYTHON) $(HW6)/agent_md_check.py 2>&1 | tee -a $(LOG6)

agent-md-generate:
	@$(STAMP6); $(PYTHON) $(HW6)/agent_md_check.py --generate 2>&1 | tee -a $(LOG6)

# Interactive, so not logged; use the --script form in README_HW6.md for logged evidence.
file-memory-chat:
	$(PYTHON) $(HW6)/file_memory_chat.py

verify-hw06:
	@$(STAMP6); $(PYTHON) $(HW6)/verify_hw06.py 2>/dev/null | tee -a $(LOG6)

report-hw06:
	$(PYTHON) $(HW6)/render_report_hw06.py

# ---------- HW7 (JWT + roles, agent loop, Reflexion, bike-share ReAct, prompt injection, file tools) ----------
LOG7 := reports/hw07/RUN_LOG.txt
STAMP7 = mkdir -p reports/hw07/raw; echo -e "\n===== $$(date '+%Y-%m-%d %H:%M:%S') $@ (Kavan Siddesh) =====" | tee -a $(LOG7)
HW7 := Homework7/scripts

.PHONY: migrate-hw07 lint format-check precommit-all

migrate-hw07:
	@$(STAMP7); $(PYTHON) scripts/migrate_hw07.py 2>&1 | tee -a $(LOG7)

lint:
	@$(STAMP7); .venv/bin/ruff check . 2>&1 | tee -a $(LOG7)

format-check:
	@$(STAMP7); .venv/bin/ruff format --check . 2>&1 | tee -a $(LOG7)

precommit-all:
	@$(STAMP7); .venv/bin/pre-commit run --all-files 2>&1 | tee -a $(LOG7)

auth-demo:
	@$(STAMP7); $(PYTHON) $(HW7)/auth_demo.py 2>&1 | tee -a $(LOG7)

agent-reliability:
	@$(STAMP7); $(PYTHON) $(HW7)/run_agent_reliability.py 2>&1 | tee -a $(LOG7)

file-tools-demo:
	@$(STAMP7); $(PYTHON) $(HW7)/run_file_tools_demo.py 2>&1 | tee -a $(LOG7)

reflexion-compare:
	@$(STAMP7); $(PYTHON) $(HW7)/run_reflexion_compare.py 2>&1 | tee -a $(LOG7)

bikeshare-scenarios:
	@$(STAMP7); $(PYTHON) $(HW7)/build_bikeshare_scenarios.py 2>&1 | tee -a $(LOG7)

bikeshare-run:
	@$(STAMP7); $(PYTHON) $(HW7)/run_bikeshare_scenarios.py 2>&1 | tee -a $(LOG7)

injection-tests:
	@$(STAMP7); $(PYTHON) $(HW7)/run_injection_tests.py 2>&1 | tee -a $(LOG7)

test-hw7:
	@$(STAMP7); $(PYTHON) Homework7/tests/run_hw7_tests.py 2>/dev/null | tee -a $(LOG7)

test-hw7-live:
	@$(STAMP7); $(PYTHON) Homework7/tests/run_hw7_tests.py --live 2>/dev/null | tee -a $(LOG7)

test-all:
	@$(STAMP7); for t in tests/run_offline_tests.py Homework6/tests/run_hw6_tests.py Homework7/tests/run_hw7_tests.py; do \
	  echo "--- $$t"; $(PYTHON) $$t 2>/dev/null | tail -1; done 2>&1 | tee -a $(LOG7)

verify-hw07:
	@$(STAMP7); $(PYTHON) $(HW7)/verify_hw07.py 2>/dev/null | tee -a $(LOG7)

report-hw07:
	$(PYTHON) $(HW7)/render_report_hw07.py

injection-summary:
	@$(STAMP7); $(PYTHON) $(HW7)/run_injection_tests.py --summarize-only 2>&1 | tee -a $(LOG7)

# ---------- HW8 (Kafka request/response, three-agent pipeline, failure behavior) ----------
LOG8 := reports/hw08/RUN_LOG.txt
STAMP8 = mkdir -p reports/hw08/raw/agent_logs; echo -e "\n===== $$(date '+%Y-%m-%d %H:%M:%S') $@ (Kavan Siddesh) =====" | tee -a $(LOG8)
HW8 := Homework8/scripts
AGENT_LOGS := reports/hw08/raw/agent_logs

.PHONY: kafka-up kafka-down kafka-ps kafka-logs kafka-topics homework-demo homework-demo-api api-calls \
        planner writer writer2 reviewer send-question pipeline-demo dup-test death-test poison-test \
        ordering-test failure-tests metrics-hw08 reset-groups test-hw8 verify-hw08 report-hw08

# Kafka + topic setup + worker + FastAPI (all in docker-compose.yml)
kafka-up:
	@$(STAMP8); (docker compose up -d --build && docker compose ps -a) 2>&1 | grep -v "^#\|^ *=>" | tee -a $(LOG8)

kafka-down:
	docker compose down

kafka-ps:
	@$(STAMP8); docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>&1 | tee -a $(LOG8)

kafka-logs:
	@$(STAMP8); (echo "--- docker logs s9486_worker"; docker logs s9486_worker 2>&1 | grep "\[worker\]" | head -3; \
	  echo "--- docker logs s9486_api"; docker logs s9486_api 2>&1 | head -5) | tee -a $(LOG8)

kafka-topics:
	@$(STAMP8); docker exec -i s9486_kafka bash -s kafka:29092 < scripts/kafka_create_topics.sh 2>&1 | tee -a $(LOG8)

homework-demo:
	@$(STAMP8); $(PYTHON) Homework8/homework_demo.py 2>&1 | tee -a $(LOG8)

homework-demo-api:
	@$(STAMP8); $(PYTHON) Homework8/homework_demo.py --via api 2>&1 | tee -a $(LOG8)

api-calls:
	@$(STAMP8); $(PYTHON) $(HW8)/api_calls.py 2>&1 | tee -a $(LOG8)

# Part 2: one agent per terminal (each also keeps its own log file for the journey excerpt)
planner:
	@$(STAMP8); $(PYTHON) kafka_agents/planner.py 2>&1 | tee -a $(AGENT_LOGS)/planner.log

writer:
	@$(STAMP8); $(PYTHON) kafka_agents/writer.py 2>&1 | tee -a $(AGENT_LOGS)/writer.log

writer2:
	@$(STAMP8); $(PYTHON) kafka_agents/writer.py --instance writer-2 2>&1 | tee -a $(AGENT_LOGS)/writer2.log

reviewer:
	@$(STAMP8); $(PYTHON) kafka_agents/reviewer.py 2>&1 | tee -a $(AGENT_LOGS)/reviewer.log

send-question:
	@$(STAMP8); $(PYTHON) kafka_agents/send_question.py 2>&1 | tee -a $(LOG8)

# Starts the three agents in the background, sends one question and saves the journey (no extra terminals).
pipeline-demo:
	@$(STAMP8); $(PYTHON) $(HW8)/pipeline_demo.py 2>&1 | tee -a $(LOG8)

# Part 3 failure tests (each prints before-fix and after-fix runs)
dup-test:
	@$(STAMP8); $(PYTHON) $(HW8)/failure_duplicate.py 2>&1 | tee -a $(LOG8)

death-test:
	@$(STAMP8); $(PYTHON) $(HW8)/failure_consumer_death.py 2>&1 | tee -a $(LOG8)

poison-test:
	@$(STAMP8); $(PYTHON) $(HW8)/failure_poison.py 2>&1 | tee -a $(LOG8)

ordering-test:
	@$(STAMP8); $(PYTHON) $(HW8)/failure_ordering.py 2>&1 | tee -a $(LOG8)

failure-tests: dup-test death-test poison-test ordering-test

metrics-hw08:
	@$(STAMP8); $(PYTHON) $(HW8)/build_metrics.py 2>&1 | tee -a $(LOG8)

reset-groups:
	@$(STAMP8); $(PYTHON) $(HW8)/reset_groups.py 2>&1 | tee -a $(LOG8)

test-hw8:
	@$(STAMP8); $(PYTHON) Homework8/tests/run_hw8_tests.py 2>/dev/null | tee -a $(LOG8)

verify-hw08:
	@$(STAMP8); $(PYTHON) $(HW8)/verify_hw08.py 2>/dev/null | tee -a $(LOG8)

report-hw08:
	$(PYTHON) $(HW8)/render_report_hw08.py
