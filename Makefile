.PHONY: setup data data-starter validate repro test api ui demo eval-ai schema

setup:
	python -m pip install -e ".[dev]"

data:
	@echo "TODO: full synthetic dataset generator is not implemented yet."

data-starter:
	@echo "TODO: starter dataset generator is not implemented yet."

validate:
	python -c "from yottaflex_debt_collection.schema_loader import load_dictionary; print(f'Validated {len(load_dictionary().tables)} tables')"
	python tools/generate_schema.py --check

repro:
	@echo "TODO: dataset regeneration and checksum comparison are not implemented yet."

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
