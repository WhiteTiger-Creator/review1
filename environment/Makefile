CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -std=gnu11 -D_DEFAULT_SOURCE -Iinclude
PREFIX ?= /app

OBJS = \
	pick/book_load.o \
	pick/scan_snaps.o \
	pick/rank_list.o \
	pick/rank_pick.o \
	emit/fmt_lane.o \
	emit/stage_emit.o \
	emit/env_pack.o \
	journal/stage_io.o \
	archive/memo_pack.o \
	daemon/metricd.o

CHECK_OBJS = \
	pick/book_load.o \
	pick/scan_snaps.o \
	pick/rank_list.o \
	pick/rank_pick.o \
	emit/fmt_lane.o \
	emit/stage_emit.o \
	emit/env_pack.o \
	journal/stage_io.o \
	archive/memo_pack.o \
	tools/check_bin.o

.PHONY: all install clean

all: metricd check_bin

metricd: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS)

check_bin: $(CHECK_OBJS)
	$(CC) $(CFLAGS) -o $@ $(CHECK_OBJS)

%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<

install: all
	mkdir -p $(PREFIX)/bin
	cp metricd $(PREFIX)/bin/metricd
	cp check_bin $(PREFIX)/bin/check_bin
	chmod +x $(PREFIX)/bin/metricd $(PREFIX)/bin/check_bin

clean:
	rm -f $(OBJS) $(CHECK_OBJS) metricd check_bin
