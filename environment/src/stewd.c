/* stewd - Fallowfield yard steward daemon.
 * State: /opt/steward/state/{roster.tsv,dispositions.tsv,gate,pools.tsv,applied.tsv}
 * Socket: /run/steward.sock, line protocol:
 *   STATUS | ROSTER | DISPOSE <host> <verb>[ <slots>] | UNDISPOSE <host> | RESUME
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <signal.h>
#include <errno.h>

#define STATE "/opt/steward/state"
#define SOCKP "/run/steward.sock"
#define MAXH 64
#define MAXSLOTS 64

typedef struct {
    char host[16], pod[16], rack[8];
    int racked;
    char verb[16];              /* "", graduate, continue, restart */
    int slots[MAXSLOTS], nslots;
} Host;

static Host hosts[MAXH];
static int nhosts = 0;
static char gate[16] = "closed";

static Host *find(const char *h) {
    for (int i = 0; i < nhosts; i++)
        if (!strcmp(hosts[i].host, h)) return &hosts[i];
    return NULL;
}

static void load_roster(void) {
    FILE *f = fopen(STATE "/roster.tsv", "r");
    char line[256];
    if (!f) { fprintf(stderr, "stewd: no roster\n"); exit(1); }
    if (!fgets(line, sizeof line, f)) { fclose(f); exit(1); }   /* header */
    while (fgets(line, sizeof line, f) && nhosts < MAXH) {
        Host *h = &hosts[nhosts];
        char rk[16];
        if (sscanf(line, "%15s\t%15s\t%7s\t%15s",
                   h->host, h->pod, h->rack, rk) == 4) {
            h->racked = atoi(rk + 1);
            h->verb[0] = 0; h->nslots = 0;
            nhosts++;
        }
    }
    fclose(f);
}

static void load_gate(void) {
    FILE *f = fopen(STATE "/gate", "r");
    if (f) { if (fscanf(f, "%15s", gate) != 1) strcpy(gate, "closed");
             fclose(f); }
}

static void load_dispositions(void) {
    FILE *f = fopen(STATE "/dispositions.tsv", "r");
    char line[512];
    if (!f) return;
    while (fgets(line, sizeof line, f)) {
        char hn[16], vb[16], sl[384] = "";
        int n = sscanf(line, "%15s\t%15s\t%383s", hn, vb, sl);
        if (n < 2) continue;
        Host *h = find(hn);
        if (!h) continue;
        strcpy(h->verb, vb);
        h->nslots = 0;
        if (n == 3 && !strcmp(vb, "continue")) {
            char *tok = strtok(sl, ",");
            while (tok && h->nslots < MAXSLOTS) {
                if (tok[0] == 'S') h->slots[h->nslots++] = atoi(tok + 1);
                tok = strtok(NULL, ",");
            }
        }
    }
    fclose(f);
}

static void save_dispositions(void) {
    FILE *f = fopen(STATE "/dispositions.tsv", "w");
    if (!f) return;
    for (int i = 0; i < nhosts; i++) {
        Host *h = &hosts[i];
        if (!h->verb[0]) continue;
        if (!strcmp(h->verb, "continue")) {
            fprintf(f, "%s\t%s\t", h->host, h->verb);
            for (int j = 0; j < h->nslots; j++)
                fprintf(f, "%sS%d", j ? "," : "", h->slots[j]);
            fprintf(f, "\n");
        } else {
            fprintf(f, "%s\t%s\n", h->host, h->verb);
        }
    }
    fclose(f);
}

static void save_gate(const char *v) {
    FILE *f = fopen(STATE "/gate", "w");
    if (f) { fprintf(f, "%s\n", v); fclose(f); }
    strcpy(gate, v);
}

static int cmp_rack(const void *a, const void *b) {
    const Host *x = *(Host * const *)a, *y = *(Host * const *)b;
    return strcmp(x->rack, y->rack);
}

static int do_resume(char *err, size_t elen) {
    /* every rostered host disposed */
    for (int i = 0; i < nhosts; i++)
        if (!hosts[i].verb[0]) {
            snprintf(err, elen, "ERR undisposed hosts remain (%s)",
                     hosts[i].host);
            return -1;
        }
    /* per-pod slot capacity <= 8 per shift */
    for (int s = 49; s <= 120; s++) {
        const char *pods[3] = {"north", "mid", "south"};
        for (int p = 0; p < 3; p++) {
            int c = 0;
            for (int i = 0; i < nhosts; i++) {
                Host *h = &hosts[i];
                if (strcmp(h->verb, "continue") || strcmp(h->pod, pods[p]))
                    continue;
                for (int j = 0; j < h->nslots; j++)
                    if (h->slots[j] == s) c++;
            }
            if (c > 8) {
                snprintf(err, elen, "ERR slot capacity exceeded S%d %s",
                         s, pods[p]);
                return -1;
            }
        }
    }
    /* apply: pools placement (pod cell, next free position in rack order) */
    FILE *pf = fopen(STATE "/pools.tsv", "w");
    if (!pf) { snprintf(err, elen, "ERR state write"); return -1; }
    const char *pods[3] = {"north", "mid", "south"};
    for (int p = 0; p < 3; p++) {
        Host *sel[MAXH]; int ns = 0;
        for (int i = 0; i < nhosts; i++)
            if (!strcmp(hosts[i].verb, "graduate") &&
                !strcmp(hosts[i].pod, pods[p]))
                sel[ns++] = &hosts[i];
        qsort(sel, ns, sizeof sel[0], cmp_rack);
        for (int i = 0; i < ns; i++)
            fprintf(pf, "%s\t%s-cell\t%d\n", sel[i]->host, pods[p], i + 1);
    }
    fclose(pf);
    FILE *af = fopen(STATE "/applied.tsv", "w");
    if (!af) { snprintf(err, elen, "ERR state write"); return -1; }
    for (int i = 0; i < nhosts; i++) {
        Host *h = &hosts[i];
        if (!strcmp(h->verb, "continue")) {
            fprintf(af, "%s\t%s\t", h->host, h->verb);
            for (int j = 0; j < h->nslots; j++)
                fprintf(af, "%sS%d", j ? "," : "", h->slots[j]);
            fprintf(af, "\n");
        } else {
            fprintf(af, "%s\t%s\n", h->host, h->verb);
        }
    }
    fclose(af);
    save_gate("open");
    return 0;
}

