PYTHON ?= python3
LEANTEX = PYTHONPATH=../.. $(PYTHON) -m leantex
TEX ?= minimal.tex

all: build

build:
	$(LEANTEX) build $(TEX)

build-no-pdf:
	$(LEANTEX) build $(TEX) --no-latexmk

minimal:
	$(LEANTEX) build minimal.tex

test4:
	$(LEANTEX) build test4.tex

clean:
	latexmk -C $(TEX)
	rm -rf LeanTeX leantex.generated.tex
