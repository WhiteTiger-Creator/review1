#!/bin/bash
# Reference solution: a KX8 disassembler, a cycle-accurate core with its two peripherals,
# and unlock-code recovery driven by the machine itself.
set -euo pipefail

cd /app

cat > /app/src/image.rs <<'KX_IMAGE_EOF'
//! KXF1 container parsing.

pub const IO_BASE: u16 = 0xFF00;
pub const IO_TOP: u16 = 0xFF1F;

pub struct Firmware {
    pub load: u16,
    pub body: Vec<u8>,
    pub checksum: u16,
}

pub fn parse(raw: &[u8]) -> Result<Firmware, (&'static str, String)> {
    if raw.len() < 16 {
        return Err(("bad_length", format!("image is {} bytes, header needs 16", raw.len())));
    }
    if &raw[0..4] != b"KXF1" {
        return Err(("bad_magic", format!("magic {:02x?} is not KXF1", &raw[0..4])));
    }
    if raw[4] != 1 {
        return Err(("bad_version", format!("container version {}", raw[4])));
    }
    if raw[5] != 0 {
        return Err(("bad_flags", format!("flags byte 0x{:02x}", raw[5])));
    }
    let load = u16::from_be_bytes([raw[6], raw[7]]);
    if load != 0 {
        return Err(("bad_load_address", format!("load address 0x{:04x}", load)));
    }
    if raw[12..16] != [0, 0, 0, 0] {
        return Err(("bad_reserved", "reserved header bytes are not zero".to_string()));
    }
    let len = u16::from_be_bytes([raw[8], raw[9]]) as usize;
    if len == 0 || len > 0xFF00 || len != raw.len() - 16 {
        return Err(("bad_length", format!("declared body length {} for {} trailing bytes", len, raw.len() - 16)));
    }
    let stored = u16::from_be_bytes([raw[10], raw[11]]);
    let body = raw[16..].to_vec();
    let sum = body.iter().fold(0u16, |a, b| a.wrapping_add(*b as u16));
    if sum != stored {
        return Err(("bad_checksum", format!("stored 0x{:04x}, computed 0x{:04x}", stored, sum)));
    }
    Ok(Firmware { load, body, checksum: stored })
}

pub fn is_io(addr: u16) -> bool {
    addr >= IO_BASE && addr <= IO_TOP
}
KX_IMAGE_EOF

cat > /app/src/decode.rs <<'KX_DECODE_EOF'
//! KX8 instruction decoding and disassembly text.

#[derive(Clone)]
pub struct Insn {
    pub addr: u16,
    pub len: u16,
    pub cycles: u32,
    pub op: u8,
    pub wide: bool,
    pub rd: u8,
    pub rs: u8,
    pub imm: u16,
    pub disp: i32,
    pub target: u16,
    pub illegal: bool,
    pub bytes: Vec<u8>,
}

impl Insn {
    fn bad(addr: u16, b: u8) -> Insn {
        Insn {
            addr,
            len: 1,
            cycles: 0,
            op: b,
            wide: false,
            rd: 0,
            rs: 0,
            imm: 0,
            disp: 0,
            target: 0,
            illegal: true,
            bytes: vec![b],
        }
    }
}

fn nib_hi(b: u8) -> u8 {
    b >> 4
}
fn nib_lo(b: u8) -> u8 {
    b & 0x0F
}

