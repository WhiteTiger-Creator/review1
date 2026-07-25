Our arcade ran a scoring engine for its Dropforge cabinet, and it is gone.
What survives is the rules card at /app/rules.md, which states only the universal core of well games, and thirty-one recorded games under /app/games/, each holding the full drop script and the true final well and score the old engine produced.
Everything that separates one well game from another is a house convention the card never wrote down: what falls after a clear, what the house paid for a clear and how that changed as a game wore on, what happens at the top edge, how rotations behave at a wall.
The scoring in particular was never a single flat rate, and the recordings are the only evidence for any of it.
Some recordings are only a few pieces long; the techs kept those as probes when the cabinet misbehaved, and each isolates one house rule so its effect can be read on its own before you see it tangled with the others in a full game.
Write /app/engine.js so that `node /app/engine.js <game.json>` replays a game file holding a script and prints the final state as JSON on one line, in exactly the shape of the "final" objects in the recorded games (well, score).
The recordings carry the answer next to the script so you can check yourself; the files your engine gets handed later hold the script alone.
Your engine will be run on other recorded scripts from the same cabinet, so it has to get the conventions right, not just fit the shipped games.
Study the recordings closely; every convention that matters is recoverable from them.
The machine is offline and only the Node standard library is available.
