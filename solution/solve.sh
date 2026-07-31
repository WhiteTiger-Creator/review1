#!/bin/bash
set -euo pipefail

# Resolve the directory this script was mounted into rather than assuming one,
# so the sources next to it are found wherever the harness puts them.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Build the rebuilder.
#
# Two facts the listing needs cannot come out of the image. Which addresses the
# official hosts answer on is a DNS answer that changes whenever the project
# moves a machine, and which arenas are published is whatever the catalogue is
# serving right now, so both are looked up while the tool runs.
#
# A third one is missing from the checkout rather than merely stale: the yojimbo
# submodule under src/3rdparty is not vendored here, so netcode_address_t, which
# the heartbeat carries whole, has to be read from the published repository.

g++ -std=c++17 -O2 -o /app/mslist "$SCRIPT_DIR/MsList.cpp"

# 2. Show the layout the tool was written against, straight from the header the
#    checkout is missing. The union comes first, then the port, then the type,
#    which is twenty bytes once the trailing padding is counted. This step is
#    illustrative, so a hiccup reaching the repository must not fail the build.

if curl -fsS --max-time 60 \
    https://raw.githubusercontent.com/TeamHypersomnia/yojimbo/master/netcode/netcode.h \
    -o /app/netcode.h
then
    sed -n '/struct netcode_address_t/,/};/p' /app/netcode.h
else
    echo "could not fetch netcode.h for display; the layout it documents is already in the tool"
fi

# 3. Rebuild the listing the master server was serving when the journal closed.

/app/mslist /app/journal/session14.cap /app/msconfig.json /app/out

echo "entries rebuilt:"
grep -c '"ip"' /app/out/server_list.json
echo "snapshot bytes:"
wc -c < /app/out/snapshot.bin
