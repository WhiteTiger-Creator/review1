# frozen_string_literal: true

require_relative "blob_fmt"

module N4k
  module ScanV
    module_function

    def scan_v(blob, base_u, slice_ix)
      hdr = BlobFmt.parse_hdr(blob)
      raise "slice" if slice_ix < 0 || slice_ix >= hdr[:count]
      rec = BlobFmt.rec_at(blob, slice_ix)
      adj = hdr[:rbase]
      probe = base_u.to_i
      file_off = if probe == adj
                   rec[:poff]
                 else
                   rec[:poff] - adj + probe
                 end
      plen = rec[:plen]
      raw = ""
      if file_off >= 0 && (file_off + plen) <= blob.bytesize
        raw = blob[file_off, plen].to_s
      end
      parts = raw.split("|", 3)
      name = parts[0].to_s
      ver = parts[1].to_s
      plat = parts[2].to_s
      loff = rec[:poff] - adj + probe
      {
        nh: rec[:nh],
        vtag: rec[:vtag],
        pbits: rec[:pbits],
        flags: rec[:flags],
        etag: rec[:etag],
        ix: rec[:ix],
        file_off: file_off,
        loff: loff,
        name: name,
        ver: ver,
        plat: plat,
        base_u: probe,
        rbase: adj,
        poff: rec[:poff]
      }
    end
  end
end