/// Decode the instruction beginning at `addr` in the 64 KiB memory image.
pub fn decode(mem: &[u8], addr: u16) -> Insn {
    let at = |i: usize| -> Option<u8> {
        let a = addr as usize + i;
        if a > 0xFFFF {
            None
        } else {
            Some(mem[a])
        }
    };
    let first = mem[addr as usize];
    let mut off = 0usize;
    let mut wide = false;
    let mut op = first;
    if first == 0xED {
        wide = true;
        off = 1;
        op = match at(1) {
            Some(v) => v,
            None => return Insn::bad(addr, first),
        };
        if !matches!(op, 0x30 | 0x31 | 0x48 | 0x49) {
            return Insn::bad(addr, first);
        }
    }

    let mut ins = Insn {
        addr,
        len: 0,
        cycles: 0,
        op,
        wide,
        rd: 0,
        rs: 0,
        imm: 0,
        disp: 0,
        target: 0,
        illegal: false,
        bytes: Vec::new(),
    };

    macro_rules! byte {
        ($i:expr) => {
            match at($i) {
                Some(v) => v,
                None => return Insn::bad(addr, first),
            }
        };
    }

    let total: usize;
    match op {
        0x00 | 0x01 | 0x02 => {
            total = off + 1;
            ins.cycles = if op == 0x02 { 6 } else { 2 };
        }
        0x50..=0x5F => {
            total = off + 1;
            ins.rd = op & 0x07;
            ins.cycles = 3;
        }
        0xF0..=0xF7 => {
            total = off + 1;
            ins.rd = op & 0x07;
            ins.cycles = 2;
        }
        0x10..=0x19 => {
            let o = byte!(off + 1);
            ins.rd = nib_hi(o);
            ins.rs = nib_lo(o);
            if ins.rd > 7 {
                return Insn::bad(addr, first);
            }
            if op <= 0x17 && ins.rs > 7 {
                return Insn::bad(addr, first);
            }
            if op >= 0x18 && ins.rs > 7 {
                return Insn::bad(addr, first);
            }
            total = off + 2;
            ins.cycles = if op == 0x17 { 5 } else { 3 };
        }
        0x20..=0x27 | 0x70..=0x7F | 0x80..=0x8F => {
            ins.rd = op & 0x07;
            ins.imm = byte!(off + 1) as u16;
            total = off + 2;
            ins.cycles = if (0x80..=0x87).contains(&op) { 5 } else { 3 };
        }
        0x28..=0x2B => {
            ins.rd = op & 0x03;
            ins.imm = u16::from_le_bytes([byte!(off + 1), byte!(off + 2)]);
            total = off + 3;
            ins.cycles = 4;
        }
        0x30 | 0x31 => {
            let o = byte!(off + 1);
            ins.rd = nib_hi(o);
            ins.rs = nib_lo(o);
            if ins.rd > 7 || ins.rs > 3 {
                return Insn::bad(addr, first);
            }
            if wide {
                ins.disp = i16::from_le_bytes([byte!(off + 2), byte!(off + 3)]) as i32;
                total = off + 4;
                ins.cycles = 6;
            } else {
                ins.disp = byte!(off + 2) as i8 as i32;
                total = off + 3;
                ins.cycles = 5;
            }
        }
        0x32 | 0x33 => {
            let o = byte!(off + 1);
            if nib_hi(o) != 0 || nib_lo(o) > 7 {
                return Insn::bad(addr, first);
            }
            ins.rd = nib_lo(o);
            ins.imm = u16::from_le_bytes([byte!(off + 2), byte!(off + 3)]);
            total = off + 4;
            ins.cycles = 6;
        }
        0x34 | 0x35 => {
            let o = byte!(off + 1);
            if nib_hi(o) != 0 || nib_lo(o) > 3 {
                return Insn::bad(addr, first);
            }
            ins.rd = nib_lo(o);
            ins.imm = u16::from_le_bytes([byte!(off + 2), byte!(off + 3)]);
            total = off + 4;
            ins.cycles = 7;
        }
        0x40..=0x47 => {
            ins.target = u16::from_le_bytes([byte!(off + 1), byte!(off + 2)]);
            total = off + 3;
            ins.cycles = match op {
                0x40 => 5,
                0x47 => 8,
                _ => 4,
            };
        }
        0x48 => {
            if wide {
                ins.disp = i16::from_le_bytes([byte!(off + 1), byte!(off + 2)]) as i32;
                total = off + 3;
                ins.cycles = 6;
            } else {
                ins.disp = byte!(off + 1) as i8 as i32;
                total = off + 2;
                ins.cycles = 5;
            }
            ins.target = ((addr as i32 + total as i32 + ins.disp) & 0xFFFF) as u16;
        }
        0x49 => {
            let o = byte!(off + 1);
            if nib_hi(o) != 0 || nib_lo(o) > 7 {
                return Insn::bad(addr, first);
            }
            ins.rd = nib_lo(o);
            if wide {
                ins.disp = i16::from_le_bytes([byte!(off + 2), byte!(off + 3)]) as i32;
                total = off + 4;
                ins.cycles = 5;
            } else {
                ins.disp = byte!(off + 2) as i8 as i32;
                total = off + 3;
                ins.cycles = 4;
            }
            ins.target = ((addr as i32 + total as i32 + ins.disp) & 0xFFFF) as u16;
        }
        _ => return Insn::bad(addr, first),
    }

    if addr as usize + total > 0x10000 {
        return Insn::bad(addr, first);
    }
    ins.len = total as u16;
    ins.bytes = (0..total).map(|i| mem[addr as usize + i]).collect();
    ins
}

fn disp_text(d: i32, wide: bool) -> String {
    let sign = if d < 0 { '-' } else { '+' };
    let m = d.unsigned_abs();
    if wide {
        format!("{}0x{:04x}", sign, m)
    } else {
        format!("{}0x{:02x}", sign, m)
    }
}

/// Render one decoded instruction as a disassembly line.
pub fn line(ins: &Insn) -> String {
    let bytes: Vec<String> = ins.bytes.iter().map(|b| format!("{:02x}", b)).collect();
    let col = bytes.join(" ");
    let body = if ins.illegal {
        format!(".byte 0x{:02x}", ins.bytes[0])
    } else {
        text(ins)
    };
    format!("{:04x}: {:<14} {}", ins.addr, col, body)
}

