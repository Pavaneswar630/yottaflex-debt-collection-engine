.PHONY: help run test schema

help:
	@echo "Available targets: run, test, schema"

run:
	python -m yottaflex_debt_collection --help

test:
	python -m unittest discover -s tests -v

schema:
	python tools/generate_schema.py
