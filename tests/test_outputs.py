"""Behavioural tests for the KX8 workbench: decoding, execution, mapping and recovery.

Everything here drives /app/bin/kxtool as a black box. Board-specific expectations are
either derived from the tool's own output (round trips, invariants) or checked against a
hash, so nothing in this file spells out an unlock code.
"""

import hashlib
import itertools
import json
import re
import subprocess
from pathlib import Path

import pytest

BIN = "/app/bin/kxtool"
SAMPLES = Path("/app/samples")

LINE = re.compile(r"^([0-9a-f]{4}): ((?:[0-9a-f]{2})(?: [0-9a-f]{2})*) *(\S+)(?: (.*))?$")

# Two boards ship in /app/samples; two more are held back here so a recovery that only
# works on the shipped pair cannot pass. Bodies are stored raw; the container around them
# is built below exactly as the datasheet describes it.
HELD_BACK = {
    "unit-3e52": {
        "body": (
            "0006000000002874002273238030400015423140007001441c00710182517225ed4903e8ff4774000100000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "00000000000000000000000000000000000000005b88574827fc8ce6f970ea698e77eaffae581002d54d4e978b40151b"
            "d73edbf413c5fd20c7632274683374072f044d5ed0fcdda8bfecab6dd9e12718dcda096eb3dd2f2620a4e3073fa1f6ba"
            "9ca41caa96cb0f7677f665a3d884e5201c71aad123697b4389c00304bb62716a15c8a9dcce38ffb7e42e017989021fc9"
            "3d04866c0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000f2a749f3ead7458b1eda0000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "00000000000000000000000000000000"
        ),
        "length": 10,
        "code_sha": "c83024650930dc0f175ec5d599002aea1f2bde07e890eee967edb1e2f80ffc3e",
        "entry": "0x0006",
        "patched": ("0x0074", "0x00f4"),
    },
    "unit-d160": {
        "body": (
            "000400002888002218238430400015423140007001441a007101828d72d0ed4903e8ff47880001000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000003008408258c895d8"
            "ba88c70bd9dbdb291d09d5987a4907d9b888c82950c4bae618e5088a58375bea8babf92dd9c8f86818081ca86b4c3890"
            "b088c0037cc9da3c3b9308e8585d3a6c7b91fd39fcd9db584b082dfc4d1b4aecd8f0ac6debccb8109b0d4bb728490ee9"
            "1638fae2d8fafc28608438ea5d495a4dab8aa8d7daeaa25b1a18c7aa0000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000bad246e96ab9587f2a386a6e"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
            "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
        ),
        "length": 12,
        "code_sha": "89be124e8096f14c9ad938bca2cf79a9b44c3cc9f1b6faf4e59f026ec064996d",
        "entry": "0x0004",
        "patched": ("0x0088", "0x010c"),
    },
}

SHIPPED = {
    "unit-4c17": {
        "length": 10,
        "code_sha": "43a543fe9fc1611288628dbeecac801479c512c715b63fa826a0070e0dd271db",
        "entry": "0x0004",
        "patched": ("0x0060", "0x00df"),
        "body_len": 512,
        "checksum": "0x4c62",
    },
    "unit-9a83": {
        "length": 11,
        "code_sha": "394eee9e827c156116612c079949dc921be3285a7715aa61230b39e3d23de4bc",
        "entry": "0x0004",
        "patched": ("0x0050", "0x00d2"),
        "body_len": 448,
        "checksum": "0x54b5",
    },
}

# Small hand-written programs that push their results to the result latch. They exercise
# corners of the core on their own, without any of the board firmware around them.
PROBES = {
    "endian": "00040000283412330010ff330110ff3500000132020001330210ff32030101330310ff34010001330210ff01",
    "alu": (
        "0004000020811801330010ff210043130021ee330110ff22308206330210ff230043260023ee330310ff"
        "245cf4330410ff1943330410ff252026401656270043440027ee330710ff330510ff01"
    ),
    "stack": "0004000025aa26bb55565f330710ff5f330710ff2b00802077ed3103107f472200012099330010ff02",
    "loop": "00040000200371054900fb330110ff01",
    "ram_store": "0004000020013300000101",
    "io_store": "000400002001330010ff01",
    "fault": "0004000000c301",
    "wide_misuse": "00040000ed0001",
}


