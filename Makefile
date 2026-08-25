.PHONY: validate test public-safety public-history-safety full-stack fresh-clone-verify viewer viewer-candidate-qa viewer-harness

PYTHON ?= python3.14
VIEWER_BIND ?= 127.0.0.1
VIEWER_PORT ?= 18765

validate: test public-safety

test:
	PYTHONPATH=packages/runner/src $(PYTHON) -m unittest discover -s tests -v

public-safety:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner public-safety --root .

public-history-safety:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner public-history-safety --root . --base-ref "$(BASE_REF)"

full-stack:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner run-full-stack --root .

fresh-clone-verify:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner fresh-clone-verify --root .

viewer:
	$(PYTHON) packages/viewer/serve.py --bind $(VIEWER_BIND) --port $(VIEWER_PORT)

viewer-candidate-qa:
	$(PYTHON) packages/viewer/serve.py --bind $(VIEWER_BIND) --port $(VIEWER_PORT) --candidate-run-id "$(RUN_ID)"

viewer-harness:
	$(PYTHON) packages/viewer/serve.py --bind $(VIEWER_BIND) --port $(VIEWER_PORT) --harness-scenario "$(SCENARIO)"
