.PHONY: setup data data-starter validate repro test api ui demo eval-ai schema

setup:
	python -m pip install -e ".[dev]"

data:
	python -m yottaflex_debt_collection --loans 10000 --seed 20261022

data-starter:
	python -m yottaflex_debt_collection --loans 100 --seed 20261022

validate:
	python -c "from yottaflex_debt_collection.schema_loader import load_dictionary; print(f'Validated {len(load_dictionary().tables)} tables')"
	python tools/generate_schema.py --check

repro:
	python -m pytest tests/test_generator.py -k seed_repeats_records_and_export_checksums

test:
	python -m pytest

api:
	@echo "TODO: API server is not implemented yet."

ui:
	@echo "TODO: UI is not implemented yet."

demo:
	@echo "TODO: end-to-end demo is not implemented yet."

eval-ai:
	@echo "TODO: AI evaluation is not implemented yet."

schema:
	python tools/generate_schema.py
