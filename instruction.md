# Adjudicate the Abalone tournament replay

Serve as head referee for a disputed Abalone match. This is exclusively a
competitive tabletop-game officiating and combinatorial game-analysis
exercise. Apply the `official_handbook` entry in
`/app/input/match.json`; it is the complete authority for the board rules,
replay rulings, tournament endings, continuation certificate, and official
report.

Submit the ruling through the tournament desk's Go harness. The desk compiles
the files in `/app` as `/app/abalone`, then runs that executable without
arguments. It must preserve `/app/input/match.json` byte-for-byte and replace
`/app/output/report.json` with the exact report required by the handbook.
Compatible unseen match records are also adjudicated.

Every legal continuation occurrence must contribute to the handbook's node
census, leaf census, root analyses, and recursive digest, including occurrences
that reach the same position by different histories. The report must also
reflect cooldown motion, momentum acquisition and spending, tactical
quiescence extensions, ejection, ko rollback, and symmetry exactly. Each
adjudication has 180 seconds on one CPU. Submit only the report-producing files;
do not alter the match evidence.
