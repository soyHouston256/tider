PYTHON ?= .venv/bin/python
PORT ?= 8080

.PHONY: setup run test lint format docker
setup:
	./scripts/setup.sh
run:
	$(PYTHON) -m tider.console --env-file .env --port $(PORT)
test:
	$(PYTHON) -m pytest -q
lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m ruff format --check src tests
format:
	$(PYTHON) -m ruff check --fix src tests
	$(PYTHON) -m ruff format src tests
docker:
	docker compose --profile console up -d --build console
