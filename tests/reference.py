"""Independent reference implementation of the master server list rebuild.

This module is mounted only at verification time. It re-derives every value the
graded tool is expected to produce, straight from the same Hypersomnia sources
the agent reads, and it also generates fresh journals so that grading is not
limited to the journal shipped inside the image.
"""

from __future__ import annotations

import json
import random
import socket
import struct
import urllib.request

JOURNAL_MAGIC = b"HMSJRNL1"
SNAPSHOT_MAGIC = b"HYPRSNAP"
SNAPSHOT_VERSION = 1

MAX_SERVER_NAME = 60
MAX_ARENA_NAME = 30
MAX_GAME_MODE_NAME = 30
MAX_VERSION = 20
MAX_NICKNAME = 40

PLAYER_INFO_SIZE = 52
NETCODE_ADDRESS_SIZE = 20
NETCODE_ADDRESS_IPV4 = 1

REQ_HEARTBEAT = 0
REQ_TELL_ME_MY_ADDRESS = 1
REQ_GOODBYE = 2
REQ_DUMMY_INT = 3
REQ_DUMMY_FLOAT = 4
REQ_WEBRTC = 5

NAT_NAMES = [
    "PUBLIC_INTERNET",
    "PORT_PRESERVING_CONE",
    "CONE",
    "ADDRESS_SENSITIVE",
    "PORT_SENSITIVE",
    "UNKNOWN",
]

LOCATION_PREFIXES = [
    ("[AU]", "au"),
    ("[NL]", "nl"),
    ("[PL]", "pl"),
    ("[US]", "us-central"),
    ("[RU]", "ru"),
    ("[DE]", "de"),
    ("[CH]", "ch"),
    ("[FI]", "fi"),
]


class WireError(Exception):
    """Raised when a request payload cannot be decoded."""


class JournalError(Exception):
    """Raised when a journal file is not well formed."""


