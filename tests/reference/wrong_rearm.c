/* A cancelled id is armable again straight away, with no memory of the
   cancel carried to the rest of the current advance window. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MAXT 8192
#define IDS 65536
#define LVLS 4
#define SLOTS 256
#define MAXOPS 20000
#define MAXADV 33554432u

static uint32_t g_now;
static int32_t g_head[LVLS][SLOTS];
static int32_t g_next[MAXT];
static uint32_t g_expires[MAXT];
static uint32_t g_ident[MAXT];
static int32_t g_slot[MAXT];
static int32_t g_lookup[IDS];
static int32_t g_pool[MAXT];
static int32_t g_pooltop;
static uint32_t g_live;
static uint32_t g_digest;
static uint32_t g_fired[MAXT];

static uint32_t rotl32(uint32_t v, unsigned r) {
    return (v << r) | (v >> (32u - r));
}

static void place(int32_t node) {
    uint32_t expires = g_expires[node];
    uint32_t delta = expires - g_now;
    uint32_t idx;
    int lvl;
    if ((int32_t)delta <= 0) {
        delta = 0;
        expires = g_now;
        g_expires[node] = expires;
    }
    if (delta < 256u) {
        lvl = 0;
        idx = expires & 255u;
    } else if (delta < 65536u) {
        lvl = 1;
        idx = (expires >> 8) & 255u;
    } else if (delta < 16777216u) {
        lvl = 2;
        idx = (expires >> 16) & 255u;
    } else {
        lvl = 3;
        idx = (expires >> 24) & 255u;
    }
    g_next[node] = g_head[lvl][idx];
    g_head[lvl][idx] = node;
    g_slot[node] = lvl * SLOTS + (int32_t)idx;
}

static void unlink_node(int32_t node) {
    int32_t slot = g_slot[node];
    int32_t *cur = &g_head[slot >> 8][slot & 255];
    while (*cur >= 0) {
        if (*cur == node) {
            *cur = g_next[node];
            return;
        }
        cur = &g_next[*cur];
    }
}

static void cascade(int lvl, uint32_t idx) {
    int32_t node = g_head[lvl][idx];
    g_head[lvl][idx] = -1;
    while (node >= 0) {
        int32_t nxt = g_next[node];
        place(node);
        node = nxt;
    }
}

static uint32_t tick(uint32_t count) {
    uint32_t index = g_now & 255u;
    int32_t node;
    if (index == 0) {
        uint32_t i1 = (g_now >> 8) & 255u;
        cascade(1, i1);
        if (i1 == 0) {
            uint32_t i2 = (g_now >> 16) & 255u;
            cascade(2, i2);
            if (i2 == 0) {
                cascade(3, (g_now >> 24) & 255u);
            }
        }
    }
    node = g_head[0][index];
    g_head[0][index] = -1;
    while (node >= 0) {
        int32_t nxt = g_next[node];
        uint32_t ident = g_ident[node];
        g_fired[count++] = ident;
        g_digest = rotl32(g_digest ^ ident, 7) + 0x7feb352du;
        g_lookup[ident] = 0;
        g_pool[g_pooltop++] = node;
        g_live--;
        node = nxt;
    }
    g_now++;
    return count;
}

static void fail(const char *token) {
    printf("ERR %s\n", token);
    fflush(stdout);
}

static int digits(const char *s, size_t n) {
    size_t i;
    if (n == 0 || n > 10) {
        return 0;
    }
    for (i = 0; i < n; i++) {
        if (s[i] < '0' || s[i] > '9') {
            return 0;
        }
    }
    return 1;
}

static int split(char *line, char *out[3]) {
    int n = 0;
    char *p = line;
    while (*p) {
        while (*p == ' ') {
            p++;
        }
        if (!*p) {
            break;
        }
        if (n == 3) {
            return -1;
        }
        out[n++] = p;
        while (*p && *p != ' ') {
            p++;
        }
        if (*p) {
            *p++ = 0;
        }
    }
    return n;
}

static int parse(const char *s, uint64_t *v) {
    uint64_t acc = 0;
    size_t i;
    size_t n = strlen(s);
    if (!digits(s, n)) {
        return 0;
    }
    for (i = 0; i < n; i++) {
        acc = acc * 10u + (uint64_t)(s[i] - '0');
    }
    *v = acc;
    return 1;
}

int main(void) {
    char line[80];
    char *field[3];
    uint64_t value[3];
    long ops = 0;
    uint32_t advanced = 0;
    int started = 0;
    int i;
    int j;

    for (i = 0; i < LVLS; i++) {
        for (j = 0; j < SLOTS; j++) {
            g_head[i][j] = -1;
        }
    }
    for (i = 0; i < MAXT; i++) {
        g_pool[i] = MAXT - 1 - i;
    }
    g_pooltop = MAXT;
    g_digest = 0x9e3779b9u;

    while (fgets(line, sizeof(line), stdin)) {
        size_t len = strlen(line);
        int count;
        int k;
        if (len == 0 || line[len - 1] != '\n') {
            fail("syntax");
            return 1;
        }
        line[--len] = 0;
        if (len > 64) {
            fail("syntax");
            return 1;
        }
        count = split(line, field);
        if (count < 1) {
            fail("syntax");
            return 1;
        }
        if (strlen(field[0]) != 1) {
            fail("syntax");
            return 1;
        }
        if (field[0][0] == 'S') {
            if (started || count != 2) {
                fail("syntax");
                return 1;
            }
            if (!parse(field[1], &value[1])) {
                fail("syntax");
                return 1;
            }
            if (value[1] > 4294967295u) {
                fail("range");
                return 1;
            }
            g_now = (uint32_t)value[1];
            started = 1;
            continue;
        }
        if (!started) {
            fail("syntax");
            return 1;
        }
        if (field[0][0] == 'A') {
            if (count != 3) {
                fail("syntax");
                return 1;
            }
        } else if (field[0][0] == 'C' || field[0][0] == 'T') {
            if (count != 2) {
                fail("syntax");
                return 1;
            }
        } else {
            fail("syntax");
            return 1;
        }
        for (k = 1; k < count; k++) {
            if (!parse(field[k], &value[k])) {
                fail("syntax");
                return 1;
            }
        }
        if (field[0][0] == 'A') {
            if (value[1] > 65535u || value[2] > 4294967295u) {
                fail("range");
                return 1;
            }
        } else if (field[0][0] == 'C') {
            if (value[1] > 65535u) {
                fail("range");
                return 1;
            }
        } else {
            if (value[1] < 1u || value[1] > 65535u) {
                fail("range");
                return 1;
            }
        }
        if (ops == MAXOPS) {
            fail("ops");
            return 1;
        }
        ops++;
        if (field[0][0] == 'A') {
            uint32_t ident = (uint32_t)value[1];
            int32_t node;
            if (g_lookup[ident] != 0) {
                continue;
            }
            if (g_live == MAXT) {
                fail("capacity");
                return 1;
            }
            node = g_pool[--g_pooltop];
            g_ident[node] = ident;
            g_expires[node] = (uint32_t)value[2];
            g_lookup[ident] = node + 1;
            g_live++;
            place(node);
        } else if (field[0][0] == 'C') {
            uint32_t ident = (uint32_t)value[1];
            int32_t node = g_lookup[ident];
            if (node == 0) {
                continue;
            }
            node--;
            unlink_node(node);
            g_lookup[ident] = 0;
            g_pool[g_pooltop++] = node;
            g_live--;
        } else {
            uint32_t n = (uint32_t)value[1];
            uint32_t fired = 0;
            uint32_t t;
            if (advanced + n > MAXADV) {
                fail("budget");
                return 1;
            }
            advanced += n;
            for (t = 0; t < n; t++) {
                fired = tick(fired);
            }
            printf("F %u", g_now);
            for (t = 0; t < fired; t++) {
                printf(" %u", g_fired[t]);
            }
            printf("\n");
            g_digest = rotl32(g_digest ^ g_live, 11) + 0x846ca68bu;
            printf("E %u\n", g_live);
        }
    }
    if (!started) {
        fail("syntax");
        return 1;
    }
    printf("D %08x\n", g_digest);
    return 0;
}
