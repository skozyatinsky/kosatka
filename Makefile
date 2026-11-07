# ======================================================================
# Makefile — iskinosfera-orca (FILE_AND_FOLDER_STANDARD §2.1, §2.2)
# ======================================================================

.PHONY: all run build test lint clean

all: build

run:
	pnpm run dev

build:
	./build.sh --target-all

test:
	pnpm test

lint:
	pnpm run lint

clean:
	./build.sh --clean
