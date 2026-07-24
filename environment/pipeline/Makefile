.PHONY: build clean run

build:
	mkdir -p binary
	go build -o binary/tripfix ./kernel/kernel_main

clean:
	rm -f binary/tripfix
	rm -f ledger/output.json

run: build
	./binary/tripfix
