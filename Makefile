# Makefile — a thin, discoverable wrapper around `pixi run`.
#
# pixi.toml is the source of truth for both the environment and the tasks;
# these targets only exist so `make <tab>` and `make help` work for people who
# reach for make out of habit. Add tasks in pixi.toml first, then mirror here.

.DEFAULT_GOAL := help
.PHONY: help install scrape build pipeline serve test lint fmt check clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-10s\033[0m %s\n", $$1, $$2}'

install:  ## Create/refresh the pixi environment from pixi.lock
	pixi install

scrape:   ## Fetch every source, snapshot raw payloads, append tidy rows
	pixi run scrape

build:    ## Render data/tidy/*.csv into site/data/*.json
	pixi run build

pipeline: ## scrape + build (exactly what CI runs)
	pixi run pipeline

serve:    ## Preview ./site at http://localhost:8000
	pixi run serve

test:     ## Offline test-suite
	pixi run test

lint:     ## ruff check + format check
	pixi run lint

fmt:      ## Auto-fix lint and formatting
	pixi run fmt

check:    ## lint + test (CI's quality gate)
	pixi run check

clean:    ## Remove generated site data and caches (keeps data/ and the env)
	rm -rf site/data .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
