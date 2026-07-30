.PHONY: all clean report run-one
all:
	go build -o bin/certctl ./cmd/certctl
clean:
	rm -f bin/certctl
report:
	./bin/certctl --all --out /app/output/certification_report.json
run-one:
	./bin/certctl --site $(SITE) --out $(OUT)