fn text(ins: &Insn) -> String {
    let d = ins.rd;
    let s = ins.rs;
    match ins.op {
        0x00 => "NOP".to_string(),
        0x01 => "HLT".to_string(),
        0x02 => "RET".to_string(),
        0x50..=0x57 => format!("PUSH R{}", d),
        0x58..=0x5F => format!("POP R{}", d),
        0xF0..=0xF7 => format!("SWAP R{}", d),
        0x10 => format!("MOV R{}, R{}", d, s),
        0x11 => format!("ADD R{}, R{}", d, s),
        0x12 => format!("SUB R{}, R{}", d, s),
        0x13 => format!("AND R{}, R{}", d, s),
        0x14 => format!("OR R{}, R{}", d, s),
        0x15 => format!("XOR R{}, R{}", d, s),
        0x16 => format!("CMP R{}, R{}", d, s),
        0x17 => format!("MUL R{}, R{}", d, s),
        0x18 => format!("ROL R{}, #{}", d, s),
        0x19 => format!("ROR R{}, #{}", d, s),
        0x20..=0x27 => format!("LDI R{}, #0x{:02x}", d, ins.imm),
        0x70..=0x77 => format!("ADDI R{}, #0x{:02x}", d, ins.imm),
        0x78..=0x7F => format!("XORI R{}, #0x{:02x}", d, ins.imm),
        0x80..=0x87 => format!("MULI R{}, #0x{:02x}", d, ins.imm),
        0x88..=0x8F => format!("CMPI R{}, #0x{:02x}", d, ins.imm),
        0x28..=0x2B => format!("LDPI P{}, #0x{:04x}", d, ins.imm),
        0x30 => format!("LDB R{}, [P{}{}]", d, s, disp_text(ins.disp, ins.wide)),
        0x31 => format!("STB R{}, [P{}{}]", d, s, disp_text(ins.disp, ins.wide)),
        0x32 => format!("LDB R{}, [0x{:04x}]", d, ins.imm),
        0x33 => format!("STB R{}, [0x{:04x}]", d, ins.imm),
        0x34 => format!("LDW P{}, [0x{:04x}]", d, ins.imm),
        0x35 => format!("STW P{}, [0x{:04x}]", d, ins.imm),
        0x40 => format!("JMP 0x{:04x}", ins.target),
        0x41 => format!("JZ 0x{:04x}", ins.target),
        0x42 => format!("JNZ 0x{:04x}", ins.target),
        0x43 => format!("JC 0x{:04x}", ins.target),
        0x44 => format!("JNC 0x{:04x}", ins.target),
        0x45 => format!("JS 0x{:04x}", ins.target),
        0x46 => format!("JNS 0x{:04x}", ins.target),
        0x47 => format!("CALL 0x{:04x}", ins.target),
        0x48 => format!("JR 0x{:04x}", ins.target),
        0x49 => format!("DJNZ R{}, 0x{:04x}", d, ins.target),
        _ => format!(".byte 0x{:02x}", ins.bytes[0]),
    }
}
KX_DECODE_EOF

cat > /app/src/cpu.rs <<'KX_CPU_EOF'
//! The KX8 core, its memory map and the two peripherals the boards expose.

use crate::decode::{decode, Insn};
use crate::image::is_io;

pub const STEP_LIMIT: u64 = 2_000_000;
pub const RESET_SP: u16 = 0x7FFE;

#[derive(PartialEq, Clone, Copy, Debug)]
pub enum Stop {
    Halted,
    Fault,
    Timeout,
}

pub struct Machine {
    pub mem: Vec<u8>,
    pub r: [u8; 8],
    pub pc: u16,
    pub sp: u16,
    pub fz: bool,
    pub fc: bool,
    pub fs: bool,
    pub cycles: u64,
    pub instructions: u64,
    pub latch: Vec<u8>,
    pub key: Vec<u8>,
    pub key_pos: usize,
    pub key_fault: bool,
    pub io_reads: Vec<u16>,
    pub io_writes: Vec<u16>,
    pub stop: Option<Stop>,
    pub stop_pc: u16,
    insn_start_cycles: u64,
    io_touched: bool,
}

impl Machine {
    pub fn new(body: &[u8], key: &[u8]) -> Machine {
        let mut mem = vec![0u8; 0x10000];
        mem[..body.len()].copy_from_slice(body);
        let pc = u16::from_be_bytes([mem[0], mem[1]]);
        Machine {
            mem,
            r: [0; 8],
            pc,
            sp: RESET_SP,
            fz: false,
            fc: false,
            fs: false,
            cycles: 0,
            instructions: 0,
            latch: Vec::new(),
            key: key.to_vec(),
            key_pos: 0,
            key_fault: false,
            io_reads: Vec::new(),
            io_writes: Vec::new(),
            stop: None,
            stop_pc: 0,
            insn_start_cycles: 0,
            io_touched: false,
        }
    }

    fn note_io(&mut self, addr: u16, write: bool) {
        if !is_io(addr) {
            return;
        }
        self.io_touched = true;
        let list = if write { &mut self.io_writes } else { &mut self.io_reads };
        if let Err(i) = list.binary_search(&addr) {
            list.insert(i, addr);
        }
    }