def container(body: bytes) -> bytes:
    """Wrap a body in a valid KXF1 container."""
    head = bytearray(16)
    head[0:4] = b"KXF1"
    head[4] = 1
    head[5] = 0
    head[6:8] = (0).to_bytes(2, "big")
    head[8:10] = len(body).to_bytes(2, "big")
    head[10:12] = (sum(body) & 0xFFFF).to_bytes(2, "big")
    return bytes(head) + body


def tool(*args):
    """Invoke the workbench binary and hand back the completed process."""
    return subprocess.run([BIN, *args], capture_output=True, text=True, check=False, timeout=600)


def ok_json(*args):
    """Invoke the binary, insist it succeeded, and parse its single JSON object."""
    proc = tool(*args)
    assert proc.returncode == 0, f"{args} failed: {proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture(scope="session")
def workdir(tmp_path_factory):
    """Materialise the held-back boards and the probe programs as real image files."""
    d = tmp_path_factory.mktemp("kx8")
    for name, spec in HELD_BACK.items():
        (d / f"{name}.fw").write_bytes(container(bytes.fromhex(spec["body"])))
    for name, body in PROBES.items():
        (d / f"probe-{name}.fw").write_bytes(container(bytes.fromhex(body)))
    return d


def board_path(workdir, name):
    if name in SHIPPED:
        return str(SAMPLES / f"{name}.fw")
    return str(workdir / f"{name}.fw")


ALL_BOARDS = {**SHIPPED, **HELD_BACK}


def disasm_lines(*args):
    proc = tool("disasm", *args)
    assert proc.returncode == 0, proc.stderr
    out = []
    for raw in proc.stdout.splitlines():
        m = LINE.match(raw)
        assert m, f"line does not follow the contract: {raw!r}"
        out.append(
            {
                "addr": int(m.group(1), 16),
                "bytes": [int(b, 16) for b in m.group(2).split()],
                "mnemonic": m.group(3),
                "operands": (m.group(4) or "").strip(),
            }
        )
    return out


# What the bench capture in /app/samples/conformance records for each shipped ROM.
CAPTURE = {
    "rotate-left": (109, ["0x06", "0x00", "0xb4", "0x00", "0xc3", "0x00", "0xd3"]),
    "rotate-right": (109, ["0x60", "0x00", "0x2d", "0x00", "0xc3", "0x00", "0x7a"]),
    "add-paths": (106, ["0x31", "0x32", "0x31", "0x10", "0x01"]),
    "flag-rules": (143, ["0x20", "0x01", "0x1e", "0x00", "0x00", "0x00", "0x01", "0x01"]),
    "bus-timing": (40, ["0x11", "0x22"]),
    "transfers": (86, ["0xbb", "0xaa", "0x12", "0x99"]),
}


@pytest.mark.parametrize("rom", sorted(CAPTURE))
def test_core_reproduces_the_bench_capture(rom):
    """Running each shipped ROM gives back exactly what the part on the jig produced."""
    cycles, latch = CAPTURE[rom]
    out = ok_json("run", "--image", str(SAMPLES / "conformance" / f"{rom}.fw"))
    assert out["latch"] == latch, f"{rom} latched something else"
    assert out["cycles"] == cycles, f"{rom} cost a different number of cycles"


