# Channel contract

Training packs and online serving must land on the same ordered little-endian f32 channel layout for each schema revision.

For the baseline revision the ordered names are u_a, u_b, u_c, then u_d. Each name occupies four bytes. A finished channel view spans four bytes times the number of names.

Revision one renames u_a to v_a and u_c to v_c while u_b and u_d keep their wire labels. Wire order in a revision-one blob may list the renamed labels; after resolution the bytes must still sit in the baseline canonical indices.

Revision two inserts nullable name w_n after u_b, so the ordered names become u_a, u_b, w_n, u_c, then u_d.

Revision three tries to omit u_c. Catalog policy forbids that omission, so the join must not quietly shrink the view and feed a shortened zero-padded blob into scoring.

A geometry digest is the lowercase sixteen-hex FNV-1a of the resolved little-endian f32 bytes in canonical name order. Offline materialization and online serving for the same revision must emit matching digests once name maps and defaults have been applied.
