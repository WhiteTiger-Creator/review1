# `server_list.json`

The listing the browse servers screen would have been showing at the moment the
journal window closed, as a JSON array, one object per game server.

## Configuration

The config file passed on the command line holds:

| Key | Meaning |
|---|---|
| `server_entry_timeout_secs` | how long a registration survives without a heartbeat |
| `official_hosts` | host names of the servers the project runs itself |
| `external_arena_files_provider` | base URL of the published arena catalogue |
| `banlist_servers_path` | path to the ban list the master server enforces |

A host counts as official when the address a datagram came from is one of the
addresses that host currently resolves to. When more than one configured host
matches, the earliest one in `official_hosts` wins. The arena catalogue is the
index the game itself asks that provider for.

## Rebuilding the registry

* A registration is keyed by the full source address, address and port together.
* A registration expires once `server_entry_timeout_secs` have passed since its
  last accepted heartbeat. Expiry is evaluated at every arrival time in the
  journal, before the records bearing that time are handled, and once more at
  the window end.
* Ban lists, heartbeat validity, request kinds, and payloads that cannot be
  decoded are all handled the way the master server handles them. The game
  sources under `/app/hypersomnia/src` are the contract.
* The array holds the registrations still alive at the window end whose last
  accepted heartbeat asked to appear on the server list, sorted ascending by the
  four address octets and then by port.

## Entry schema

Every entry is a JSON object. These keys are always present:

| Key | Type | Value |
|---|---|---|
| `name` | string | server name from the heartbeat |
| `ip` | string | `address:port` the heartbeat came from |
| `official_url` | string | `host:port` when the server is official, else `""` |
| `webrtc_id` | string | signalling alias the master server assigns to an official server, `""` for anyone else |
| `browser_connect_string` | string | the alias when it is not empty, otherwise `ip` |
| `site_displayed_address` | string | `official_url` when it is not empty, otherwise `ip` |
| `server_version` | string | version string from the heartbeat |
| `is_official` | bool | whether `official_url` is not empty |
| `is_ranked` | bool | official, and the heartbeat reports a ranked state |
| `nat` | string | NAT type, spelled the way the game spells it |
| `arena` | string | arena the heartbeat advertises |
| `arena_in_catalogue` | bool | that arena is published in the catalogue |
| `arena_author` | string | author the catalogue lists for it, `""` when not published |
| `game_mode` | string | game mode from the heartbeat |
| `time_hosted` | number | arrival time of the heartbeat that opened the current registration |
| `time_last_heartbeat` | number | arrival time of the last accepted heartbeat |
| `heartbeats_accepted` | number | heartbeats accepted for the current registration |
| `slots` | number | player slots the heartbeat reports |
| `num_online_humans` | number | humans online |
| `num_playing` | number | everyone online who is not spectating |
| `num_spectating` | number | length of the spectator list |
| `score_resistance` | number | Resistance score |
| `score_metropolis` | number | Metropolis score |
| `players_resistance` | array | Resistance players, in heartbeat order |
| `players_metropolis` | array | Metropolis players, in heartbeat order |
| `players_spectating` | array | spectators, in heartbeat order |

Each player is an object with `nickname` (string), `score` (number) and
`deaths` (number).

Two keys are conditional and must be left out entirely when they do not apply:

| Key | Type | Present when |
|---|---|---|
| `internal_network_address` | string | the heartbeat carries one, formatted `address:port` |
| `is_editor_playtesting_server` | bool | the heartbeat sets it, in which case the value is `true` |
