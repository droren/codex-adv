.PHONY: install-dev lint audit test check

install-dev:
	python3 -m pip install -e ".[dev]"

lint:
	python3 -m ruff check src tests

audit:
	python3 -m bandit -c pyproject.toml -r src

test:
	python3 -m pytest

check:
	python3 -m ruff check src tests
	python3 -m bandit -c pyproject.toml -r src
	python3 -m pytest
