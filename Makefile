PYTHON ?= python3

.PHONY: test validate validate-report-example render-report-example build-site mock-e2e

test:
	@fail=0; for d in harness/*/tests; do 	  [ -d "$$d" ] || continue; 	  echo "== $$d"; $(PYTHON) -m unittest discover -s "$$d" -t "$$d" || fail=1; 	done; exit $$fail

validate:
	$(PYTHON) harness/5-formal-campaign/code/validate_spec.py harness/5-formal-campaign/code/examples/campaign.yaml --schema harness/5-formal-campaign/schemas/campaign-spec.schema.json
	$(PYTHON) harness/5-formal-campaign/code/validate_spec.py harness/5-formal-campaign/code/examples/mock-campaign.json --schema harness/5-formal-campaign/schemas/campaign-spec.schema.json
	@find results -mindepth 2 -maxdepth 2 -name study.yaml -print | while read f; do $(PYTHON) harness/5-formal-campaign/code/validate_spec.py "$$f" --schema harness/5-formal-campaign/schemas/study.schema.json || exit; done
	$(PYTHON) harness/5-formal-campaign/code/validate_spec.py harness/7-report-and-feedback/code/examples/report-config.json --schema harness/7-report-and-feedback/schemas/report-config.schema.json

validate-report-example:
	$(PYTHON) harness/7-report-and-feedback/code/validate_report_inputs.py harness/7-report-and-feedback/code/examples/report-config.json harness/7-report-and-feedback/code/examples/normalized-report-data.json

render-report-example: validate-report-example
	rm -rf /tmp/llm-report-example
	$(PYTHON) harness/7-report-and-feedback/code/render_report.py harness/7-report-and-feedback/code/examples/report-config.json harness/7-report-and-feedback/code/examples/normalized-report-data.json --runs-csv harness/7-report-and-feedback/code/examples/campaign-summary-runs.csv --aggregate-csv harness/7-report-and-feedback/code/examples/campaign-summary-aggregate.csv --output-dir /tmp/llm-report-example

build-site:
	harness/7-report-and-feedback/code/site/astro/scripts/build-site.sh

mock-e2e:
	rm -rf /tmp/llm-bench-mock
	$(PYTHON) harness/5-formal-campaign/code/run_campaign.py harness/5-formal-campaign/code/examples/mock-campaign.json --results-root /tmp/llm-bench-mock
	CAMPAIGN="$$(find /tmp/llm-bench-mock -name RUNS_COMPLETE -print -quit | xargs dirname)"; \
	$(PYTHON) harness/6-accept-and-publish/code/aggregate_campaign.py "$$CAMPAIGN"; \
	$(PYTHON) harness/5-formal-campaign/code/finalize_campaign.py "$$CAMPAIGN" --allow-missing-post-idle
