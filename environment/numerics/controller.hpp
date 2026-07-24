#pragma once

#include "../core/types.hpp"

#include <vector>

CtrlState num_ctrl_defaults(const ProfKnobs& prof, double kappa, double dx);
int num_ctrl_advance(std::vector<double>& owned, std::vector<double>& glo, std::vector<double>& ghi,
                     CtrlState& ctrl, HistRec& hist, const ProfKnobs& prof, double kappa, double dx,
                     int lo, int hi, int n_global, int rank, int nproc);
CtrlState num_ctrl_restore(const GlobRec& glob, const ProfKnobs& prof, double kappa, double dx);