    fn read8(&mut self, addr: u16) -> u8 {
        self.note_io(addr, false);
        match addr {
            0xFF00 => {
                let mut v = 0u8;
                if self.key_pos < self.key.len() {
                    v |= 0x01;
                } else {
                    v |= 0x02;
                }
                if self.key_fault {
                    v |= 0x04;
                }
                v
            }
            0xFF01 => {
                if self.key_pos < self.key.len() {
                    let v = self.key[self.key_pos];
                    self.key_pos += 1;
                    v
                } else {
                    self.key_fault = true;
                    0
                }
            }
            0xFF08 => (self.insn_start_cycles & 0xFF) as u8,
            0xFF09 => ((self.insn_start_cycles >> 8) & 0xFF) as u8,
            0xFF10 => *self.latch.last().unwrap_or(&0),
            a if is_io(a) => 0,
            a => self.mem[a as usize],
        }
    }

    fn write8(&mut self, addr: u16, v: u8) {
        self.note_io(addr, true);
        match addr {
            0xFF10 => self.latch.push(v),
            a if is_io(a) => {}
            a => self.mem[a as usize] = v,
        }
    }

    fn pair(&self, p: u8) -> u16 {
        let p = p as usize;
        ((self.r[2 * p + 1] as u16) << 8) | self.r[2 * p] as u16
    }

    fn set_pair(&mut self, p: u8, v: u16) {
        let p = p as usize;
        self.r[2 * p + 1] = (v >> 8) as u8;
        self.r[2 * p] = (v & 0xFF) as u8;
    }

    fn set_zs(&mut self, v: u8) {
        self.fz = v == 0;
        self.fs = v & 0x80 != 0;
    }

    fn push(&mut self, v: u8) {
        let sp = self.sp;
        self.write8(sp, v);
        self.sp = sp.wrapping_sub(1);
    }

    fn pop(&mut self) -> u8 {
        self.sp = self.sp.wrapping_add(1);
        let sp = self.sp;
        self.read8(sp)
    }

    /// Execute until the machine halts, faults or exhausts the step budget.
    pub fn run(&mut self) {
        while self.stop.is_none() {
            if self.instructions >= STEP_LIMIT {
                self.stop = Some(Stop::Timeout);
                self.stop_pc = self.pc;
                return;
            }
            self.step();
        }
    }

