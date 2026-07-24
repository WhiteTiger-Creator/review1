#pragma once

#include "../core/types.hpp"

#include <vector>

double num_mass_observe(const std::vector<double>& owned, double dx, int n_global, int rank,
                        int nproc);
