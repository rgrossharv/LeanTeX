TEX=minimal.tex

all:
	PYTHONPATH=../.. python3 -m leantex build $(TEX)

build-no-pdf:
	PYTHONPATH=../.. python3 -m leantex build $(TEX) --no-latexmk

clean:
	latexmk -C $(TEX)
	rm -rf LeanTeX leantex.generated.tex
