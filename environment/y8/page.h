#ifndef PAGE_H
#define PAGE_H
#include "perc.h"
int page_publish(struct desk *d);
int page_tear(struct desk *d);
int page_recover(struct desk *d);
int page_load_model(struct desk *d);
#endif
