# frozen_string_literal: true

require_relative "../jr8/ckpt_fmt"
require_relative "led_check"

module Rp5
  module Absorb
    module_function

    def absorb(path, walk_base_override: nil, gate_first_cli: nil)
      blob = File.binread(path)
      raise "short" if blob.bytesize < 12
      magic = blob[0, 4]
      raise "magic" unless magic == Jr8::CkptFmt::MAGIC
      ver, _rsv, hdr_crc = blob[4, 8].unpack("vvV")
      raise "ver" unless ver == Jr8::CkptFmt::VERSION
      body = blob[12..] || ""
      raise "crc" unless Jr8::CkptFmt.fnv1a32(body) == hdr_crc

      off = 0
      walk_base = body[off, 4].unpack1("V"); off += 4
      gate_b = body[off, 1].unpack1("C"); off += 1
      off += 1 # pad
      act_done = body[off, 2].unpack1("v"); off += 2
      n_comp = body[off, 2].unpack1("v"); off += 2
      seed, off = Jr8::CkptFmt.dec_str(body, off)
      index_crc, off = Jr8::CkptFmt.dec_str(body, off)
      rbase = body[off, 4].unpack1("V"); off += 4

      completed = []
      n_comp.times do
        row, off = Jr8::CkptFmt.dec_row(body, off)
        completed << row
      end

      n_pend = body[off, 2].unpack1("v"); off += 2
      pending = []
      n_pend.times do
        gid, off = Jr8::CkptFmt.dec_str(body, off)
        pending << gid
      end

      n_led = body[off, 2].unpack1("v"); off += 2
      ledger = []
      n_led.times do
        op, seq = body[off, 8].unpack("V2"); off += 8
        gid, off = Jr8::CkptFmt.dec_str(body, off)
        ledger << { op: op, gem_id: gid, seq: seq }
      end
      raise "short" if off + 4 > body.bytesize
      led_raw = body[off, 4].unpack1("V"); off += 4
      led_hex = format("%08x", led_raw)

      if act_done <= 0
        raise "ledger" unless LedCheck.valid?(ledger, led_hex)
      end

      active_base = if walk_base_override
                      walk_base_override.to_i
                    else
                      walk_base.to_i
                    end

      gate_first = if gate_first_cli.nil?
                     gate_b == 1
                   else
                     gate_b == 1
                   end

      {
        walk_base: active_base,
        frozen_walk_base: walk_base.to_i,
        gate_first: gate_first,
        frozen_gate_first: gate_b == 1,
        act_done: act_done,
        seed: seed,
        index_crc: index_crc,
        rbase: rbase.to_i,
        completed: completed,
        pending_ids: pending,
        ledger: ledger,
        led_hex: led_hex
      }
    end
  end
end
