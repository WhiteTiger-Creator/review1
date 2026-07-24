#include "n3.h"

#include <math.h>

double n3_fd_probe(double f0, double f1, double h) {
    if (h <= 0.0) {
        return 0.0;
    }
    return (f1 - f0) / h;
}

double n3_probe_chain(double base, double dt, int steps) {
    double v = base;
    for (int i = 0; i < steps; i++) {
        v = n3_fd_probe(v, v + dt * 0.01, dt);
    }
    return v;
}
