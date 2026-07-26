# frozen_string_literal: true

require "fileutils"
require_relative "ckpt_fmt"
require_relative "journal"

module Jr8
  module CkptW
    module_function

    def write_restart(path, meta, completed, pending_ids, journal)
      FileUtils.mkdir_p(File.dirname(path))
      body = String.new(encoding: Encoding::BINARY)

      body << [meta.fetch(:walk_base).to_i].pack("V")
      body << [meta.fetch(:gate_first) ? 1 : 0].pack("C")
      body << [0].pack("C")
      body << [meta.fetch(:act_done).to_i].pack("v")
      body << [completed.length].pack("v")
      body << CkptFmt.enc_str(meta.fetch(:seed))
      body << CkptFmt.enc_str(meta.fetch(:index_crc))
      body << [meta.fetch(:rbase).to_i].pack("V")

      completed.each do |r|
        snap = r.dup
        snap["reloc_off"] = r.fetch("poff").to_i
        body << CkptFmt.enc_row(snap)
      end

      body << [pending_ids.length].pack("v")
      pending_ids.each { |gid| body << CkptFmt.enc_str(gid) }

      led = journal.ledger
      body << [led.length].pack("v")
      led.each do |rec|
        body << CkptFmt.enc_led_rec(rec[:op], rec[:gem_id], rec[:seq])
      end
      weak = led.map { |r| r[:gem_id].to_s }.join("|")
      body << [Jr8::CkptFmt.fnv1a32(weak)].pack("V")

      hdr = String.new(encoding: Encoding::BINARY)
      hdr << CkptFmt::MAGIC
      hdr << [CkptFmt::VERSION].pack("v")
      hdr << [0].pack("v")
      crc = Jr8::CkptFmt.fnv1a32(body)
      hdr << [crc].pack("V")

      File.binwrite(path, hdr + body)
      path
    end
  end
end
