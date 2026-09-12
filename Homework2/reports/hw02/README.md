# HW2 Reproducible Run Instructions

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PORT_BASE=8986
python -m user_management_app.main
```

For the graph, set `LOCAL_MODEL=qwen3:8b` and ensure Ollama is running with that model. All node calls go through `src/model_client.py`. Run `python scripts/run_graph_experiments.py` for the required frozen-input experiments, then `COMMIT_HASH=$(git rev-parse HEAD) python scripts/verify_hw02.py` for the self-check.
