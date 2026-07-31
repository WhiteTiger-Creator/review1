//! KX8 instruction decoding and disassembly text.
//!
//! `decode` looks at the 64 KiB memory image and describes the instruction that begins at
//! `addr`; `line` renders that description the way the contract prints it.

#[derive(Clone)]
pub struct Insn {
    /// Address the instruction begins at.
    pub addr: u16,
    /// Total length in bytes, prefix included.
    pub len: u16,
    /// Base cost, before the timing additions the datasheet lists.
    pub cycles: u32,
    /// Primary opcode, that is, the byte after any prefix.
    pub op: u8,
    /// Set when the instruction carries the wide prefix.
    pub wide: bool,
    /// First operand field: destination register, or pair for the word forms.
    pub rd: u8,
    /// Second operand field: source register, pair or rotate count.
    pub rs: u8,
    /// Immediate or absolute address.
    pub imm: u16,
    /// Signed displacement of an indexed or relative form.
    pub disp: i32,
    /// Resolved target of a transfer of control.
    pub target: u16,
    /// Set when the bytes at `addr` do not form a legal instruction.
    pub illegal: bool,
    /// The instruction's own bytes.
    pub bytes: Vec<u8>,
}

pub fn decode(mem: &[u8], addr: u16) -> Insn {
    Insn {
        addr,
        len: 1,
        cycles: 0,
        op: mem[addr as usize],
        wide: false,
        rd: 0,
        rs: 0,
        imm: 0,
        disp: 0,
        target: 0,
        illegal: true,
        bytes: vec![mem[addr as usize]],
    }
}

pub fn line(ins: &Insn) -> String {
    let _ = ins;
    String::new()
}
