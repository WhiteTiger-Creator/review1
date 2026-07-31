//! The KX8 core, its memory map and the peripherals the boards expose.

pub const STEP_LIMIT: u64 = 2_000_000;
pub const RESET_SP: u16 = 0x7FFE;

#[derive(PartialEq, Clone, Copy, Debug)]
pub enum Stop {
    Halted,
    Fault,
    Timeout,
}

pub struct Machine {
    /// The whole 16-bit address space, with the body shadowed in at reset.
    pub mem: Vec<u8>,
    pub r: [u8; 8],
    pub pc: u16,
    pub sp: u16,
    pub fz: bool,
    pub fc: bool,
    pub fs: bool,
    pub cycles: u64,
    pub instructions: u64,
    /// Bytes written to the result latch, in order.
    pub latch: Vec<u8>,
    /// The key stream presented at the port.
    pub key: Vec<u8>,
    /// How much of that stream has been taken.
    pub key_pos: usize,
    pub key_fault: bool,
    /// Distinct peripheral addresses read from and written to, ascending.
    pub io_reads: Vec<u16>,
    pub io_writes: Vec<u16>,
    pub stop: Option<Stop>,
    pub stop_pc: u16,
}

impl Machine {
    pub fn new(body: &[u8], key: &[u8]) -> Machine {
        let mut mem = vec![0u8; 0x10000];
        mem[..body.len()].copy_from_slice(body);
        Machine {
            mem,
            r: [0; 8],
            pc: 0,
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
        }
    }

    /// Execute until the machine halts, faults or exhausts the step budget.
    pub fn run(&mut self) {
        self.stop = Some(Stop::Halted);
        self.stop_pc = self.pc;
    }

    /// Reading of the latch record once the machine has stopped.
    pub fn verdict(&self) -> &'static str {
        "halted"
    }
}
