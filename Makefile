.PHONY: validate test public-safety full-stack viewer

PYTHON ?= python3.14

validate: test public-safety

test:
	PYTHONPATH=packages/runner/src $(PYTHON) -m unittest discover -s tests -v

public-safety:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner public-safety --root .

full-stack:
	PYTHONPATH=packages/runner/src $(PYTHON) -m cortrix_demo_runner run-full-stack --root .

viewer:
	$(PYTHON) -m http.server 18765 --bind 192.168.50.75
