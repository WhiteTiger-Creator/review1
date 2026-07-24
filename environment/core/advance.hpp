#pragma once

#include "types.hpp"

#include <vector>

double adv_dx(int n_global);
void adv_init_bump(int n_global, int seed, std::vector<double>& u);
void adv_decompose(int n_global, int nproc, int rank, int& lo, int& hi, int& loc_n);
void adv_extract_local(const std::vector<double>& global, int lo, int hi, int n_global,
                       std::vector<double>& owned, std::vector<double>& glo,
                       std::vector<double>& ghi, std::vector<int>& gids);
void adv_assemble_preview(const std::vector<double>& owned, const std::vector<double>& glo,
                          const std::vector<double>& ghi, const std::vector<int>& gids,
                          int n_global, std::vector<double>& global);
double adv_total_mass(const std::vector<double>& owned, double dx);
double adv_pick_dt(double kappa, double dx, double dt0, double cfl);
double adv_cfl_limit(double kappa, double dx, double cfl);
double adv_max_abs_delta(const std::vector<double>& before, const std::vector<double>& after);
int adv_ftcs_step(std::vector<double>& owned, const std::vector<double>& glo,
                  const std::vector<double>& ghi, double kappa, double dx, double dt, int lo, int hi,
                  int n_global);
int adv_ftcs_trial(const std::vector<double>& owned, const std::vector<double>& glo,
                   const std::vector<double>& ghi, double kappa, double dx, double dt, int lo, int hi,
                   int n_global, std::vector<double>& next);
std::string adv_fingerprint(const RunCfg& cfg, const ProfKnobs& prof);
double adv_field_cksum(const std::vector<double>& global);
