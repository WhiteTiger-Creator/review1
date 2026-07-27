# Edge routing topology

The router is `edge-ams-01`, local AS3333, with router id `192.0.2.10`.

| Role | IPv4 neighbor | IPv6 neighbor | Remote AS | Inbound local preference during maintenance |
| --- | --- | --- | --- | --- |
| primary transit-a | 192.0.2.2 | 2001:db8:10::2 | 64501 | 80 |
| standby transit-b | 192.0.2.6 | 2001:db8:20::2 | 64502 | 250 |

The intended originations are exactly `193.0.0.0/21` and `2001:67c:2e8::/48`. More-specific originations are prohibited. The maintenance export route-map is named `OUT-STANDBY-EXACT`; inbound maps are `IN-PRIMARY-MAINT` and `IN-STANDBY-MAINT`. The exact aggregate prefix-lists are `INTENDED-V4` and `INTENDED-V6`.
