# KX8 core datasheet (rev C, extract)

Applies to the KX8 core as fitted to the LP-series access controllers. This extract covers
the programmer's model, the instruction set, the bus timing and the flash container. The
application notes, the package drawings and the electrical characteristics are not part of
this extract.

## 0. Applicability

This is the rev C book. The controllers in the field carry rev D silicon and no errata sheet
for that revision was ever published, so this text describes the part as it was specified,
not necessarily as it was built. The capture under `../samples/conformance` was taken off a
rev D part on the production jig; where it and this document disagree, the part is right.

## 1. Overview

The KX8 is an 8-bit core with a flat 16-bit address space. There is no cache, no pipeline
and no interrupt controller. Instructions are 1 to 5 bytes long. Every instruction takes a
fixed number of clock cycles except conditional transfers, which cost more when the transfer
is taken, and operand accesses that land in the peripheral window, which cost one extra
cycle each.

## 2. Address space

| Range           | Contents                                                       |
|-----------------|----------------------------------------------------------------|
| 0x0000 - 0xFEFF | RAM. The boot loader shadows the flash body into 0x0000 upward before the core is released, so this region is both code and data and may be written by the running program. |
| 0xFF00 - 0xFF1F | Peripheral window (section 7). Not RAM. |
| 0xFF20 - 0xFFFF | RAM. |

RAM that the shadowed body does not cover reads as 0x00 at reset.

All address arithmetic is modulo 0x10000. There is no alignment requirement and no
protection: a program may write over its own code.

## 3. Programmer's model

Eight 8-bit general registers, R0 to R7. All are equivalent; none is special-cased by the
instruction set.

Four register pairs address memory. A pair holds a 16-bit value:

| Pair | High byte | Low byte |
|------|-----------|----------|
| P0   | R1        | R0       |
| P1   | R3        | R2       |
| P2   | R5        | R4       |
| P3   | R7        | R6       |

PC is the 16-bit program counter. SP is the 16-bit stack pointer.

Three flags: Z (result was zero), C (carry, borrow or rotated-out bit, depending on the
instruction), S (bit 7 of the result). Section 6 lists what each instruction does to them.
Instructions not listed there leave all three flags untouched.

### Reset

At reset the core clears R0 to R7 and all three flags, sets SP to 0x7FFE, and loads PC from
the 16-bit **big-endian** word at address 0x0000. The two bytes at 0x0002 are reserved for a
fault vector that this revision does not use.

### Stack

`PUSH` writes the register to the address in SP and then decrements SP by one. `POP`
increments SP by one and then reads the register from the address in SP. `CALL` pushes the
high byte of the return address and then its low byte; `RET` pops the low byte and then the
high byte. The stack lives in ordinary RAM and wraps with the address space.

## 4. Instruction encoding

The first byte selects the operation. Depending on the operation it is followed by an
operand byte carrying two 4-bit fields, by an 8-bit immediate or displacement, or by a
16-bit field.

* Two-field operand bytes are written high nibble first. Which field is a register, a pair
  or a count depends on the operation (section 6). A field that names a register must be 0
  to 7; a field that names a pair must be 0 to 3. Anything else is an illegal instruction.
* **16-bit fields inside an instruction — immediates, absolute addresses and wide
  displacements — are little-endian.** This is not the byte order the core uses for 16-bit
  values in memory (section 5) or for the reset vector (section 3).
* 8-bit displacements are signed two's complement. Wide displacements are signed 16-bit.

### Wide prefix

The byte 0xED is a prefix. It promotes the displacement of the instruction that follows from
8 bits to 16 bits, adding one byte to the length and one cycle to the timing. It is defined
only in front of opcodes 0x30, 0x31, 0x48 and 0x49. In front of anything else it is an
illegal instruction.

### Illegal instructions

An opcode that section 6 does not define, a field that names a register above 7 or a pair
above 3, a misplaced wide prefix, or an instruction whose bytes would run past 0xFFFF, is an
illegal instruction. The core stops at that address and raises the illegal-instruction
fault. There is no fault handler in this revision.

## 5. Data in memory

