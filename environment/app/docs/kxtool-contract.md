# kxtool output contract

`kxtool` is the bench-side workbench for KXF1 images. Other tooling parses its output, so
the shapes below are fixed. The core it models is specified in `kx8-datasheet.md`.

    kxtool disasm --image PATH --addr ADDR --count N [--live]
    kxtool run     --image PATH [--key HEX]
    kxtool map     --image PATH
    kxtool recover --image PATH

`--image` is required everywhere and `--addr` is required by `disasm`. `ADDR` is a 16-bit
address, written either as `0x` plus hexadecimal digits or as a decimal number. `--count` is
1 to 4096 and defaults to 16. `--key` is an even-length string of hexadecimal digits (either
case) and defaults to empty. An option a subcommand has no use for is accepted and ignored.

Every image is validated as a container before anything else happens.

## Exit status and errors

Success prints the output described below on stdout and exits 0. Any failure prints nothing
on stdout, prints one JSON object on stderr and exits 2:

    {"error":"bad_checksum","detail":"stored 0x39c4, computed 0x7bc4"}

`detail` is free text. `error` is one of `bad_magic`, `bad_version`, `bad_flags`,
`bad_load_address`, `bad_length`, `bad_checksum`, `bad_reserved`, `bad_argument`,
`io_error`, `unrecoverable`.

kxtool never writes to the image it was given.

## The empty-key run

`map` and `disasm --live` both describe the machine as it stands when it stops after being
started from reset with an empty key stream. "Stops" means the halt instruction, the
illegal-instruction fault, or the step limit, whichever comes first.

## disasm

One line per instruction, `--count` lines, starting at `--addr` and advancing by the length
of each decoded instruction. `--live` disassembles the memory of the empty-key run instead
of the image as it was shadowed at reset.

    0200: 28 40 03       LDPI P0, #0x0340
    0203: 25 1f          LDI R5, #0x1f
    0205: ed 30 41 20 fe LDB R4, [P1-0x01e0]
    020a: 42 00 02       JNZ 0x0200
    020d: 3b             .byte 0x3b

The address is four lowercase hexadecimal digits, then `: `, then the instruction's bytes as
two lowercase hexadecimal digits each separated by single spaces, left-justified in a
14-column field, then one space, then the instruction. Mnemonics are upper case, operands
are separated by `, `.

Operands are written `R3`, `P2`, `#0x1f` for an 8-bit immediate, `#0x1f2a` for a 16-bit
immediate, `#3` for a rotate count, `[0xff01]` for an absolute address, `[P2+0x34]` or
`[P2-0x12]` for an indexed access with a signed 8-bit displacement, `[P2+0x1234]` for a wide
one, and the resolved target address as `0x000b` for every transfer of control including the
relative forms.

An illegal instruction is printed as `.byte 0xNN` for its first byte, and the disassembly
resumes at the very next address.

## run

Presents `--key` at the key port, releases the core and prints one JSON object:

    {"status":"denied","fault":null,"halt_pc":"0x0031","instructions":712,"cycles":3260,"key_reads":0,"latch":["0x5a"]}

* `status` is `granted` when the machine stopped at a halt instruction and the last byte
  written to the latch was 0xa5, `denied` when it was 0x5a, `halted` for any other clean
  stop, `fault` for the illegal-instruction fault and `timeout` for the step limit.
* `fault` is `"illegal_instruction"` when the machine faulted, otherwise null.
* `halt_pc` is the address of the instruction the machine stopped on.
* `instructions` counts instructions that completed, the stopping one included; a faulting
  instruction does not complete.
* `cycles` is the total cost of those instructions.
* `key_reads` counts the bytes taken from the key port.
* `latch` lists the bytes written to the latch, in order.

## map

Describes the image and what the empty-key run did to it:

    {"entry":"0x0008","load":"0x0000","body_len":384,"checksum":"0x39c4","patched":[{"start":"0x0044","end":"0x00a1"}],"io_reads":["0xff00","0xff01"],"io_writes":["0xff10"],"status":"denied","halt_pc":"0x0031","instructions":712,"cycles":3260}

* `entry` is the address the reset vector points at, `load` and `checksum` come from the
  header, `body_len` is the body length in bytes.
* `patched` lists the stretches of the body that the empty-key run left holding something
  other than what the image shipped. Ranges are maximal, ascending and half-open: `start`
  is the first changed address and `end` is one past the last. Addresses outside the body
  are not reported.
* `io_reads` and `io_writes` are the distinct peripheral addresses the run read from and
  wrote to, ascending.
* `status`, `halt_pc`, `instructions` and `cycles` are as for `run`.

## recover

Reconstructs the key stream that the image accepts:

    {"length":9,"code_hex":"444f434b5349444537","code_text":"DOCKSIDE7"}

* `length` is the number of bytes in the stream.
* `code_hex` is those bytes, lowercase hexadecimal, no separators.
* `code_text` is the same bytes as text when every one of them is 0x20 to 0x7e, and null
  otherwise.

If no accepted stream can be reconstructed the command fails with `unrecoverable`.
