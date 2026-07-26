# frozen_string_literal: true

require "digest"

module Jr8
  module CkptFmt
    MAGIC = "GSJR"
    VERSION = 1
    OP_ACT = 1
    OP_CUT = 2
    OP_FOLD = 3

    module_function

    def fnv1a32(data)
      h = 0x811c9dc5
      data.bytes.each do |b|
        h ^= b
        h = (h * 0x01000193) & 0xffffffff
      end
      h
    end

    def enc_str(s)
      b = s.to_s.b
      [b.bytesize].pack("v") + b
    end

    def dec_str(blob, off)
      raise "short" if off + 2 > blob.bytesize
      n = blob[off, 2].unpack1("v")
      off += 2
      raise "short" if off + n > blob.bytesize
      [blob[off, n].to_s.force_encoding("UTF-8"), off + n]
    end

    def enc_row(r)
      buf = String.new(encoding: Encoding::BINARY)
      buf << enc_str(r.fetch("gem_id"))
      buf << enc_str(r.fetch("ver"))
      buf << enc_str(r.fetch("edge_digest"))
      buf << enc_str(r.fetch("overlay_ref"))
      buf << enc_str(r.fetch("platform"))
      buf << enc_str(r.fetch("opt_side"))
      buf << [r.fetch("act_ord").to_i].pack("V")
      buf << [r.fetch("reloc_off").to_i].pack("V")
      buf << [r.fetch("poff").to_i].pack("V")
      buf << enc_str(r.fetch("bind_token"))
      buf
    end

    def dec_row(blob, off)
      gem_id, off = dec_str(blob, off)
      ver, off = dec_str(blob, off)
      edge, off = dec_str(blob, off)
      ov, off = dec_str(blob, off)
      plat, off = dec_str(blob, off)
      side, off = dec_str(blob, off)
      raise "short" if off + 12 > blob.bytesize
      act, reloc, poff = blob[off, 12].unpack("V3")
      off += 12
      bind, off = dec_str(blob, off)
      row = {
        "gem_id" => gem_id,
        "ver" => ver,
        "edge_digest" => edge,
        "overlay_ref" => ov,
        "platform" => plat,
        "opt_side" => side,
        "act_ord" => act,
        "reloc_off" => reloc,
        "poff" => poff,
        "bind_token" => bind
      }
      [row, off]
    end

    def enc_led_rec(op, gem_id, seq)
      buf = String.new(encoding: Encoding::BINARY)
      buf << [op.to_i, seq.to_i].pack("V2")
      buf << enc_str(gem_id)
      # pad to fixed trailer hashing unit: op,seq + gem
      buf
    end

    def led_digest(records)
      canon = records.map { |r| enc_led_rec(r[:op], r[:gem_id], r[:seq]) }.join
      format("%08x", fnv1a32(canon))
    end
  end
end
