# Master server packet journal (`.cap`)

Every datagram that reached a master server command socket was appended to a
journal file. The journal stores the arrival time, the address the datagram came
from and the datagram itself, untouched. Nothing in the journal has been
decoded: the payload bytes are exactly the bytes a game server put on the wire,
so they follow the master server request format that the game sources define.

All integers below are little endian.

## Header

| Offset | Size | Field |
|---|---|---|
| 0  | 8 | magic, the ASCII bytes `HMSJRNL1` |
| 8  | 4 | `uint32` record count |
| 12 | 8 | `float64` window start, seconds since the Unix epoch |
| 20 | 8 | `float64` window end, seconds since the Unix epoch |

The window is the period the socket was recorded for. It starts no later than
the first record and ends no earlier than the last one.

## Records

The header is followed by exactly `record count` records, laid out back to back
with no padding:

| Size | Field |
|---|---|
| 8 | `float64` arrival time, seconds since the Unix epoch |
| 1 | address family: always `4`, meaning IPv4 |
| 4 | source address, one byte per octet in the usual order |
| 2 | `uint16` source port |
| 2 | `uint16` payload length in bytes |
| n | the payload, `payload length` bytes |

Records appear in the order they arrived, so arrival times never decrease.
Several records may share an arrival time, in which case the order in the file
is the order they were handled in.

## Journals that must be rejected

An unusable journal must end the run with exit status 2 and leave no report
behind, not even half of one. A run that produces a report exits with status 0.
A journal is unusable when any of the following holds:

* the magic is not `HMSJRNL1`, or the file is shorter than the header
* the window ends before it starts
* a record is truncated, or its payload runs past the end of the file
* the file holds fewer records than the count says, or has bytes left over
  after the last record
* a record declares an address family other than `4`
* an arrival time decreases, or falls outside the window

A payload that cannot be decoded is **not** a broken journal. Datagrams get
mangled in flight, and the master server has always had an answer for that.