    fn step(&mut self) {
        self.insn_start_cycles = self.cycles;
        self.io_touched = false;
        let ins: Insn = decode(&self.mem, self.pc);
        if ins.illegal {
            self.stop = Some(Stop::Fault);
            self.stop_pc = self.pc;
            return;
        }
        let next = self.pc.wrapping_add(ins.len);
        let mut cycles = ins.cycles;
        let mut taken = false;
        let d = ins.rd as usize;
        let s = ins.rs as usize;
        let imm8 = ins.imm as u8;

        match ins.op {
            0x00 => {}
            0x01 => {
                self.stop = Some(Stop::Halted);
                self.stop_pc = self.pc;
                self.cycles += cycles as u64;
                self.instructions += 1;
                return;
            }
            0x02 => {
                let lo = self.pop();
                let hi = self.pop();
                self.cycles += cycles as u64;
                self.instructions += 1;
                self.pc = ((hi as u16) << 8) | lo as u16;
                return;
            }
            0x50..=0x57 => {
                let v = self.r[d];
                self.push(v);
            }
            0x58..=0x5F => {
                let v = self.pop();
                self.r[d] = v;
            }
            0xF0..=0xF7 => {
                let v = (self.r[d] << 4) | (self.r[d] >> 4);
                self.r[d] = v;
                self.set_zs(v);
            }
            0x10 => self.r[d] = self.r[s],
            0x11 => {
                // The register-to-register add carries in, unlike the immediate form.
                let sum = self.r[d] as u16 + self.r[s] as u16 + u16::from(self.fc);
                self.fc = sum > 0xFF;
                let v = sum as u8;
                self.r[d] = v;
                self.set_zs(v);
            }
            0x12 | 0x16 => {
                let a = self.r[d];
                let b = self.r[s];
                self.fc = b > a;
                let v = a.wrapping_sub(b);
                if ins.op == 0x12 {
                    self.r[d] = v;
                }
                self.set_zs(v);
            }
            0x13 | 0x14 | 0x15 => {
                let a = self.r[d];
                let b = self.r[s];
                let v = match ins.op {
                    0x13 => a & b,
                    0x14 => a | b,
                    _ => a ^ b,
                };
                self.fc = false;
                self.r[d] = v;
                self.set_zs(v);
            }
            0x17 => {
                let p = self.r[d] as u16 * self.r[s] as u16;
                self.fc = p >> 8 != 0;
                let v = p as u8;
                self.r[d] = v;
                self.set_zs(v);
            }
            0x18 | 0x19 => {
                // The part rotates one position further than the encoded count.
                let a = self.r[d];
                let n = (ins.rs + 1) & 7;
                if n == 0 {
                    self.set_zs(a);
                } else {
                    let v = if ins.op == 0x18 {
                        self.fc = (a >> (8 - n)) & 1 == 1;
                        (a << n) | (a >> (8 - n))
                    } else {
                        self.fc = (a >> (n - 1)) & 1 == 1;
                        (a >> n) | (a << (8 - n))
                    };
                    self.r[d] = v;
                    self.set_zs(v);
                }
            }
            0x20..=0x27 => self.r[d] = imm8,
            0x70..=0x77 => {
                let sum = self.r[d] as u16 + imm8 as u16;
                self.fc = sum > 0xFF;
                let v = sum as u8;
                self.r[d] = v;
                self.set_zs(v);
            }
            0x78..=0x7F => {
                let v = self.r[d] ^ imm8;
                self.fc = false;
                self.r[d] = v;
                self.set_zs(v);
            }
            0x80..=0x87 => {
                let p = self.r[d] as u16 * imm8 as u16;
                self.fc = p >> 8 != 0;
                let v = p as u8;
                self.r[d] = v;
                self.set_zs(v);
            }
            0x88..=0x8F => {
                let a = self.r[d];
                self.fc = imm8 > a;
                let v = a.wrapping_sub(imm8);
                self.set_zs(v);
            }
            0x28..=0x2B => self.set_pair(ins.rd, ins.imm),
            0x30 | 0x31 => {
                let base = self.pair(ins.rs);
                let addr = ((base as i32 + ins.disp) & 0xFFFF) as u16;
                if ins.op == 0x30 {
                    let v = self.read8(addr);
                    self.r[d] = v;
                } else {
                    let v = self.r[d];
                    self.write8(addr, v);
                }
            }
            0x32 => {
                let v = self.read8(ins.imm);
                self.r[d] = v;
            }
            0x33 => {
                let v = self.r[d];
                self.write8(ins.imm, v);
            }
            0x34 => {
                let hi = self.read8(ins.imm);
                let lo = self.read8(ins.imm.wrapping_add(1));
                self.set_pair(ins.rd, ((hi as u16) << 8) | lo as u16);
            }
            0x35 => {
                let v = self.pair(ins.rd);
                self.write8(ins.imm, (v >> 8) as u8);
                self.write8(ins.imm.wrapping_add(1), (v & 0xFF) as u8);
            }
            0x40 => taken = true,
            0x41 => taken = self.fz,
            0x42 => taken = !self.fz,
            0x43 => taken = self.fc,
            0x44 => taken = !self.fc,
            0x45 => taken = self.fs,
            0x46 => taken = !self.fs,
            0x47 => {
                self.push((next >> 8) as u8);
                self.push((next & 0xFF) as u8);
                taken = true;
            }
            0x48 => taken = true,
            0x49 => {
                let v = self.r[d].wrapping_sub(1);
                self.r[d] = v;
                taken = v != 0;
            }
            _ => {
                self.stop = Some(Stop::Fault);
                self.stop_pc = self.pc;
                return;
            }
        }

        if self.io_touched {
            cycles += 2;
        }
        if taken && matches!(ins.op, 0x41..=0x46 | 0x49) {
            cycles += 2;
        }
        self.cycles += cycles as u64;
        self.instructions += 1;
        self.pc = if taken { ins.target } else { next };
    }

    /// "granted" / "denied" / "halted" for a machine that stopped cleanly.
    pub fn verdict(&self) -> &'static str {
        match self.stop {
            Some(Stop::Fault) => "fault",
            Some(Stop::Timeout) => "timeout",
            _ => match self.latch.last() {
                Some(0xA5) => "granted",
                Some(0x5A) => "denied",
                _ => "halted",
            },
        }
    }
}
KX_CPU_EOF

cat > /app/src/recover.rs <<'KX_RECOVER_EOF'
//! Unlock-code recovery.
//!
//! The board keeps no copy of the code and the check folds every byte's difference into one
//! accumulator before it branches, so there is nothing to search for and nothing to learn
//! from a rejected attempt. What is left is to let the board rewrite itself, read the check
//! back out of the memory it left behind, and drive its transform forwards a byte at a time:
//! the value each position has to produce is known, and only one byte produces it. Every
//! constant comes off the decoded routine, and the arithmetic is the part's, not the
//! datasheet's, which is what makes the answer come out right.

use crate::cpu::Machine;
use crate::decode::{decode, Insn};

/// The stretch of body the reset code rewrote: the check, in the clear.
fn rewritten(body: &[u8], mem: &[u8]) -> Option<(usize, usize)> {
    let start = (0..body.len()).find(|&i| mem[i] != body[i])?;
    let mut end = start;
    for i in start..body.len() {
        if mem[i] != body[i] {
            end = i + 1;
        }
    }
    Some((start, end))
}

