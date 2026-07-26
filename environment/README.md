# Ground-station kernel lockdown fortify gate

Offline security admission tooling that compiles least-privilege sysctl
fortification profiles and audits live kernel probe traces for kptr,
Yama ptrace, dmesg, and unprivileged BPF leaks on satellite ground-station hosts.

Authoritative hardening behavior is defined by the ground lockdown ledger under
`ground-canon/`. Operational notes elsewhere are historical drafts only.
