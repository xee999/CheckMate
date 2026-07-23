#!/usr/bin/env python3
import logging
import sys

# Configure root logger to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout
)

from EVAL.eval_engine import EvalEngine
from config_manager import load_config, DEFAULT_MODEL, DEFAULT_BASE_URL
import json

cfg = load_config()
api_key = cfg.get("api_key", "")
model = cfg.get("model", DEFAULT_MODEL)
base_url = cfg.get("base_url", DEFAULT_BASE_URL)

engine = EvalEngine(base_url=base_url, api_key=api_key, model=model)
report, metrics = engine.run_evals(target="test2")

print("\n" + "="*50)
print("DETAILED STATUS COMPARISON:")
print("="*50)
for row in metrics.rows:
    print(f"Req ID: {row.req_id} ({row.clause_num})")
    print(f"  Model Status:    {row.model_status}")
    print(f"  Expected Status: {row.expected_status}")
    print(f"  Status Match:    {row.status_match}")

print("\n" + "="*50)
print("EVALUATION METRICS FOR TEST 2:")
print("="*50)
print(f"Total Evals: {metrics.total_evals}")
print(f"Exact Matches: {metrics.exact_matches} ({metrics.exact_match_pct}%)")
print(f"F1 Score: {metrics.f1_score}%")
print(f"Precision: {metrics.precision}%")
print(f"Recall: {metrics.recall}%")
print(f"Intelligence Mapping Score: {metrics.intelligence_mapping_score}%")
print(f"Intention Score: {metrics.intention_score}%")
print("="*50)
