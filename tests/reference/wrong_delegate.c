#include <stdlib.h>
#include <unistd.h>

int main(void) {
    execl("/app/bin/timers", "timers", (char *)NULL);
    return 1;
}
