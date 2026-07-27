#ifndef RIS_EVIDENCE_GATE_H
#define RIS_EVIDENCE_GATE_H

#define EXIT_POLICY_ERROR 2
#define EXIT_EVIDENCE_ERROR 3
#define EXIT_IO_ERROR 4

struct policy {
    char change_id[96];
    char ipv4_resource[64];
    char ipv6_resource[128];
    char standby_profile[64];
    long expected_origin;
    long min_visibility_percent;
};

#endif
