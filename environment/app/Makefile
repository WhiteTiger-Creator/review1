.PHONY: dispatch clean

dispatch:
	PERL5LIB=/app/lamps perl /app/lamps/dispatch.pl "$(PANEL)" "$(OUT)"

clean:
	rm -f /app/out/beacon.queue /app/out/runner.fold
	find /app/notes -mindepth 1 ! -name .keep -delete 2>/dev/null || true