Byte accesses need no comment. The word forms `LDW` and `STW` transfer a pair to or from two
consecutive addresses **big-endian**: the high byte of the pair is at the lower address.

## 6. Instruction set

`Rd`, `Rs`, `Rr` name registers; `Pp` names a pair; `#n` is a rotate count 0 to 7; `imm8`
and `imm16` are immediates; `d8` and `d16` are signed displacements; `abs16` is an absolute
address. "Cycles" is the base cost, before the additions in section 7.

| Opcode | Operand bytes        | Mnemonic          | Len | Cycles | Flags |
|--------|----------------------|-------------------|-----|--------|-------|
| 0x00   | -                    | NOP               | 1   | 2      | -     |
| 0x01   | -                    | HLT               | 1   | 2      | -     |
| 0x02   | -                    | RET               | 1   | 6      | -     |
| 0x10   | [d:s]                | MOV Rd, Rs        | 2   | 3      | -     |
| 0x11   | [d:s]                | ADD Rd, Rs        | 2   | 3      | Z C S |
| 0x12   | [d:s]                | SUB Rd, Rs        | 2   | 3      | Z C S |
| 0x13   | [d:s]                | AND Rd, Rs        | 2   | 3      | Z C S |
| 0x14   | [d:s]                | OR Rd, Rs         | 2   | 3      | Z C S |
| 0x15   | [d:s]                | XOR Rd, Rs        | 2   | 3      | Z C S |
| 0x16   | [d:s]                | CMP Rd, Rs        | 2   | 3      | Z C S |
| 0x17   | [d:s]                | MUL Rd, Rs        | 2   | 5      | Z C S |
| 0x18   | [d:n]                | ROL Rd, #n        | 2   | 3      | Z C S |
| 0x19   | [d:n]                | ROR Rd, #n        | 2   | 3      | Z C S |
| 0x20+r | imm8                 | LDI Rr, #imm8     | 2   | 3      | -     |
| 0x28+p | imm16                | LDPI Pp, #imm16   | 3   | 4      | -     |
| 0x30   | [d:p] d8             | LDB Rd, [Pp+d8]   | 3   | 5      | -     |
| 0x31   | [d:p] d8             | STB Rd, [Pp+d8]   | 3   | 5      | -     |
| 0x32   | [0:d] abs16          | LDB Rd, [abs16]   | 4   | 6      | -     |
| 0x33   | [0:d] abs16          | STB Rd, [abs16]   | 4   | 6      | -     |
| 0x34   | [0:p] abs16          | LDW Pp, [abs16]   | 4   | 7      | -     |
| 0x35   | [0:p] abs16          | STW Pp, [abs16]   | 4   | 7      | -     |
| 0x40   | abs16                | JMP abs16         | 3   | 5      | -     |
| 0x41   | abs16                | JZ abs16          | 3   | 4      | -     |
| 0x42   | abs16                | JNZ abs16         | 3   | 4      | -     |
| 0x43   | abs16                | JC abs16          | 3   | 4      | -     |
| 0x44   | abs16                | JNC abs16         | 3   | 4      | -     |
| 0x45   | abs16                | JS abs16          | 3   | 4      | -     |
| 0x46   | abs16                | JNS abs16         | 3   | 4      | -     |
| 0x47   | abs16                | CALL abs16        | 3   | 8      | -     |
| 0x48   | d8                   | JR d8             | 2   | 5      | -     |
| 0x49   | [0:r] d8             | DJNZ Rr, d8       | 3   | 4      | -     |
| 0x50+r | -                    | PUSH Rr           | 1   | 3      | -     |
| 0x58+r | -                    | POP Rr            | 1   | 3      | -     |
| 0x70+r | imm8                 | ADDI Rr, #imm8    | 2   | 3      | Z C S |
| 0x78+r | imm8                 | XORI Rr, #imm8    | 2   | 3      | Z C S |
| 0x80+r | imm8                 | MULI Rr, #imm8    | 2   | 5      | Z C S |
| 0x88+r | imm8                 | CMPI Rr, #imm8    | 2   | 3      | Z C S |
| 0xF0+r | -                    | SWAP Rr           | 1   | 2      | Z S   |
| 0xED   | prefix               | wide displacement | +1  | +1     | -     |

