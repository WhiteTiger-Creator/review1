#include "emsolve/modes.hpp"

#include <algorithm>
#include <cmath>

namespace emsolve {

namespace {

static int argmax_abs(const Eigen::VectorXd& v) {
  int best = 0;
  double best_val = 0.0;
  for (int i = 0; i < v.size(); ++i) {
    const double a = std::abs(v(i));
    if (a >= best_val) {
      best_val = a;
      best = i;
    }
  }
  return best;
}

static std::vector<int> cluster_indices(const std::vector<double>& lambdas, double tol) {
  std::vector<int> order(lambdas.size());
  for (size_t i = 0; i < order.size(); ++i) order[i] = static_cast<int>(i);
  std::sort(order.begin(), order.end(),
            [&](int a, int b) { return lambdas[static_cast<size_t>(a)] < lambdas[static_cast<size_t>(b)]; });

  std::vector<int> cluster(lambdas.size(), 0);
  int cid = 0;
  for (size_t i = 0; i < order.size(); ++i) {
    if (i > 0 && std::abs(lambdas[static_cast<size_t>(order[i])] -
                          lambdas[static_cast<size_t>(order[i - 1])]) > tol) {
      ++cid;
    }
    cluster[static_cast<size_t>(order[i])] = cid;
  }
  return cluster;
}

}  // namespace

ModesOutput prepare_modes(int requested, const std::vector<double>& lambdas,
                          const std::vector<Eigen::VectorXd>& vectors,
                          const std::vector<ModeDiagnostics>& diags,
                          const std::vector<int>* /*cluster_ids*/) {
  struct Item {
    double lambda{0.0};
    Eigen::VectorXd vec;
    ModeDiagnostics diag;
  };

  ModesOutput out;
  out.requested = requested;
  out.computed = static_cast<int>(lambdas.size());

  std::vector<Item> items;
  items.reserve(lambdas.size());
  for (size_t i = 0; i < lambdas.size(); ++i) {
    items.push_back({lambdas[i], vectors[i], diags[i]});
  }

  std::sort(items.begin(), items.end(), [](const Item& a, const Item& b) {
    if (std::abs(a.lambda - b.lambda) > 1e-9) return a.lambda < b.lambda;
    return argmax_abs(a.vec) < argmax_abs(b.vec);
  });

  std::vector<double> sorted_lambdas;
  sorted_lambdas.reserve(items.size());
  for (const auto& item : items) sorted_lambdas.push_back(item.lambda);
  const auto clusters = cluster_indices(sorted_lambdas, 1e-7);

  out.modes.reserve(items.size());
  for (size_t i = 0; i < items.size(); ++i) {
    ModeRecord rec;
    rec.index = static_cast<int>(i);
    rec.eigenvalue = items[i].lambda;
    rec.diagnostics = items[i].diag;
    rec.cluster_id = clusters[i];
    rec.coefficients.resize(static_cast<size_t>(items[i].vec.size()));
    for (int c = 0; c < items[i].vec.size(); ++c) {
      rec.coefficients[static_cast<size_t>(c)] = items[i].vec(c);
    }
    out.modes.push_back(std::move(rec));
  }
  return out;
}

}  // namespace emsolve