# ---------------------------------------------------------------------------
# augs byte serialization, as implemented in augs/readwrite/byte_readwrite.h
# ---------------------------------------------------------------------------


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def take(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.data):
            raise WireError("read past the end of the stream")
        out = self.data[self.pos:self.pos + n]
        self.pos += n
        return out

    def u8(self) -> int:
        return self.take(1)[0]

    def boolean(self) -> bool:
        return self.take(1)[0] != 0

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def i64(self) -> int:
        return struct.unpack("<q", self.take(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.take(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.take(8))[0]

    def csstring(self, capacity: int) -> str:
        length = self.u32()
        if length > capacity:
            raise WireError("string longer than its constant capacity")
        return self.take(length).decode("utf-8", errors="surrogateescape")


def encode_csstring(value: str, capacity: int) -> bytes:
    raw = value.encode("utf-8")
    if len(raw) > capacity:
        raise ValueError("string longer than its constant capacity")
    return struct.pack("<I", len(raw)) + raw


def encode_address(ip: str, port: int) -> bytes:
    """netcode_address_t is trivially copyable, so augs writes it raw."""
    out = bytearray(NETCODE_ADDRESS_SIZE)
    out[0:4] = socket.inet_aton(ip)
    struct.pack_into("<H", out, 16, port)
    out[18] = NETCODE_ADDRESS_IPV4
    return bytes(out)


def decode_address(raw: bytes) -> tuple[str, int]:
    if len(raw) != NETCODE_ADDRESS_SIZE:
        raise WireError("bad address size")
    port = struct.unpack_from("<H", raw, 16)[0]
    kind = raw[18]
    if kind != NETCODE_ADDRESS_IPV4:
        raise WireError("only IPv4 addresses are supported")
    return socket.inet_ntoa(raw[0:4]), port


def encode_player(nickname: str, score: int, deaths: int) -> bytes:
    """server_heartbeat_player_info is written as a raw 52 byte struct."""
    raw = nickname.encode("utf-8")
    if len(raw) > MAX_NICKNAME:
        raise ValueError("nickname too long")
    out = bytearray(PLAYER_INFO_SIZE)
    struct.pack_into("<I", out, 0, len(raw))
    out[4:4 + len(raw)] = raw
    out[48] = score
    out[49] = deaths
    return bytes(out)


def decode_player(raw: bytes) -> dict:
    length = struct.unpack_from("<I", raw, 0)[0]
    if length > MAX_NICKNAME:
        raise WireError("nickname longer than its constant capacity")
    nickname = raw[4:4 + length].decode("utf-8", errors="surrogateescape")
    return {"nickname": nickname, "score": raw[48], "deaths": raw[49]}


class Heartbeat:
    """The GEN INTROSPECTOR block of server_heartbeat, in declaration order."""

    def __init__(self, **kwargs: object) -> None:
        self.server_name = ""
        self.current_arena = ""
        self.game_mode = ""
        self.num_online_humans = 0
        self.num_online = 0
        self.server_slots = 0
        self.internal_network_address: tuple[str, int] | None = None
        self.nat_type = 0
        self.nat_port_delta = 0
        self.predicted_next_port = 0
        self.suppress_new_community_server_webhook = False
        self.show_on_server_list = True
        self.server_version = "Unknown"
        self.is_editor_playtesting_server = False
        self.score_resistance = 0
        self.score_metropolis = 0
        self.players_resistance: list[dict] = []
        self.players_metropolis: list[dict] = []
        self.players_spectating: list[dict] = []
        self.require_authentication = False
        self.ranked_state = 0
        self.require_password = False
        for key, value in kwargs.items():
            if not hasattr(self, key):
                raise AttributeError(key)
            setattr(self, key, value)

    # -- rules taken straight out of the game sources -----------------------

    def is_valid(self) -> bool:
        name = self.server_name
        if len(name) == name.count(" "):
            return False
        for char in name:
            if char == "\0":
                return False
            if char in "\t\n\v\f\r":
                return False
        return bool(name) and bool(self.current_arena) and bool(self.game_mode)

    def num_online_bots(self) -> int:
        return self.num_online - self.num_online_humans

    def max_online(self) -> int:
        return self.server_slots + self.num_online_bots()

    def is_full(self) -> bool:
        return self.num_online == self.max_online()

    def is_ranked_server(self) -> bool:
        return self.ranked_state != 0

    def location_id(self) -> str:
        for prefix, location in LOCATION_PREFIXES:
            if self.server_name.startswith(prefix):
                return location
        return ""

    def encode(self) -> bytes:
        out = bytearray()
        out += encode_csstring(self.server_name, MAX_SERVER_NAME)
        out += encode_csstring(self.current_arena, MAX_ARENA_NAME)
        out += encode_csstring(self.game_mode, MAX_GAME_MODE_NAME)
        out += bytes([self.num_online_humans, self.num_online, self.server_slots])
        if self.internal_network_address is None:
            out += b"\x00"
        else:
            out += b"\x01"
            out += encode_address(*self.internal_network_address)
        out += bytes([self.nat_type])
        out += struct.pack("<i", self.nat_port_delta)
        out += struct.pack("<H", self.predicted_next_port)
        out += bytes([1 if self.suppress_new_community_server_webhook else 0])
        out += bytes([1 if self.show_on_server_list else 0])
        out += encode_csstring(self.server_version, MAX_VERSION)
        out += bytes([1 if self.is_editor_playtesting_server else 0])
        out += bytes([self.score_resistance, self.score_metropolis])
        for team in (self.players_resistance, self.players_metropolis, self.players_spectating):
            out += struct.pack("<I", len(team))
            for player in team:
                out += encode_player(player["nickname"], player["score"], player["deaths"])
        out += bytes([1 if self.require_authentication else 0])
        out += bytes([self.ranked_state])
        out += bytes([1 if self.require_password else 0])
        return bytes(out)

    @staticmethod
    def decode(reader: Reader) -> Heartbeat:
        beat = Heartbeat()
        beat.server_name = reader.csstring(MAX_SERVER_NAME)
        beat.current_arena = reader.csstring(MAX_ARENA_NAME)
        beat.game_mode = reader.csstring(MAX_GAME_MODE_NAME)
        beat.num_online_humans = reader.u8()
        beat.num_online = reader.u8()
        beat.server_slots = reader.u8()
        if reader.boolean():
            beat.internal_network_address = decode_address(reader.take(NETCODE_ADDRESS_SIZE))
        beat.nat_type = reader.u8()
        beat.nat_port_delta = reader.i32()
        beat.predicted_next_port = reader.u16()
        beat.suppress_new_community_server_webhook = reader.boolean()
        beat.show_on_server_list = reader.boolean()
        beat.server_version = reader.csstring(MAX_VERSION)
        beat.is_editor_playtesting_server = reader.boolean()
        beat.score_resistance = reader.u8()
        beat.score_metropolis = reader.u8()
        teams = []
        for _ in range(3):
            count = reader.u32()
            if count > 32:
                raise WireError("more players than the constant capacity")
            teams.append([decode_player(reader.take(PLAYER_INFO_SIZE)) for _ in range(count)])
        beat.players_resistance, beat.players_metropolis, beat.players_spectating = teams
        beat.require_authentication = reader.boolean()
        beat.ranked_state = reader.u8()
        beat.require_password = reader.boolean()
        return beat


def encode_request(kind: int, payload: object = None) -> bytes:
    if kind == REQ_HEARTBEAT:
        assert isinstance(payload, Heartbeat)
        return bytes([kind]) + payload.encode()
    if kind == REQ_TELL_ME_MY_ADDRESS:
        return bytes([kind]) + struct.pack("<d", float(payload or 0.0))
    if kind == REQ_GOODBYE:
        # An empty struct is trivially copyable, so augs writes one raw byte.
        return bytes([kind, 0])
    if kind == REQ_DUMMY_INT:
        return bytes([kind]) + struct.pack("<i", int(payload or 0))
    if kind == REQ_DUMMY_FLOAT:
        return bytes([kind]) + struct.pack("<f", float(payload or 0.0))
    if kind == REQ_WEBRTC:
        guid, message = payload  # type: ignore[misc]
        return bytes([kind]) + struct.pack("<q", guid) + encode_csstring(message, 4096)
    raise ValueError("unknown request kind")


def decode_request(payload: bytes) -> tuple[int, object]:
    reader = Reader(payload)
    kind = reader.u8()
    if kind == REQ_HEARTBEAT:
        return kind, Heartbeat.decode(reader)
    if kind == REQ_TELL_ME_MY_ADDRESS:
        return kind, reader.f64()
    if kind == REQ_GOODBYE:
        reader.take(1)
        return kind, None
    if kind == REQ_DUMMY_INT:
        return kind, reader.i32()
    if kind == REQ_DUMMY_FLOAT:
        return kind, reader.f32()
    if kind == REQ_WEBRTC:
        guid = reader.i64()
        return kind, (guid, reader.csstring(4096))
    raise WireError("unknown request kind")


# ---------------------------------------------------------------------------
# the journal container
# ---------------------------------------------------------------------------


class Record:
    def __init__(self, arrived_at: float, ip: str, port: int, payload: bytes) -> None:
        self.arrived_at = arrived_at
        self.ip = ip
        self.port = port
        self.payload = payload


def write_journal(path: str, started_at: float, ended_at: float, records: list[Record]) -> None:
    out = bytearray(JOURNAL_MAGIC)
    out += struct.pack("<I", len(records))
    out += struct.pack("<dd", started_at, ended_at)
    for record in records:
        out += struct.pack("<d", record.arrived_at)
        out += bytes([4])
        out += socket.inet_aton(record.ip)
        out += struct.pack("<HH", record.port, len(record.payload))
        out += record.payload
    with open(path, "wb") as handle:
        handle.write(bytes(out))


def read_journal(path: str) -> tuple[float, float, list[Record]]:
    with open(path, "rb") as handle:
        blob = handle.read()
    if len(blob) < 28 or blob[0:8] != JOURNAL_MAGIC:
        raise JournalError("bad magic")
    count = struct.unpack_from("<I", blob, 8)[0]
    started_at, ended_at = struct.unpack_from("<dd", blob, 12)
    if ended_at < started_at:
        raise JournalError("window ends before it starts")
    pos = 28
    records = []
    previous = started_at
    for _ in range(count):
        if pos + 17 > len(blob):
            raise JournalError("truncated record")
        arrived_at = struct.unpack_from("<d", blob, pos)[0]
        if blob[pos + 8] != 4:
            raise JournalError("only IPv4 records are supported")
        ip = socket.inet_ntoa(blob[pos + 9:pos + 13])
        port, length = struct.unpack_from("<HH", blob, pos + 13)
        pos += 17
        if pos + length > len(blob):
            raise JournalError("truncated payload")
        payload = blob[pos:pos + length]
        pos += length
        if arrived_at < previous or arrived_at > ended_at:
            raise JournalError("timestamps out of order")
        previous = arrived_at
        records.append(Record(arrived_at, ip, port, payload))
    if pos != len(blob):
        raise JournalError("trailing bytes")
    return started_at, ended_at, records


# ---------------------------------------------------------------------------
# external facts: DNS and the published arena catalogue
# ---------------------------------------------------------------------------


def resolve_official_hosts(hosts: list[str]) -> list[tuple[str, set[str]]]:
    resolved = []
    for host in hosts:
        addresses = set()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            addresses.add(info[4][0])
        resolved.append((host, addresses))
    return resolved


def fetch_catalogue(provider_url: str) -> dict[str, str]:
    with urllib.request.urlopen(provider_url + "?format=json", timeout=60) as response:
        entries = json.loads(response.read().decode("utf-8"))
    return {entry["name"]: entry.get("author", "") for entry in entries}


# ---------------------------------------------------------------------------
# the replay itself
# ---------------------------------------------------------------------------


class Entry:
    def __init__(self, time_hosted: float, beat: Heartbeat) -> None:
        self.time_hosted = time_hosted
        self.time_last_heartbeat = time_hosted
        self.beat = beat
        self.heartbeats = 1


def load_banlist(path: str) -> tuple[set[str], set[str]]:
    addresses: set[str] = set()
    names: set[str] = set()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return addresses, names
    for line in content.split("\n"):
        if not line:
            continue
        space = line.find(" ")
        if space == -1:
            addresses.add(line)
        else:
            addresses.add(line[:space])
            names.add(line[space + 1:].lower())
    return addresses, names


def replay(records: list[Record], ended_at: float, timeout: float,
           banned_addresses: set[str], banned_names: set[str]) -> dict[tuple[str, int], Entry]:
    registry: dict[tuple[str, int], Entry] = {}

    def evict(now: float) -> None:
        for key in [k for k, e in registry.items() if now - e.time_last_heartbeat >= timeout]:
            del registry[key]

    for record in records:
        evict(record.arrived_at)
        if record.ip in banned_addresses:
            continue
        key = (record.ip, record.port)
        try:
            kind, payload = decode_request(record.payload)
        except WireError:
            registry.pop(key, None)
            continue
        if kind == REQ_GOODBYE:
            registry.pop(key, None)
        elif kind == REQ_HEARTBEAT:
            beat = payload
            assert isinstance(beat, Heartbeat)
            if beat.server_name.lower() in banned_names:
                continue
            if not beat.is_valid():
                continue
            existing = registry.get(key)
            if existing is None:
                registry[key] = Entry(record.arrived_at, beat)
            else:
                existing.beat = beat
                existing.time_last_heartbeat = record.arrived_at
                existing.heartbeats += 1
    evict(ended_at)
    return registry


# ---------------------------------------------------------------------------
# output rendering
# ---------------------------------------------------------------------------


def webrtc_alias(beat: Heartbeat) -> str:
    location = beat.location_id()
    if location == "us-central":
        location = "us"
    if beat.is_ranked_server():
        location = "ranked-" + location
    name = beat.server_name
    hash_at = name.find("#")
    if hash_at != -1:
        tail = name[hash_at + 1:]
        index = _leading_int(tail)
        if index is not None:
            location += ":" + str(index)
    return location


def _leading_int(text: str) -> int | None:
    stripped = text.lstrip()
    pos = 0
    if pos < len(stripped) and stripped[pos] in "+-":
        pos += 1
    digits = pos
    while digits < len(stripped) and stripped[digits].isdigit():
        digits += 1
    if digits == pos:
        return None
    return int(stripped[:digits])


def build_rows(registry: dict[tuple[str, int], Entry],
               official: list[tuple[str, set[str]]],
               catalogue: dict[str, str]) -> list[dict]:
    rows = []
    for (ip, port), entry in registry.items():
        beat = entry.beat
        if not beat.show_on_server_list:
            continue
        official_url = ""
        for host, addresses in official:
            if ip in addresses:
                official_url = f"{host}:{port}"
                break
        is_official = official_url != ""
        ip_string = f"{ip}:{port}"
        webrtc_id = webrtc_alias(beat) if is_official else ""
        spectating = len(beat.players_spectating)
        row = {
            "name": beat.server_name,
            "ip": ip_string,
            "official_url": official_url,
            "webrtc_id": webrtc_id,
            "browser_connect_string": webrtc_id if webrtc_id else ip_string,
            "site_displayed_address": official_url if is_official else ip_string,
            "server_version": beat.server_version,
            "is_official": is_official,
            "is_ranked": is_official and beat.is_ranked_server(),
            "nat": NAT_NAMES[beat.nat_type] if beat.nat_type < len(NAT_NAMES) else "UNKNOWN",
            "arena": beat.current_arena,
            "arena_in_catalogue": beat.current_arena in catalogue,
            "arena_author": catalogue.get(beat.current_arena, ""),
            "game_mode": beat.game_mode,
            "time_hosted": entry.time_hosted,
            "time_last_heartbeat": entry.time_last_heartbeat,
            "heartbeats_accepted": entry.heartbeats,
            "slots": beat.server_slots,
            "num_online_humans": beat.num_online_humans,
            "num_playing": beat.num_online - spectating,
            "num_spectating": spectating,
            "score_resistance": beat.score_resistance,
            "score_metropolis": beat.score_metropolis,
            "players_resistance": beat.players_resistance,
            "players_metropolis": beat.players_metropolis,
            "players_spectating": beat.players_spectating,
        }
        if beat.internal_network_address is not None:
            row["internal_network_address"] = "{}:{}".format(*beat.internal_network_address)
        if beat.is_editor_playtesting_server:
            row["is_editor_playtesting_server"] = True
        row["_key"] = (socket.inet_aton(ip), port)
        row["_beat"] = beat
        rows.append(row)
    rows.sort(key=lambda r: r["_key"])
    return rows


def render_json(rows: list[dict]) -> str:
    public = []
    for row in rows:
        clean = {k: v for k, v in row.items() if not k.startswith("_")}
        public.append(clean)
    return json.dumps(public, indent=2)


def uvarint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative uvarint")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def svarint(value: int) -> bytes:
    return uvarint((value << 1) ^ (value >> 31))


def round_half_away(value: float) -> int:
    if value < 0:
        return -int(-value + 0.5)
    return int(value + 0.5)


CRC_TABLE = []
for _index in range(256):
    _acc = _index
    for _ in range(8):
        _acc = (_acc >> 1) ^ (0xEDB88320 if _acc & 1 else 0)
    CRC_TABLE.append(_acc)


def crc32(data: bytes) -> int:
    acc = 0xFFFFFFFF
    for byte in data:
        acc = CRC_TABLE[(acc ^ byte) & 0xFF] ^ (acc >> 8)
    return acc ^ 0xFFFFFFFF


def render_snapshot(rows: list[dict], window_start: float, window_end: float) -> bytes:
    table: list[str] = []
    index_of: dict[str, int] = {}

    def intern(text: str) -> int:
        if text not in index_of:
            index_of[text] = len(table)
            table.append(text)
        return index_of[text]

    body = bytearray()
    for row in rows:
        beat: Heartbeat = row["_beat"]
        name_idx = intern(row["name"])
        arena_idx = intern(row["arena"])
        mode_idx = intern(row["game_mode"])
        version_idx = intern(row["server_version"])
        official_indices = None
        if row["is_official"]:
            official_indices = (intern(row["official_url"]), intern(row["webrtc_id"]))
        nick_indices = []
        for team in ("players_resistance", "players_metropolis", "players_spectating"):
            nick_indices.append([intern(p["nickname"]) for p in row[team]])

        flags = 0
        if row["is_official"]:
            flags |= 0x01
        if row["is_ranked"]:
            flags |= 0x02
        if beat.internal_network_address is not None:
            flags |= 0x04
        if beat.is_editor_playtesting_server:
            flags |= 0x08
        if row["arena_in_catalogue"]:
            flags |= 0x10
        if beat.is_full():
            flags |= 0x20

        ip, port = row["_key"]
        body += ip
        body += struct.pack(">H", port)
        body += bytes([flags, beat.nat_type])
        body += svarint(beat.nat_port_delta)
        body += struct.pack(">H", beat.predicted_next_port)
        body += uvarint(name_idx) + uvarint(arena_idx)
        body += uvarint(mode_idx) + uvarint(version_idx)
        if official_indices is not None:
            body += uvarint(official_indices[0]) + uvarint(official_indices[1])
        if beat.internal_network_address is not None:
            internal_ip, internal_port = beat.internal_network_address
            body += socket.inet_aton(internal_ip)
            body += struct.pack(">H", internal_port)
        body += uvarint(round_half_away((window_end - row["time_hosted"]) * 1000.0))
        body += uvarint(round_half_away((window_end - row["time_last_heartbeat"]) * 1000.0))
        body += uvarint(row["heartbeats_accepted"])
        body += bytes([
            row["slots"],
            row["num_online_humans"],
            row["num_playing"],
            row["num_spectating"],
            row["score_resistance"],
            row["score_metropolis"],
        ])
        for team, indices in zip(
            ("players_resistance", "players_metropolis", "players_spectating"), nick_indices
        ):
            players = row[team]
            body += uvarint(len(players))
            for player, nick_idx in zip(players, indices):
                body += uvarint(nick_idx)
                body += bytes([player["score"], player["deaths"]])

    head = bytearray(SNAPSHOT_MAGIC)
    head += bytes([SNAPSHOT_VERSION])
    head += struct.pack(">H", len(rows))
    head += struct.pack(">dd", window_start, window_end)
    head += struct.pack(">H", len(table))
    for text in table:
        raw = text.encode("utf-8")
        head += uvarint(len(raw)) + raw

    blob = bytes(head) + bytes(body)
    digest = crc32(blob[len(SNAPSHOT_MAGIC):])
    return blob + struct.pack(">I", digest)


def expected_outputs(journal_path: str, config: dict, banlist_path: str,
                     official: list[tuple[str, set[str]]],
                     catalogue: dict[str, str]) -> tuple[list[dict], str, bytes]:
    started_at, ended_at, records = read_journal(journal_path)
    banned_addresses, banned_names = load_banlist(banlist_path)
    registry = replay(
        records,
        ended_at,
        float(config["server_entry_timeout_secs"]),
        banned_addresses,
        banned_names,
    )
    rows = build_rows(registry, official, catalogue)
    return rows, render_json(rows), render_snapshot(rows, started_at, ended_at)


# ---------------------------------------------------------------------------
# journal generation, used for fixtures the agent has never seen
# ---------------------------------------------------------------------------


def quantize(seconds: float) -> float:
    """Keep every timestamp on a 1/16 second grid so all arithmetic is exact."""
    return round(seconds * 16.0) / 16.0




NICKNAMES = [
    "wisp", "cheeser", "brainless", "vodka", "chairn", "peachybun", "nameless",
    "ghost", "snorkel", "billan", "kobra", "silo", "aquarium", "pigeon",
]
MODES = ["Bomb Defusal", "Gun Game", "Free for All", "Duel of Honor"]
VERSIONS = ["2.3.0-pre1", "2.2.4", "2.1.9", "1.9.3"]
LOCATION_TAGS = ["[US] ", "[DE] ", "[AU] ", "[FI] ", "[NL] ", "[PL] ", "[RU] ", "[CH] "]


def _players(rng: random.Random, count: int) -> list[dict]:
    return [
        {
            "nickname": rng.choice(NICKNAMES) + str(rng.randrange(100)),
            "score": rng.randrange(40),
            "deaths": rng.randrange(40),
        }
        for _ in range(count)
    ]


def make_heartbeat(rng: random.Random, name: str, arena: str, **overrides: object) -> Heartbeat:
    resistance = _players(rng, rng.randrange(0, 5))
    metropolis = _players(rng, rng.randrange(0, 5))
    spectating = _players(rng, rng.randrange(0, 3))
    humans = len(resistance) + len(metropolis) + len(spectating)
    bots = rng.randrange(0, 4)
    beat = Heartbeat(
        server_name=name,
        current_arena=arena,
        game_mode=rng.choice(MODES),
        num_online_humans=humans,
        num_online=humans + bots,
        server_slots=rng.choice([humans, humans + 2, 16]),
        nat_type=rng.randrange(0, 5),
        nat_port_delta=rng.randrange(-40000, 40000),
        predicted_next_port=rng.randrange(0, 65535),
        server_version=rng.choice(VERSIONS),
        score_resistance=rng.randrange(0, 16),
        score_metropolis=rng.randrange(0, 16),
        players_resistance=resistance,
        players_metropolis=metropolis,
        players_spectating=spectating,
        ranked_state=rng.choice([0, 0, 1, 2]),
        require_password=rng.random() < 0.3,
        require_authentication=rng.random() < 0.3,
        suppress_new_community_server_webhook=rng.random() < 0.2,
        is_editor_playtesting_server=rng.random() < 0.15,
    )
    if rng.random() < 0.5:
        beat.internal_network_address = (
            f"172.17.0.{rng.randrange(2, 200)}",
            rng.randrange(1024, 65535),
        )
    for key, value in overrides.items():
        setattr(beat, key, value)
    return beat


def generate_journal(seed: int, official_ips: list[str], catalogue_arenas: list[str],
                     foreign_arenas: list[str]) -> tuple[float, float, list[Record], list[str]]:
    """Build a journal that exercises every branch of the replay."""
    rng = random.Random(seed)
    start = 1700000000.0 + seed * 3600.0
    end = start + 900.0
    timeout = 65.0
    records: list[Record] = []
    ban_lines: list[str] = []
    arenas = list(catalogue_arenas) + list(foreign_arenas)

    def emit(when: float, ip: str, port: int, payload: bytes) -> None:
        records.append(Record(quantize(when), ip, port, payload))

    def series(ip: str, port: int, name: str, arena: str, first: float, last: float,
               interval: float, **overrides: object) -> float:
        when = first
        latest = first
        while when <= last:
            emit(when, ip, port, encode_request(
                REQ_HEARTBEAT, make_heartbeat(rng, name, arena, **overrides)))
            latest = when
            when = quantize(when + interval)
        return latest

    # The official fleet, one server per resolved host. Half of them advertise a
    # location tag and an instance index, which is what the alias is built from.
    for index, ip in enumerate(official_ips):
        tag = LOCATION_TAGS[index % len(LOCATION_TAGS)] if index % 3 != 2 else ""
        name = tag + "Hypersomnia Arena"
        if index % 2 == 0:
            name += f"#{index + 1}"
        series(ip, 8412 + (index % 3), name, arenas[index % len(arenas)],
               start + 2.0 + index, end - 12.0, 18.0 + index + 0.0625,
               ranked_state=[0, 1, 2, 0, 1, 3, 0, 2][index % 8])

    # Community servers that stay up for the whole window.
    community = [
        ("185.21.41.61", 8412, "Warsaw Practice Room"),
        ("193.70.94.7", 8412, "[PL] Nocna Zmiana"),
        ("51.75.130.44", 8420, "de_bunker 24/7"),
    ]
    for index, (ip, port, name) in enumerate(community):
        arena = foreign_arenas[index] if index < len(foreign_arenas) else arenas[index]
        series(ip, port, name, arena, start + 4.0 + index, end - 14.0, 21.0 + index)

    # Hidden server: its last heartbeat asks to be kept off the list.
    hidden_ip = "91.121.10.4"
    last_hidden = series(hidden_ip, 8412, "Private Scrim", arenas[0],
                         start + 6.0, end - 120.0, 20.0)
    emit(last_hidden + 20.0, hidden_ip, 8412, encode_request(
        REQ_HEARTBEAT, make_heartbeat(rng, "Private Scrim", arenas[0], show_on_server_list=False)))

    # Says goodbye near the end.
    quitter_ip = "91.121.10.5"
    series(quitter_ip, 8412, "Leaving Soon", arenas[1 % len(arenas)],
           start + 8.0, end - 40.0, 20.0)
    emit(end - 30.0, quitter_ip, 8412, encode_request(REQ_GOODBYE))

    # Sends a truncated packet near the end.
    corrupt_ip = "91.121.10.6"
    series(corrupt_ip, 8412, "Flaky Uplink", arenas[2 % len(arenas)],
           start + 10.0, end - 40.0, 20.0)
    emit(end - 26.0, corrupt_ip, 8412,
         encode_request(REQ_HEARTBEAT, make_heartbeat(rng, "Flaky Uplink", arenas[0]))[:11])

    # Requests that must never touch the registry, from an address that also
    # runs a listed server on another port.
    noise_ip = "91.121.10.7"
    series(noise_ip, 8412, "Noisy Neighbour", arenas[3 % len(arenas)],
           start + 12.0, end - 16.0, 22.0)
    emit(start + 40.0, noise_ip, 8430, encode_request(REQ_TELL_ME_MY_ADDRESS, start + 40.0))
    emit(start + 41.0, noise_ip, 8431, encode_request(REQ_WEBRTC, (91125, "offer-blob")))
    emit(start + 42.0, noise_ip, 8432, encode_request(REQ_DUMMY_INT, 5))
    emit(start + 43.0, noise_ip, 8433, encode_request(REQ_DUMMY_FLOAT, 1.5))
    emit(start + 44.0, noise_ip, 8412, encode_request(REQ_TELL_ME_MY_ADDRESS, start + 44.0))

    # A heartbeat carrying whitespace the game rejects: the registration must
    # keep the values it already had.
    wobbly_ip = "91.121.10.8"
    series(wobbly_ip, 8412, "Steady Values", arenas[4 % len(arenas)],
           start + 14.0, end - 40.0, 20.0)
    emit(end - 22.0, wobbly_ip, 8412, encode_request(
        REQ_HEARTBEAT, make_heartbeat(rng, "Steady\tValues", arenas[0])))
    emit(end - 21.0, wobbly_ip, 8412, encode_request(
        REQ_HEARTBEAT, make_heartbeat(rng, "   ", arenas[0])))
    emit(end - 20.0, wobbly_ip, 8412, encode_request(
        REQ_HEARTBEAT, make_heartbeat(rng, "Steady Values", "")))

    # Banned by address: nothing it sends may be looked at.
    banned_ip = "91.121.10.9"
    ban_lines.append(banned_ip)
    series(banned_ip, 8412, "Griefer Central", arenas[0], start + 16.0, start + 300.0, 20.0)
    emit(start + 310.0, banned_ip, 8412, encode_request(REQ_GOODBYE))
    series(banned_ip, 8412, "Griefer Central", arenas[0], start + 320.0, end - 16.0, 20.0)

    # Banned by name: the rename must be ignored, the registration must stay.
    rename_ip = "91.121.10.10"
    ban_lines.append("203.0.113.9 Rude Name")
    series(rename_ip, 8412, "Polite Name", arenas[5 % len(arenas)],
           start + 18.0, end - 40.0, 20.0)
    emit(end - 24.0, rename_ip, 8412, encode_request(
        REQ_HEARTBEAT, make_heartbeat(rng, "rude NAME", arenas[0])))

    # Goes quiet for longer than the timeout and comes back.
    flapping_ip = "91.121.10.11"
    series(flapping_ip, 8412, "Flapping Uplink", arenas[6 % len(arenas)],
           start + 20.0, start + 120.0, 20.0)
    series(flapping_ip, 8412, "Flapping Uplink", arenas[6 % len(arenas)],
           start + 400.0, end - 18.0, 20.0)

    # Its next heartbeat lands exactly on the timeout boundary.
    boundary_ip = "91.121.10.12"
    emit(start + 200.0, boundary_ip, 8412, encode_request(
        REQ_HEARTBEAT, make_heartbeat(rng, "Boundary Case", arenas[7 % len(arenas)])))
    series(boundary_ip, 8412, "Boundary Case", arenas[7 % len(arenas)],
           start + 200.0 + timeout, end - 20.0, 20.0)

    # Falls silent early and must be gone by the end of the window.
    stale_ip = "91.121.10.13"
    series(stale_ip, 8412, "Abandoned Host", arenas[0], start + 22.0, start + 150.0, 20.0)

    # The same address on two ports is two independent registrations.
    twin_ip = "91.121.10.14"
    for port in (8412, 8413):
        series(twin_ip, port, f"Twin {port}", arenas[(port + 1) % len(arenas)],
               start + 24.0, end - 20.0, 20.0)

    records.sort(key=lambda r: r.arrived_at)
    return start, end, records, ban_lines
