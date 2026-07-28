SHELL := /bin/bash
APP_DIR := /app
BIN_DIR := $(APP_DIR)/bin
BUILD_DIR := $(APP_DIR)/build
C_DIR := $(APP_DIR)/c
CC := gcc
AR := ar
GO := /usr/local/go/bin/go
CFLAGS := -O2 -g -std=c11 -Wall -Wextra -Werror -fPIC -I$(C_DIR)
GO_BUILD := env CGO_ENABLED=1 GOMAXPROCS=1 $(GO) build -mod=readonly -p=1 -trimpath
.PHONY: all build clean
all: build
build: $(BIN_DIR)/orbit-api $(BIN_DIR)/orbit-certify $(BIN_DIR)/fft-check
$(BUILD_DIR) $(BIN_DIR):
	mkdir -p $@
$(BUILD_DIR)/fftw_bridge.o: $(C_DIR)/fftw_bridge.c $(C_DIR)/orbit_fft.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD_DIR)/radial.o: $(C_DIR)/radial.c $(C_DIR)/orbit_fft.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) -c $< -o $@
$(BUILD_DIR)/liborbitfft.a: $(BUILD_DIR)/fftw_bridge.o $(BUILD_DIR)/radial.o
	$(AR) rcs $@ $^
$(BIN_DIR)/orbit-api: $(shell find cmd/orbit-api internal/api internal/catalog internal/registrybridge -type f -name '*.go') | $(BIN_DIR)
	$(GO_BUILD) -o $@ ./cmd/orbit-api
$(BIN_DIR)/orbit-certify: $(BUILD_DIR)/liborbitfft.a $(shell find cmd/orbit-certify internal -type f -name '*.go' ! -path 'internal/api/*') | $(BIN_DIR)
	$(GO_BUILD) -o $@ ./cmd/orbit-certify
$(BIN_DIR)/fft-check: tools/fft-check.c $(C_DIR)/radial.c $(C_DIR)/orbit_fft.h | $(BIN_DIR)
	$(CC) $(CFLAGS) tools/fft-check.c $(C_DIR)/radial.c -o $@ -lm
clean:
	rm -rf $(BUILD_DIR) $(BIN_DIR)