struct Check {
    table: u16,
    length: usize,
    acc0: u8,
    mask0: u8,
    mul: u8,
    rot: u8,
    rot_left: bool,
    mask_mul: u8,
    mask_add: u8,
}

/// Read the check's constants off the decoded routine.
fn describe(code: &[Insn], mem: &[u8]) -> Option<Check> {
    // The compare phase starts where the routine points a pair at its table.
    let at = code.iter().position(|i| i.op == 0x2B)?;
    let rest = &code[at..];
    let table = rest[0].imm;

    let imm_of = |op: u8| -> Option<u8> { rest.iter().find(|i| i.op == op).map(|i| i.imm as u8) };

    let acc0 = imm_of(0x22)?; // LDI R2, #acc seed
    let mask0 = imm_of(0x23)?; // LDI R3, #mask seed
    let mul = imm_of(0x84)?; // MULI R4, #multiplier
    let mask_mul = imm_of(0x83)?; // MULI R3, #mask multiplier
    let mask_add = imm_of(0x73)?; // ADDI R3, #mask increment
    let rotate = rest.iter().find(|i| (i.op == 0x18 || i.op == 0x19) && i.rd == 4)?;

    // The loop runs until the table pointer reaches one past its last entry.
    let stop = imm_of(0x8E)? as u16;
    let length = (stop.wrapping_sub(table) & 0x00FF) as usize;
    if length == 0 || length > 64 || table as usize + length > mem.len() {
        return None;
    }
    Some(Check {
        table,
        length,
        acc0,
        mask0,
        mul,
        rot: rotate.rs,
        rot_left: rotate.op == 0x18,
        mask_mul,
        mask_add,
    })
}

/// One turn of the check's mixer, arithmetic exactly as the part performs it.
fn mix(chk: &Check, byte: u8, acc: u8, mask: u8) -> (u8, u8) {
    let product = (byte ^ acc) as u16 * chk.mul as u16;
    let t = product as u8;
    let mut carry = product >> 8 != 0;

    let n = (chk.rot + 1) & 7;
    let d = if n == 0 {
        t
    } else {
        let v = if chk.rot_left {
            carry = (t >> (8 - n)) & 1 == 1;
            (t << n) | (t >> (8 - n))
        } else {
            carry = (t >> (n - 1)) & 1 == 1;
            (t >> n) | (t << (8 - n))
        };
        v
    };

    let first = acc as u16 + d as u16 + u16::from(carry);
    let second = (first as u8) as u16 + mask as u16 + u16::from(first > 0xFF);
    (d, second as u8)
}

pub fn recover(body: &[u8]) -> Option<Vec<u8>> {
    let mut m = Machine::new(body, &[]);
    m.run();
    let mem = m.mem.clone();

    let (start, end) = rewritten(body, &mem)?;
    let mut decoded = Vec::new();
    let mut pc = start as u16;
    while (pc as usize) < end {
        let ins = decode(&mem, pc);
        pc = pc.wrapping_add(ins.len.max(1));
        decoded.push(ins);
    }

    let chk = describe(&decoded, &mem)?;

    let mut acc = chk.acc0;
    let mut mask = chk.mask0;
    let mut code = Vec::with_capacity(chk.length);
    for i in 0..chk.length {
        let want = mem[chk.table as usize + i] ^ mask;
        let mut found = None;
        for cand in 0..=255u8 {
            if mix(&chk, cand, acc, mask).0 == want {
                found = Some(cand);
                break;
            }
        }
        let byte = found?;
        let (_, next) = mix(&chk, byte, acc, mask);
        code.push(byte);
        acc = next;
        mask = mask.wrapping_mul(chk.mask_mul).wrapping_add(chk.mask_add);
    }

    let mut check = Machine::new(body, &code);
    check.run();
    if check.verdict() == "granted" {
        Some(code)
    } else {
        None
    }
}
KX_RECOVER_EOF

cat > /app/src/main.rs <<'KX_MAIN_EOF'
//! kxtool - offline workbench for KXF1 firmware images.

mod cpu;
mod decode;
mod image;
mod recover;

use cpu::Machine;
use std::process::exit;

fn fail(code: &str, detail: &str) -> ! {
    eprintln!("{{\"error\":\"{}\",\"detail\":\"{}\"}}", code, escape(detail));
    exit(2);
}

