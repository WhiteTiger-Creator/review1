GO ?= go
TARGET = /app/bin/basin-flux

all: $(TARGET)

$(TARGET):
	mkdir -p /app/bin
	$(GO) build -o $(TARGET) ./cmd/basin-flux

clean:
	rm -f $(TARGET)

.PHONY: all clean
