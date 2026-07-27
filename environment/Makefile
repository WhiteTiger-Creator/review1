CC := gcc
CFLAGS := -std=c17 -O2 -Wall -Wextra -Werror
CPPFLAGS := -I include
LDLIBS := -ljson-c
TARGET := /app/bin/ris-evidence-gate

.PHONY: all clean

all: $(TARGET)

$(TARGET): src/ris_evidence_gate.c include/ris_evidence_gate.h
	mkdir -p /app/bin
	$(CC) $(CPPFLAGS) $(CFLAGS) src/ris_evidence_gate.c -o $@ $(LDLIBS)

clean:
	rm -f $(TARGET)
