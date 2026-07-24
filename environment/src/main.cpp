#include "config.hpp"
#include "report.hpp"
#include "verifier.hpp"

#include <cstdlib>
#include <iostream>

static const char* kConfigPath = "/app/config/trust_policy.json";
static const char* kReportPath = "/app/output/rollout_report.json";

static void print_help() {
    std::cout << "TUF metadata rollout verifier\n"
              << "Usage: tuf-rollout-verifier [--help]\n"
              << "Reads trust policy and repository metadata, writes rollout report.\n";
}

int main(int argc, char* argv[]) {
    if (argc > 1) {
        std::string arg = argv[1];
        if (arg == "--help" || arg == "-h") {
            print_help();
            return 0;
        }
    }

    TrustPolicy policy;
    if (!load_trust_policy(kConfigPath, policy)) {
        std::cerr << "failed to load trust policy\n";
        return 1;
    }

    RolloutReport report;
    if (!run_verification(policy, report)) {
        std::cerr << "verification failed\n";
        return 1;
    }

    if (!write_rollout_report(kReportPath, report)) {
        std::cerr << "failed to write report\n";
        return 1;
    }

    return 0;
}
