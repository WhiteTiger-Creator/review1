# frozen_string_literal: true

require_relative "blob_fmt"

module N4k
  module ScanHelp
    module_function

    def dump_hdr(blob)
      hdr = BlobFmt.parse_hdr(blob)
      lines = []
      lines << "ver=#{hdr[:ver]} count=#{hdr[:count]} rbase=#{hdr[:rbase]} crc=#{hdr[:crc].to_s(16)}"
      hdr[:count].times do |i|
        r = BlobFmt.rec_at(blob, i)
        lines << "ix=#{i} nh=#{r[:nh].to_s(16)} poff=#{r[:poff]} plen=#{r[:plen]}"
      end
      lines.join("\n")
    end
  end
end
