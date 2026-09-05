.DEFAULT_GOAL := help
UV ?= uv

.PHONY: help install test init-db poll render refresh world-svg

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-12s %s\n", $$1, $$2}'

install: ## Create the virtualenv and install dev dependencies
	$(UV) sync

test: ## Run the test suite
	$(UV) run pytest -q

init-db: ## Create the SQLite database and schema
	$(UV) run python -m statusboard init-db

poll: ## Poll every registered provider into SQLite
	$(UV) run python -m statusboard poll

render: ## Write site/index.html from SQLite
	$(UV) run python -m statusboard render --out site

world-svg: ## Regenerate statusboard/data/world-land.svgpath from the vendored GeoJSON
	$(UV) run python -c "from statusboard.mapgen import write_land_path; print(write_land_path())"

refresh: ## Poll then render; render runs even if a provider failed; exits with poll's code
	@$(UV) run python -m statusboard poll; code=$$?; \
	$(UV) run python -m statusboard render --out site; \
	exit $$code