fn escape(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

struct Args {
    cmd: String,
    image: Option<String>,
    key: Vec<u8>,
    addr: u16,
    count: usize,
    live: bool,
}

fn parse_args() -> Args {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.is_empty() {
        fail("bad_argument", "usage: kxtool <disasm|run|map|recover> --image PATH [...]");
    }
    let mut a = Args {
        cmd: argv[0].clone(),
        image: None,
        key: Vec::new(),
        addr: 0,
        count: 16,
        live: false,
    };
    if !matches!(a.cmd.as_str(), "disasm" | "run" | "map" | "recover") {
        fail("bad_argument", &format!("unknown subcommand {}", a.cmd));
    }
    let mut i = 1;
    let mut saw_addr = false;
    while i < argv.len() {
        let k = argv[i].clone();
        if k == "--live" {
            a.live = true;
            i += 1;
            continue;
        }
        if i + 1 >= argv.len() {
            fail("bad_argument", &format!("option {} is missing its value", k));
        }
        let v = argv[i + 1].clone();
        match k.as_str() {
            "--image" => a.image = Some(v),
            "--key" => a.key = parse_hex(&v),
            "--addr" => {
                a.addr = parse_u16(&v);
                saw_addr = true;
            }
            "--count" => {
                let n: usize = match v.parse() {
                    Ok(n) => n,
                    Err(_) => fail("bad_argument", "count is not a number"),
                };
                if n == 0 || n > 4096 {
                    fail("bad_argument", "count must be between 1 and 4096");
                }
                a.count = n;
            }
            other => fail("bad_argument", &format!("unknown option {}", other)),
        }
        i += 2;
    }
    if a.image.is_none() {
        fail("bad_argument", "--image is required");
    }
    if a.cmd == "disasm" && !saw_addr {
        fail("bad_argument", "disasm requires --addr");
    }
    a
}

fn parse_u16(s: &str) -> u16 {
    let t = s.trim();
    let parsed = match t.strip_prefix("0x") {
        Some(hex) => u32::from_str_radix(hex, 16).ok(),
        None => t.parse::<u32>().ok(),
    };
    match parsed {
        Some(n) if n <= 0xFFFF => n as u16,
        _ => fail("bad_argument", &format!("{} is not a 16-bit address", s)),
    }
}

fn parse_hex(s: &str) -> Vec<u8> {
    let t = s.trim();
    if t.len() % 2 != 0 {
        fail("bad_argument", "key hex string has an odd number of digits");
    }
    let b = t.as_bytes();
    let mut out = Vec::new();
    for c in b.chunks(2) {
        let pair = std::str::from_utf8(c).unwrap();
        match u8::from_str_radix(pair, 16) {
            Ok(v) => out.push(v),
            Err(_) => fail("bad_argument", &format!("{} is not hexadecimal", pair)),
        }
    }
    out
}

fn hexstr(b: &[u8]) -> String {
    b.iter().map(|x| format!("{:02x}", x)).collect()
}

fn addr_list(a: &[u16]) -> String {
    let parts: Vec<String> = a.iter().map(|x| format!("\"0x{:04x}\"", x)).collect();
    format!("[{}]", parts.join(","))
}

fn main() {
    let args = parse_args();
    let path = args.image.clone().unwrap();
    let raw = match std::fs::read(&path) {
        Ok(v) => v,
        Err(e) => fail("io_error", &format!("cannot read {}: {}", path, e)),
    };
    let fw = match image::parse(&raw) {
        Ok(f) => f,
        Err((c, d)) => fail(c, &d),
    };

    match args.cmd.as_str() {
        "disasm" => {
            let mem = if args.live {
                let mut m = Machine::new(&fw.body, &[]);
                m.run();
                m.mem
            } else {
                let mut mem = vec![0u8; 0x10000];
                mem[..fw.body.len()].copy_from_slice(&fw.body);
                mem
            };
            let mut pc = args.addr as u32;
            for _ in 0..args.count {
                let ins = decode::decode(&mem, (pc & 0xFFFF) as u16);
                println!("{}", decode::line(&ins));
                pc += ins.len as u32;
                if pc > 0xFFFF {
                    pc &= 0xFFFF;
                }
            }
        }
        "run" => {
            let mut m = Machine::new(&fw.body, &args.key);
            m.run();
            let fault = if m.verdict() == "fault" { "\"illegal_instruction\"" } else { "null" };
            let latch: Vec<String> = m.latch.iter().map(|b| format!("\"0x{:02x}\"", b)).collect();
            println!(
                "{{\"status\":\"{}\",\"fault\":{},\"halt_pc\":\"0x{:04x}\",\"instructions\":{},\"cycles\":{},\"key_reads\":{},\"latch\":[{}]}}",
                m.verdict(),
                fault,
                m.stop_pc,
                m.instructions,
                m.cycles,
                m.key_pos,
                latch.join(",")
            );
        }
        "map" => {
            let mut m = Machine::new(&fw.body, &[]);
            m.run();
            let mut ranges: Vec<(usize, usize)> = Vec::new();
            let mut i = 0usize;
            while i < fw.body.len() {
                if m.mem[i] != fw.body[i] {
                    let start = i;
                    while i < fw.body.len() && m.mem[i] != fw.body[i] {
                        i += 1;
                    }
                    ranges.push((start, i));
                } else {
                    i += 1;
                }
            }
            let rs: Vec<String> = ranges
                .iter()
                .map(|(s, e)| format!("{{\"start\":\"0x{:04x}\",\"end\":\"0x{:04x}\"}}", s, e))
                .collect();
            let entry = u16::from_be_bytes([fw.body[0], fw.body[1]]);
            println!(
                "{{\"entry\":\"0x{:04x}\",\"load\":\"0x{:04x}\",\"body_len\":{},\"checksum\":\"0x{:04x}\",\"patched\":[{}],\"io_reads\":{},\"io_writes\":{},\"status\":\"{}\",\"halt_pc\":\"0x{:04x}\",\"instructions\":{},\"cycles\":{}}}",
                entry,
                fw.load,
                fw.body.len(),
                fw.checksum,
                rs.join(","),
                addr_list(&m.io_reads),
                addr_list(&m.io_writes),
                m.verdict(),
                m.stop_pc,
                m.instructions,
                m.cycles
            );
        }
        "recover" => match recover::recover(&fw.body) {
            Some(code) => {
                let printable = code.iter().all(|b| (0x20..=0x7E).contains(b));
                let text = if printable {
                    format!("\"{}\"", escape(&String::from_utf8_lossy(&code)))
                } else {
                    "null".to_string()
                };
                println!(
                    "{{\"length\":{},\"code_hex\":\"{}\",\"code_text\":{}}}",
                    code.len(),
                    hexstr(&code),
                    text
                );
            }
            None => fail("unrecoverable", "no accepted key stream could be reconstructed"),
        },
        _ => unreachable!(),
    }
}
KX_MAIN_EOF

make build

BIN=/app/bin/kxtool

# --- self-checks ---------------------------------------------------------------------
# Every check derives its expectation from the image, never from a stored answer.

for img in /app/samples/unit-4c17.fw /app/samples/unit-9a83.fw; do
    rec=$("$BIN" recover --image "$img")
    echo "recovered from $img: $rec"
    code=$(printf '%s' "$rec" | sed 's/.*"code_hex":"//; s/".*//')
    test -n "$code"

    # the recovered stream is accepted
    "$BIN" run --image "$img" --key "$code" | grep -q '"status":"granted"'

    # one byte off, one byte short and one byte long are all refused
    flipped=$(printf '%02x' $(( 0x${code:0:2} ^ 0x40 )))
    "$BIN" run --image "$img" --key "${flipped}${code:2}" | grep -q '"status":"denied"'
    "$BIN" run --image "$img" --key "${code:0:$(( ${#code} - 2 ))}" | grep -q '"status":"denied"'
    "$BIN" run --image "$img" --key "${code}41" | grep -q '"status":"denied"'

    # the body rewrites itself before the check runs: the shipped bytes at the patched
    # range do not disassemble, the live ones do
    start=$(printf '%s' "$("$BIN" map --image "$img")" | sed 's/.*"patched":\[{"start":"//; s/".*//')
    test -n "$start"
    "$BIN" disasm --image "$img" --addr "$start" --count 12 | grep -q '\.byte'
    if "$BIN" disasm --image "$img" --addr "$start" --count 12 --live | grep -q '\.byte'; then
        echo "live disassembly of $img still looks encrypted" >&2
        exit 1
    fi

    # a rejected attempt of the right length costs the same whatever it contains, so the
    # code cannot be peeled off one byte at a time
    a=$("$BIN" run --image "$img" --key "${flipped}${code:2}" | sed 's/.*"instructions"://; s/,.*//')
    b=$("$BIN" run --image "$img" --key "$(printf '00%.0s' $(seq 1 $(( ${#code} / 2 ))))" \
        | sed 's/.*"instructions"://; s/,.*//')
    if [ "$a" != "$b" ]; then
        echo "rejected attempts on $img cost different amounts ($a vs $b)" >&2
        exit 1
    fi

    # repeating the recovery gives the same answer
    test "$("$BIN" recover --image "$img")" = "$rec"
done

# the model matches the bench capture, not just the datasheet
while read -r img cycles latch; do
    case "$img" in \#*|image|'') continue ;; esac
    got=$("$BIN" run --image "/app/samples/conformance/$img")
    gotc=$(printf '%s' "$got" | sed 's/.*"cycles"://; s/,.*//')
    gotl=$(printf '%s' "$got" | sed 's/.*"latch":\[//; s/\].*//; s/"0x//g; s/"//g; s/,/ /g')
    if [ "$gotc" != "$cycles" ] || [ "$gotl" != "$latch" ]; then
        echo "conformance mismatch on $img: cycles $gotc vs $cycles, latch [$gotl] vs [$latch]" >&2
        exit 1
    fi
done < <(sed -n 's/^\([a-z-]*\.fw\) *\([0-9]*\) *\(.*\)$/\1 \2 \3/p' \
    /app/samples/conformance/rev-d-capture.txt)

# a container that does not check out is refused rather than executed
if "$BIN" map --image /app/samples/unit-corrupt.fw >/dev/null 2>&1; then
    echo "damaged container was accepted" >&2
    exit 1
fi

echo "solution complete"
