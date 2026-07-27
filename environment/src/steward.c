/* steward - yard steward CLI. Talks to stewd on /run/steward.sock;
 * starts the daemon if it is not running. */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>

#define SOCKP "/run/steward.sock"

static int conn(void) {
    int s = socket(AF_UNIX, SOCK_STREAM, 0);
    struct sockaddr_un a;
    memset(&a, 0, sizeof a);
    a.sun_family = AF_UNIX;
    strncpy(a.sun_path, SOCKP, sizeof a.sun_path - 1);
    if (connect(s, (struct sockaddr *)&a, sizeof a)) { close(s); return -1; }
    return s;
}

static void ensure_daemon(void) {
    int s = conn();
    if (s >= 0) { close(s); return; }
    pid_t p = fork();
    if (p == 0) {
        setsid();
        freopen("/dev/null", "r", stdin);
        freopen("/dev/null", "w", stdout);
        freopen("/dev/null", "w", stderr);
        execl("/usr/local/bin/stewd", "stewd", (char *)NULL);
        _exit(127);
    }
    for (int i = 0; i < 60; i++) {
        struct timespec ts = {0, 50 * 1000 * 1000};
        nanosleep(&ts, NULL);
        s = conn();
        if (s >= 0) { close(s); return; }
    }
}

static void usage(void) {
    puts("usage: steward <command>");
    puts("  status                              gate and serving state");
    puts("  roster                              hosts and current dispositions");
    puts("  dispose <host> graduate             mark host for graduation");
    puts("  dispose <host> continue S49,S50,..  assign continuation slots");
    puts("  dispose <host> restart              mark host for intake restart");
    puts("  undispose <host>                    clear a disposition");
    puts("  resume                              apply dispositions, open intake");
}

int main(int argc, char **argv) {
    if (argc < 2) { usage(); return 2; }
    char req[1024] = "";
    if (!strcmp(argv[1], "status") && argc == 2)
        snprintf(req, sizeof req, "STATUS\n");
    else if (!strcmp(argv[1], "roster") && argc == 2)
        snprintf(req, sizeof req, "ROSTER\n");
    else if (!strcmp(argv[1], "dispose") && argc == 4)
        snprintf(req, sizeof req, "DISPOSE %s %s\n", argv[2], argv[3]);
    else if (!strcmp(argv[1], "dispose") && argc == 5)
        snprintf(req, sizeof req, "DISPOSE %s %s %s\n",
                 argv[2], argv[3], argv[4]);
    else if (!strcmp(argv[1], "undispose") && argc == 3)
        snprintf(req, sizeof req, "UNDISPOSE %s\n", argv[2]);
    else if (!strcmp(argv[1], "resume") && argc == 2)
        snprintf(req, sizeof req, "RESUME\n");
    else { usage(); return 2; }

    ensure_daemon();
    int s = conn();
    if (s < 0) { fprintf(stderr, "steward: daemon unavailable\n"); return 1; }
    if (write(s, req, strlen(req)) < 0) { close(s); return 1; }
    char buf[4096];
    ssize_t n;
    int rc = 0;
    while ((n = read(s, buf, sizeof buf - 1)) > 0) {
        buf[n] = 0;
        fputs(buf, stdout);
        if (!strncmp(buf, "ERR", 3)) rc = 1;
    }
    close(s);
    return rc;
}
