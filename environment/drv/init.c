#include "ops.h"
#include <string.h>
int desk_init(struct desk *d) {
	memset(d, 0, sizeof(*d));
	d->m.generation = 1;
	d->m.persist_id = BOOT_PERSIST;
	return 0;
}
