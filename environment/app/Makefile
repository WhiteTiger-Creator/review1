.PHONY: all build clean

PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin

all: build

build:
	@mkdir -p $(BINDIR)
	@printf '%s\n' '#!/usr/bin/env python3' 'from wtac.cli import main' 'raise SystemExit(main())' > $(BINDIR)/wtac-validate
	@chmod +x $(BINDIR)/wtac-validate
	@test -x $(BINDIR)/wtac-validate

clean:
	@rm -f $(BINDIR)/wtac-validate
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
