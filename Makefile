.PHONY: setup data data-starter validate integrity detect evaluate db-load repro test api ui ui-build api-types demo eval-ai schema

setup:
	python -m pip install -e ".[dev]"

data:
	python -m yottaflex_debt_collection --dataset full --loans 10000 --seed 20261022 --anomaly-rows 50

data-starter:
	python -m yottaflex_debt_collection --dataset starter --loans 100 --seed 20261022 --anomaly-rows 50

validate:
	python -c "from yottaflex_debt_collection.schema_loader import load_dictionary; print(f'Validated {len(load_dictionary().tables)} tables')"
	python tools/generate_schema.py --check
	python -m yottaflex_debt_collection.integrity --data-dir data/full

integrity:
	python -m yottaflex_debt_collection.integrity --data-dir data/full --report reports/integrity.json

detect:
	python -m yottaflex_debt_collection.detectors --data-dir data/full --output reports/detections.csv

evaluate:
	python -m yottaflex_debt_collection.evaluation --detections reports/detections.csv --ground-truth ground_truth/full/ground_truth.csv --report reports/detector_metrics.md

db-load:
	python -m yottaflex_debt_collection.database --data-dir data/full --ground-truth-dir ground_truth/full --db data/full/collection.sqlite

repro:
	python tools/repro.py --dataset full --loans 10000 --seed 20261022 --anomaly-rows 50 --report docs/validation_summary.md

test:
	python -m pytest

api:
	python -m yottaflex_debt_collection.api

ui:
	npm --prefix ui run dev

ui-build:
	npm --prefix ui run build

api-types:
	python tools/export_openapi.py
	npm --prefix ui run generate:api-types

demo:
	@echo "TODO: end-to-end demo is not implemented yet."

eval-ai:
	@echo "TODO: AI evaluation is not implemented yet."

schema:
	python tools/generate_schema.py
