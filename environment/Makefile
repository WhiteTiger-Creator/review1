GO ?= go
QD := /app/bin/qd
ENV := $(CURDIR)

.PHONY: all build install
all: build install

build:
	cd $(ENV) && $(GO) build -o $(QD) ./cmd/qd

install:
	mkdir -p /app/bin /app/output /app/p9
	rm -rf /app/w8
	ln -sfn $(ENV)/w8 /app/w8
	ln -sfn $(ENV)/p9/q1.contract /app/p9/q1.contract
