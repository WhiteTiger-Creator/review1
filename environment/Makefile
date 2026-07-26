.PHONY: build run clean

BINARY := /app/build/salvagectl

build:
	@mkdir -p /app/build
	cd /app && go build -o build/salvagectl ./osfcmd/salvagectl

run: build
	/app/build/salvagectl

clean:
	rm -f /app/build/salvagectl /app/build/fleet_sortie_ledger.json