def test_the_work_is_done_by_the_compiled_crate():
    """The launcher is a thin front for a real binary that answers on its own."""
    artifact = Path("/app/target/release/kxtool")
    assert artifact.exists(), "the crate produced no binary"
    assert artifact.read_bytes()[:4] == b"\x7fELF", "the built artefact is not a native binary"
    assert Path(BIN).stat().st_size < 2048, "the entry point is carrying an implementation"

    args = ["map", "--image", str(SAMPLES / "unit-4c17.fw")]
    # An empty PATH: a program built from the standard library needs nothing else on disk.
    direct = subprocess.run(
        [str(artifact), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=600,
        env={"PATH": "/nonexistent"},
    )
    assert direct.returncode == 0, f"the binary cannot answer by itself: {direct.stderr}"
    assert direct.stdout == tool(*args).stdout


def test_unknown_subcommand_is_refused():
    """An unrecognised subcommand fails with a contract error object and no stdout."""
    proc = tool("frobnicate", "--image", str(SAMPLES / "unit-4c17.fw"))
    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert json.loads(proc.stderr)["error"] == "bad_argument"


def test_odd_length_key_is_refused():
    """A key stream that is not whole bytes of hexadecimal is rejected before execution."""
    proc = tool("run", "--image", str(SAMPLES / "unit-4c17.fw"), "--key", "abc")
    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert json.loads(proc.stderr)["error"] == "bad_argument"


def test_damaged_container_is_refused():
    """The sample whose stored checksum no longer matches its body is not executed."""
    proc = tool("map", "--image", str(SAMPLES / "unit-corrupt.fw"))
    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert json.loads(proc.stderr)["error"] == "bad_checksum"


@pytest.mark.parametrize(
    ("damage", "expected"),
    [
        ("magic", "bad_magic"),
        ("version", "bad_version"),
        ("flags", "bad_flags"),
        ("load", "bad_load_address"),
        ("length", "bad_length"),
        ("reserved", "bad_reserved"),
    ],
)
def test_header_fields_are_validated(workdir, damage, expected):
    """Each header field the container defines is checked before the body is trusted."""
    raw = bytearray(container(bytes.fromhex(PROBES["loop"])))
    if damage == "magic":
        raw[3] = ord("2")
    elif damage == "version":
        raw[4] = 2
    elif damage == "flags":
        raw[5] = 0x01
    elif damage == "load":
        raw[6] = 0x01
    elif damage == "length":
        raw[9] = (raw[9] + 1) & 0xFF
    else:
        raw[14] = 0x09
    path = workdir / f"damaged-{damage}.fw"
    path.write_bytes(bytes(raw))
    proc = tool("run", "--image", str(path))
    assert proc.returncode == 2
    assert proc.stdout.strip() == ""
    assert json.loads(proc.stderr)["error"] == expected


def test_disasm_emits_one_line_per_requested_instruction():
    """disasm prints exactly --count lines and advances by each instruction's length."""
    lines = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", "0x0004", "--count", "13")
    assert len(lines) == 13
    for cur, nxt in itertools.pairwise(lines):
        assert nxt["addr"] == cur["addr"] + len(cur["bytes"])


def test_disasm_window_defaults_to_sixteen_instructions():
    """With no --count the disassembler prints the contract's default window."""
    lines = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", "0x0004")
    assert len(lines) == 16


def test_reset_code_decodes_to_the_documented_forms():
    """The plain part of a sample board decodes to the mnemonics its bytes encode."""
    lines = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", "0x0004", "--count", "13")
    got = [line["mnemonic"] for line in lines]
    assert got == [
        "LDPI", "LDI", "LDI", "LDB", "XOR", "STB", "ADDI",
        "JNC", "ADDI", "MULI", "ADDI", "DJNZ", "CALL",
    ]
    assert lines[3]["operands"] == "R4, [P0+0x00]"


def test_instruction_immediates_are_little_endian():
    """A 16-bit immediate reads back low byte first, unlike the reset vector."""
    lines = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", "0x0004", "--count", "1")
    assert lines[0]["bytes"] == [0x28, 0x60, 0x00]
    assert lines[0]["operands"] == "P0, #0x0060"


def test_wide_prefix_extends_the_instruction():
    """A prefixed instruction is one byte longer and resolves its 16-bit displacement."""
    lines = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", "0x0004", "--count", "12")
    wide = lines[-1]
    assert wide["mnemonic"] == "DJNZ"
    assert len(wide["bytes"]) == 5
    assert wide["bytes"][0] == 0xED
    assert wide["operands"] == "R3, 0x000b"


def test_shipped_bytes_of_the_rewritten_region_do_not_decode():
    """Disassembling the region as shipped runs into bytes that are not instructions."""
    start = SHIPPED["unit-4c17"]["patched"][0]
    lines = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", start, "--count", "12")
    assert len(lines) == 12
    assert any(line["mnemonic"] == ".byte" for line in lines)


def test_live_view_of_the_rewritten_region_decodes_cleanly():
    """After the board has run, the same region holds real instructions."""
    start = SHIPPED["unit-4c17"]["patched"][0]
    shipped = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", start, "--count", "12")
    live = disasm_lines("--image", str(SAMPLES / "unit-4c17.fw"), "--addr", start, "--count", "12", "--live")
    assert len(live) == 12
    assert all(line["mnemonic"] != ".byte" for line in live)
    assert [line["bytes"] for line in live] != [line["bytes"] for line in shipped]


@pytest.mark.parametrize("name", sorted(ALL_BOARDS))
def test_map_reports_entry_and_the_rewritten_range(workdir, name):
    """map names the reset target and the stretch of body the board rewrites."""
    spec = ALL_BOARDS[name]
    out = ok_json("map", "--image", board_path(workdir, name))
    assert out["entry"] == spec["entry"]
    assert out["load"] == "0x0000"
    assert out["patched"] == [{"start": spec["patched"][0], "end": spec["patched"][1]}]
    assert out["io_reads"] == ["0xff00"]
    assert out["io_writes"] == ["0xff10"]


def test_map_repeats_the_header_fields():
    """map reports the body length and stored checksum taken from the container."""
    out = ok_json("map", "--image", str(SAMPLES / "unit-4c17.fw"))
    assert out["body_len"] == SHIPPED["unit-4c17"]["body_len"]
    assert out["checksum"] == SHIPPED["unit-4c17"]["checksum"]


def test_board_with_no_key_refuses():
    """A board released with nothing at the key port denies and takes no key bytes."""
    out = ok_json("run", "--image", str(SAMPLES / "unit-4c17.fw"))
    assert out["status"] == "denied"
    assert out["latch"] == ["0x5a"]
    assert out["key_reads"] == 0
    assert out["fault"] is None


def test_empty_key_run_costs_the_documented_number_of_cycles():
    """Cycle accounting over a whole board run matches what the part charges."""
    out = ok_json("run", "--image", str(SAMPLES / "unit-4c17.fw"))
    assert out["instructions"] == 1030
    assert out["cycles"] == 4762


def test_peripheral_access_stalls_the_bus(workdir):
    """The same store costs more when it lands in the peripheral window than in memory."""
    ram = ok_json("run", "--image", str(workdir / "probe-ram_store.fw"))
    io = ok_json("run", "--image", str(workdir / "probe-io_store.fw"))
    assert ram["cycles"] == 11
    assert io["cycles"] == 13
    assert io["latch"] == ["0x01"]


def test_taken_conditional_transfers_cost_more(workdir):
    """A counted loop pays the taken-transfer penalty only on the iterations that loop."""
    out = ok_json("run", "--image", str(workdir / "probe-loop.fw"))
    assert out["latch"] == ["0x0f"]
    assert out["cycles"] == 38


def test_immediates_and_memory_words_use_opposite_byte_orders(workdir):
    """A pair loaded from an immediate and stored to memory comes back with halves swapped."""
    out = ok_json("run", "--image", str(workdir / "probe-endian.fw"))
    assert out["latch"] == ["0x34", "0x12", "0x12", "0x34", "0x34"]


def test_arithmetic_and_rotate_results_match_the_part(workdir):
    """Rotate, multiply, swap and compare leave the registers and flags the part leaves."""
    out = ok_json("run", "--image", str(workdir / "probe-alu.fw"))
    assert out["latch"] == ["0x06", "0xee", "0x20", "0x00", "0xc5", "0x5c", "0x00", "0x20"]


def test_stack_and_call_ordering(workdir):
    """Pushes pop back in reverse and a call returns to the instruction after it."""
    out = ok_json("run", "--image", str(workdir / "probe-stack.fw"))
    assert out["latch"] == ["0xbb", "0xaa", "0x77", "0x99"]


def test_undefined_opcode_faults_where_it_stands(workdir):
    """An undefined opcode stops the core at its own address without completing."""
    out = ok_json("run", "--image", str(workdir / "probe-fault.fw"))
    assert out["status"] == "fault"
    assert out["fault"] == "illegal_instruction"
    assert out["halt_pc"] == "0x0005"
    assert out["instructions"] == 1


def test_misplaced_wide_prefix_faults(workdir):
    """The wide prefix in front of an instruction that has no displacement is illegal."""
    out = ok_json("run", "--image", str(workdir / "probe-wide_misuse.fw"))
    assert out["status"] == "fault"
    assert out["halt_pc"] == "0x0004"
    assert out["instructions"] == 0


@pytest.mark.parametrize("name", sorted(SHIPPED))
def test_recovered_code_unlocks_the_shipped_boards(workdir, name):
    """The recovered stream is the one the sample board accepts."""
    spec = SHIPPED[name]
    path = board_path(workdir, name)
    out = ok_json("recover", "--image", path)
    assert out["length"] == spec["length"]
    assert len(out["code_hex"]) == 2 * spec["length"]
    assert hashlib.sha256(out["code_hex"].strip().lower().encode()).hexdigest() == spec["code_sha"]
    assert ok_json("run", "--image", path, "--key", out["code_hex"])["status"] == "granted"


@pytest.mark.parametrize("name", sorted(HELD_BACK))
def test_recovery_generalises_to_unseen_boards(workdir, name):
    """Recovery works on boards with different codes, constants and layout."""
    spec = HELD_BACK[name]
    path = board_path(workdir, name)
    out = ok_json("recover", "--image", path)
    assert out["length"] == spec["length"]
    assert hashlib.sha256(out["code_hex"].strip().lower().encode()).hexdigest() == spec["code_sha"]
    assert ok_json("run", "--image", path, "--key", out["code_hex"])["status"] == "granted"


def test_recovered_text_matches_the_recovered_bytes():
    """code_text renders exactly the bytes of code_hex when they are all printable."""
    out = ok_json("recover", "--image", str(SAMPLES / "unit-4c17.fw"))
    assert out["code_text"] is not None
    assert bytes.fromhex(out["code_hex"]).decode("ascii") == out["code_text"]


def test_every_single_byte_change_is_refused():
    """Changing any one byte of the accepted stream turns the verdict to denied."""
    path = str(SAMPLES / "unit-4c17.fw")
    code = bytearray(bytes.fromhex(ok_json("recover", "--image", path)["code_hex"]))
    for i in range(len(code)):
        spoiled = bytearray(code)
        spoiled[i] ^= 0x2A
        out = ok_json("run", "--image", path, "--key", spoiled.hex())
        assert out["status"] == "denied", f"byte {i} was not checked"


def test_rejected_attempts_of_equal_length_cost_the_same():
    """The board spends the same work on every stream of its length, whatever it contains."""
    path = str(SAMPLES / "unit-4c17.fw")
    code = bytearray(bytes.fromhex(ok_json("recover", "--image", path)["code_hex"]))
    costs = set()
    for i in range(len(code)):
        spoiled = bytearray(code)
        spoiled[i] ^= 0x11
        out = ok_json("run", "--image", path, "--key", spoiled.hex())
        assert out["status"] == "denied"
        costs.add((out["instructions"], out["cycles"]))
    blank = ok_json("run", "--image", path, "--key", "00" * len(code))
    costs.add((blank["instructions"], blank["cycles"]))
    assert len(costs) == 1, f"the cost of a rejected attempt varies with its content: {costs}"


def test_short_and_long_key_streams_are_refused():
    """A truncated stream and an over-long stream are both rejected by the board."""
    path = str(SAMPLES / "unit-4c17.fw")
    code = bytes.fromhex(ok_json("recover", "--image", path)["code_hex"])
    short = ok_json("run", "--image", path, "--key", code[:-1].hex())
    assert short["status"] == "denied"
    assert short["key_reads"] == len(code) - 1
    long = ok_json("run", "--image", path, "--key", (code + b"\x41").hex())
    assert long["status"] == "denied"
    assert long["key_reads"] == len(code)


def test_key_port_stops_at_the_stream_the_board_wants():
    """An over-long stream is read only as far as the board's key length."""
    path = str(SAMPLES / "unit-4c17.fw")
    length = ok_json("recover", "--image", path)["length"]
    out = ok_json("run", "--image", path, "--key", "00" * 64)
    assert out["key_reads"] == length


@pytest.mark.parametrize("name", sorted(ALL_BOARDS))
def test_output_is_reproducible(workdir, name):
    """Two identical invocations produce identical output."""
    path = board_path(workdir, name)
    for args in (("map", "--image", path), ("recover", "--image", path)):
        first = tool(*args)
        second = tool(*args)
        assert first.returncode == second.returncode == 0
        assert first.stdout == second.stdout


def test_images_are_left_untouched(workdir):
    """None of the subcommands writes back to the image it was given."""
    path = SAMPLES / "unit-4c17.fw"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    ok_json("map", "--image", str(path))
    ok_json("recover", "--image", str(path))
    ok_json("run", "--image", str(path), "--key", "4142")
    tool("disasm", "--image", str(path), "--addr", "0x0000", "--count", "40", "--live")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
