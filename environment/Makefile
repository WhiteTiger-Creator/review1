CC ?= gcc
CFLAGS ?= -Wall -Wextra -O2 -Ilib -Icast -Ilibm -Itile -Iadv -Iverify -Ir8 -Iio
LDFLAGS ?= -lm

BIN ?= /app/bin/q7
OBJDIR = build

SRCS = lib/profile.c lib/ast.c \
       cast/m4.c cast/lane_z9.c cast/p7.c cast/stage_emit.c \
       libm/r2.c libm/span_order.c libm/s5.c libm/stage_bind.c \
       tile/k9.c tile/n3.c tile/stage_jac.c \
       adv/w1.c adv/stage_step.c \
       verify/z9_val.c verify/t3.c \
       r8/ledger.c r8/checkpoint.c r8/mode_ctrl.c r8/mode_resume.c \
       io/fixt_load.c io/segment.c \
       cmd/q7/main.c

OBJS = $(SRCS:%.c=$(OBJDIR)/%.o)

.PHONY: all clean

all: $(BIN)

$(OBJDIR)/%.o: %.c
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

$(BIN): $(OBJS)
	@mkdir -p $(dir $(BIN))
	$(CC) $(CFLAGS) -o $@ $(OBJS) $(LDFLAGS)
	chmod +x cmd/q7/run.sh

clean:
	rm -rf $(OBJDIR) $(BIN)
