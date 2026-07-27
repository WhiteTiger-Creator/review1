CC ?= gcc
CFLAGS ?= -std=c11 -O2 -Wall -Wextra

recovered: src/recovered.c
	mkdir -p build
	$(CC) $(CFLAGS) -o build/recovered src/recovered.c

clean:
	rm -rf build

.PHONY: clean
