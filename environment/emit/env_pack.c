#include "ship_api.h"

#include <stdlib.h>
#include <string.h>

const char *pack_label_from_env(void) {
    const char *keys[] = {"LC_ALL", "LANG", "LC_NUMERIC", NULL};
    for (int i = 0; keys[i]; i++) {
        const char *v = getenv(keys[i]);
        if (v && strstr(v, "de_DE")) {
            return "de_DE";
        }
    }
    return "C";
}
