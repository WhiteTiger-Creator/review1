# frozen_string_literal: true

module N4k
  module BlobFmt
    MAGIC = "GIX1"
    HDR = 16
    REC = 32

    module_function

    def parse_hdr(blob)
      raise "short" if blob.bytesize < HDR
      magic = blob[0, 4]
      raise "magic" unless magic == MAGIC
      ver, count, rbase, crc = blob[4, 12].unpack("v2V2")
      { ver: ver, count: count, rbase: rbase, crc: crc }
    end

    def rec_at(blob, ix)
      off = HDR + ix * REC
      raise "oob" if off + REC > blob.bytesize
      nh, vtag, pbits, poff, plen, flags, etag, _rsv = blob[off, REC].unpack("VvvVvvVV")
      {
        nh: nh, vtag: vtag, pbits: pbits, poff: poff, plen: plen,
        flags: flags, etag: etag, ix: ix
      }
    end

    def body_crc(blob)
      require "zlib"
      Zlib.crc32(blob[HDR..-1] || "") & 0xffffffff
    end
  end
end