static void handle(int c) {
    char buf[1024], out[1024];
    ssize_t n = read(c, buf, sizeof buf - 1);
    if (n <= 0) return;
    buf[n] = 0;
    char *nl = strchr(buf, '\n');
    if (nl) *nl = 0;
    char cmd[16] = "", a1[32] = "", a2[16] = "", a3[512] = "";
    sscanf(buf, "%15s %31s %15s %511s", cmd, a1, a2, a3);
    out[0] = 0;

    if (!strcmp(cmd, "STATUS")) {
        int d = 0;
        for (int i = 0; i < nhosts; i++) if (hosts[i].verb[0]) d++;
        snprintf(out, sizeof out, "gate=%s serving=%s disposed=%d/%d\n",
                 gate, strcmp(gate, "open") ? "no" : "yes", d, nhosts);
    } else if (!strcmp(cmd, "ROSTER")) {
        size_t off = 0;
        for (int i = 0; i < nhosts && off < sizeof out - 64; i++)
            off += snprintf(out + off, sizeof out - off, "%s %s %s S%d %s\n",
                            hosts[i].host, hosts[i].pod, hosts[i].rack,
                            hosts[i].racked,
                            hosts[i].verb[0] ? hosts[i].verb : "-");
    } else if (!strcmp(cmd, "DISPOSE")) {
        Host *h = find(a1);
        if (!strcmp(gate, "open"))
            snprintf(out, sizeof out, "ERR gate open\n");
        else if (!h)
            snprintf(out, sizeof out, "ERR unknown host\n");
        else if (!strcmp(a2, "graduate") || !strcmp(a2, "restart")) {
            strcpy(h->verb, a2); h->nslots = 0;
            save_dispositions();
            snprintf(out, sizeof out, "OK %s %s\n", a1, a2);
        } else if (!strcmp(a2, "continue")) {
            int sl[MAXSLOTS], ns = 0, bad = 0;
            char tmp[512]; strncpy(tmp, a3, sizeof tmp - 1);
            tmp[sizeof tmp - 1] = 0;
            char *tok = strtok(tmp, ",");
            while (tok) {
                if (tok[0] != 'S' || atoi(tok + 1) < 49) { bad = 1; break; }
                if (ns < MAXSLOTS) sl[ns++] = atoi(tok + 1);
                tok = strtok(NULL, ",");
            }
            if (bad || ns == 0)
                snprintf(out, sizeof out,
                         "ERR continue needs future slots S49+\n");
            else {
                strcpy(h->verb, "continue");
                memcpy(h->slots, sl, sizeof sl[0] * ns);
                h->nslots = ns;
                save_dispositions();
                snprintf(out, sizeof out, "OK %s continue %d slots\n", a1, ns);
            }
        } else
            snprintf(out, sizeof out, "ERR bad verb\n");
    } else if (!strcmp(cmd, "UNDISPOSE")) {
        Host *h = find(a1);
        if (!strcmp(gate, "open"))
            snprintf(out, sizeof out, "ERR gate open\n");
        else if (!h)
            snprintf(out, sizeof out, "ERR unknown host\n");
        else {
            h->verb[0] = 0; h->nslots = 0;
            save_dispositions();
            snprintf(out, sizeof out, "OK %s cleared\n", a1);
        }
    } else if (!strcmp(cmd, "RESUME")) {
        char err[128];
        if (!strcmp(gate, "open"))
            snprintf(out, sizeof out, "ERR gate open\n");
        else if (do_resume(err, sizeof err))
            snprintf(out, sizeof out, "%s\n", err);
        else
            snprintf(out, sizeof out, "OK intake serving\n");
    } else {
        snprintf(out, sizeof out, "ERR bad command\n");
    }
    if (write(c, out, strlen(out)) < 0) { /* peer gone */ }
}

int main(void) {
    signal(SIGPIPE, SIG_IGN);
    load_roster();
    load_gate();
    load_dispositions();

    unlink(SOCKP);
    int s = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof addr);
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, SOCKP, sizeof addr.sun_path - 1);
    if (bind(s, (struct sockaddr *)&addr, sizeof addr) || listen(s, 8)) {
        perror("stewd: bind");
        return 1;
    }
    chmod(SOCKP, 0666);
    for (;;) {
        int c = accept(s, NULL, NULL);
        if (c < 0) { if (errno == EINTR) continue; break; }
        handle(c);
        close(c);
    }
    return 0;
}
