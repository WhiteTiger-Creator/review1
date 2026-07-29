CC ?= gcc
CFLAGS ?= -O2 -g -Wall -Wextra -Iinclude -Iv3 -Iw6 -Ix1 -Iy8 -Iz2 -Idrv -Idecoy -Iutil
SRCS = util/fnv.c v3/fold.c w6/score.c x1/step.c y8/page.c z2/epoch.c \
	drv/init.c drv/emit.c drv/ops_fold.c drv/ops_fit.c drv/ops_page.c drv/ops_epoch.c \
	drv/load_cases.c drv/ops_cycle.c drv/main.c decoy/idle.c decoy/note.c
OBJS = $(SRCS:.c=.o)
.PHONY: all clean install
all: percctl
percctl: $(OBJS)
	$(CC) $(CFLAGS) -o $@ $(OBJS) -lm
%.o: %.c
	$(CC) $(CFLAGS) -c -o $@ $<
install: percctl
	mkdir -p /app/bin /app/output /app/var/model
	cp percctl /app/bin/percctl
clean:
	rm -f $(OBJS) percctl
