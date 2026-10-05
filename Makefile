PYTHON ?= python3

.PHONY: help test lint generate update record icons clean

help: ## list available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

# golden regen: UPDATE_GOLDEN=1 make test
test: ## run unit tests
	$(PYTHON) -m unittest discover -s tests -v

lint: ## byte-compile scripts and tests
	$(PYTHON) -m compileall -q scripts tests

generate: ## regenerate svg and readme from the recorded fixture
	$(PYTHON) scripts/generate.py --from-json fixtures/repos.recorded.json

update: ## regenerate svg and readme from live gh data
	$(PYTHON) scripts/generate.py --live

record: ## refresh the recorded gh repo-list fixture
	gh repo list --limit 300 --json name,stargazerCount,description,languages,isFork,isArchived,createdAt > fixtures/repos.recorded.json

icons: ## vendor devicon svgs into assets/devicons
	$(PYTHON) scripts/vendor_icons.py

clean: ## remove __pycache__ dirs under scripts and tests
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for d in ('scripts', 'tests') for p in pathlib.Path(d).rglob('__pycache__')]"
