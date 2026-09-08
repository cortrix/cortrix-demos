.PHONY: validate test live-demo-test live-demo-harness-test public-safety full-stack fresh-clone-verify viewer

PYTHON ?= python3.14
NODE ?= node
VIEWER_BIND ?= 127.0.0.1
VIEWER_PORT ?= 18765

validate: test live-demo-test public-safety

test:
	PYTHONPATH=packages/runner/src $(PYTHON) -m unittest discover -s tests -v

live-demo-test:
	PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/live_demo/src $(PYTHON) -m unittest discover -s packages/live_demo/tests -p 'test_*.py' -v
	DEMO_UNIT_ONLY=1 $(NODE) --test packages/live_demo/tests/harness-contract-tests.mjs

live-demo-harness-test:
	@test -n "$(DEMO_HARNESS_ROOT)"
	@DEMO_UNIT_ONLY=1 DEMO_HARNESS_ROOT="$(DEMO_HARNESS_ROOT)" DEMO_HARNESS_COMMIT=99f6f02fecdb7dff40c3fbc9470f5907c29f74ca $(NODE) --test packages/live_demo/tests/harness-tests.mjs

public-safety:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner public-safety --root .

full-stack:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner run-full-stack --root .

fresh-clone-verify:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner fresh-clone-verify --root .

viewer:
	$(PYTHON) packages/viewer/serve.py --bind $(VIEWER_BIND) --port $(VIEWER_PORT)
