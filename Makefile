.PHONY: help run test

help:
	@echo "Available targets: run, test"

run:
	python -m yottaflex_debt_collection --help

test:
	python -m unittest discover -s tests -v