`+r` is 0 to 7 and `+p` is 0 to 3, so 0x2C to 0x2F are not defined. Every opcode absent from
the table is undefined.

Semantics that are not obvious from the mnemonic:

* `CMP` and `CMPI` compute the subtraction for the flags and discard the difference.
* `SUB`, `CMP` and `CMPI` set C when the subtrahend is greater than the minuend as unsigned
  bytes, that is, when the subtraction borrows.
* `MUL` and `MULI` keep the low byte of the 16-bit product in Rd and set C when the high
  byte of the product is not zero.
* `AND`, `OR`, `XOR` and `XORI` clear C.
* `ROL Rd, #n` rotates left by n bit positions with no carry involvement, and leaves in C
  the last bit that left bit 7. `ROR Rd, #n` rotates right and leaves in C the last bit that
  left bit 0. A count of zero moves no bits, leaves C alone and still reports Z and S for the
  unchanged register.
* `SWAP` exchanges the two nibbles of the register and leaves C alone.
* `DJNZ` decrements the register, transfers control when the result is not zero, and does
  not touch the flags.
* `LDB`/`STB`/`LDW`/`STW` and the transfers do not touch the flags.
* Indexed forms compute the address as the pair plus the sign-extended displacement.
* Relative forms compute the target as the address of the following instruction plus the
  sign-extended displacement.

## 7. Timing and peripherals

Add to the base cost of an instruction:

* **2 cycles** when a conditional transfer (0x41 to 0x46, 0x49) is taken.
* **1 cycle** when the instruction's operand access touches the peripheral window, whatever
  the number of bytes transferred. Instruction fetch never attracts this penalty.

The peripheral window is 0xFF00 to 0xFF1F. Registers not listed below read as 0x00 and
discard writes.

| Address | Name   | Access | Description |
|---------|--------|--------|-------------|
| 0xFF00  | KSTAT  | read   | Key port status. Bit 0 (RDY) is set while an unread byte is waiting. Bit 1 (END) is set once the presented stream has been read to the end, and is clear while bytes remain. Bit 2 (FLT) is a sticky flag, set by a read of KDATA with RDY clear, and cleared only by reset. Bits 3 to 7 read as zero. |
| 0xFF01  | KDATA  | read   | Key port data. Reading takes the next byte of the presented stream and advances the port. Reading with RDY clear yields 0x00 and sets FLT. |
| 0xFF08  | CYCL   | read   | Low byte of the free-running cycle counter, sampled at the start of the instruction performing the read. |
| 0xFF09  | CYCH   | read   | High byte of the same sample. |
| 0xFF10  | LATCH  | write  | Result latch. Each write is appended to the latch record in order. Reading returns the byte written last, or 0x00 before the first write. |

The key port is loaded by the reader before the core is released and is not refilled while
the core runs: a stream of length L presents L bytes, after which RDY stays clear and END
stays set.

The core stops on `HLT` and on the illegal-instruction fault. A core that has executed
2,000,000 instructions without stopping is considered hung and is cut off by the bench
harness.

## 8. Flash container (KXF1)

A 16-byte header followed by the body. All multi-byte header fields are **big-endian**.

| Offset | Size | Field                                                             |
|--------|------|-------------------------------------------------------------------|
| 0      | 4    | Magic, the ASCII bytes `KXF1`                                     |
| 4      | 1    | Container version, 1 for this revision                            |
| 5      | 1    | Flags, 0 for this revision                                        |
| 6      | 2    | Load address, 0x0000 for this revision                            |
| 8      | 2    | Body length in bytes, 1 to 0xFF00                                 |
| 10     | 2    | Body checksum: the sum of the body bytes taken modulo 0x10000     |
| 12     | 4    | Reserved, all zero                                                |
| 16     | ...  | Body, shadowed into RAM at the load address                       |

A reader checks the magic, the container version, the flags, the load address and the
reserved bytes, then the declared body length against the size of the file, and last the
checksum. An image that fails any of these checks is not to be executed.
