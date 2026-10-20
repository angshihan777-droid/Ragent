# Isolated evaluation (never runs against the application database)

`evaluation/` is deliberately separate from the product runtime. It contains a frozen synthetic corpus and an executable harness for two kinds of evidence requested for this project:

- retrieval: document-level Recall@3, MRR@3, Hit@1, latency, vector-only baseline vs. vector recall + local reranker, plus separate no-answer probes;
- recovery: duplicate delivery fencing, stale lease takeover, lost initial Redis delivery, lost SSE terminal notification, safe durable failure history/FIFO continuation, and transaction rollback.

The harness creates a temporary PostgreSQL database named `ragent_eval_<random>`, applies the application schema there, and drops it in `finally`. It only records counts and MD5 fingerprints of the real application database; it never prints API keys or document content from that database. Redis keys are namespaced and deleted individually.

Run inside the API container after services are healthy:

```powershell
docker compose exec -T api mkdir -p /tmp/evaluation
docker compose cp evaluation/. api:/tmp/evaluation/
docker compose exec -T api env PYTHONPATH=/app python /tmp/evaluation/run.py
```

The report is written to `evaluation/results/latest.json` inside the container. Copy it back if needed:

```powershell
docker compose cp api:/tmp/evaluation/results/latest.json evaluation/results/latest.json
```

The live-provider section runs only when the existing database has an API configuration. It performs a small JSON-mode compatibility smoke check and two synthetic graph questions; it does not upload the preserved resume. Retrieval numbers are a small engineering regression signal, not a general benchmark.

## 20-question CI gate

`regression.py` is the fast, deterministic gate used by CI. It creates a temporary
database on the target PostgreSQL instance, ingests the frozen corpus, runs the
20 retrieval questions with the real embedding + rerank models, and exits non-zero
when any threshold is missed:

```bash
PYTHONPATH=backend DATABASE_URL=postgresql://ragent:ragent@localhost:5432/ragent \
  python evaluation/regression.py
```

Current thresholds: Hit@1 ≥ 0.85, MRR@3 ≥ 0.90, Recall@3 ≥ 0.95.
The result is written to `evaluation/results/regression.json`.
