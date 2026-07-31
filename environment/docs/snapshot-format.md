# `snapshot.bin`

A packed copy of the same list, small enough to keep one per window so that two
snapshots can be diffed byte for byte. It is checked byte for byte, so every
rule below matters.

## Number encodings

* Fixed width integers are **big endian**.
* `uvarint` is unsigned LEB128: seven bits per byte, low group first, the top
  bit set on every byte but the last.
* `svarint` is the same encoding applied to the zig-zag folding of a signed
  32 bit value, that is `(n << 1) ^ (n >> 31)` in two's complement.
* Millisecond counts are the plain difference of the two `float64` seconds
  multiplied by 1000, rounded to the nearest whole millisecond, with an exact
  half rounded away from zero.

## Layout

```
magic          8 bytes, the ASCII bytes HYPRSNAP
version        uint8, currently 1
entry_count    uint16
window_start   float64
window_end     float64
string_count   uint16
strings        string_count entries, each a uvarint byte length followed by the UTF-8 bytes
entries        entry_count records
digest         uint32
```

`window_start` and `window_end` are the journal window, copied over unchanged.
Entries appear in the same order as in `server_list.json`.

## The string table

Strings are interned: the table holds each distinct string once, in the order
the strings are first needed, and entries refer to them by index. Walk the
entries in output order and, for each entry, take the strings in this order:

1. `name`
2. `arena`
3. `game_mode`
4. `server_version`
5. `official_url`, then `webrtc_id`, **only** when the entry is official
6. the nicknames of the Resistance players, then the Metropolis players, then
   the spectators, each in heartbeat order

An empty string is interned like any other.

## An entry

| Size | Field |
|---|---|
| 4 | source address, one byte per octet |
| 2 | `uint16` source port |
| 1 | flags, see below |
| 1 | `uint8` NAT type, as the numeric value the game gives it |
| var | `svarint` NAT port delta |
| 2 | `uint16` predicted next port |
| var | `uvarint` string index of `name` |
| var | `uvarint` string index of `arena` |
| var | `uvarint` string index of `game_mode` |
| var | `uvarint` string index of `server_version` |
| var | `uvarint` string index of `official_url`, only when flag `0x01` is set |
| var | `uvarint` string index of `webrtc_id`, only when flag `0x01` is set |
| 4 | internal address octets, only when flag `0x04` is set |
| 2 | `uint16` internal port, only when flag `0x04` is set |
| var | `uvarint` milliseconds from `time_hosted` to the window end |
| var | `uvarint` milliseconds from `time_last_heartbeat` to the window end |
| var | `uvarint` heartbeats accepted for this registration |
| 1 | `uint8` slots |
| 1 | `uint8` humans online |
| 1 | `uint8` playing |
| 1 | `uint8` spectating |
| 1 | `uint8` Resistance score |
| 1 | `uint8` Metropolis score |
| var | Resistance players |
| var | Metropolis players |
| var | spectators |

Each of the three player groups is a `uvarint` count followed by that many
records of a `uvarint` nickname string index, a `uint8` score and a `uint8`
deaths count.

The flags byte:

| Bit | Meaning |
|---|---|
| `0x01` | the server is official |
| `0x02` | the server is ranked |
| `0x04` | the heartbeat carries an internal network address |
| `0x08` | the heartbeat marks an editor playtesting server |
| `0x10` | the advertised arena is published in the catalogue |
| `0x20` | the heartbeat reports the server as full |
| `0x40` | unused, always clear |
| `0x80` | unused, always clear |

Whether a server counts as full is the game's own notion of a full server.

## The digest

CRC-32 as used by zlib and PNG: reflected polynomial `0xEDB88320`, starting
value `0xFFFFFFFF`, final value inverted. It covers every byte written so far
**except the eight magic bytes**, and is appended big endian as the last four
bytes of the file.
