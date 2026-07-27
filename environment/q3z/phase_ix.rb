# frozen_string_literal: true

require_relative "../n4k/scan_v"
require_relative "io_paths"

module Q3z
  module PhaseIx
    module_function

    def walk_all(blob, base_u)
      require_relative "../n4k/blob_fmt"
      hdr = N4k::BlobFmt.parse_hdr(blob)
      (0...hdr[:count]).map do |i|
        N4k::ScanV.scan_v(blob, base_u, i)
      end
    end

    def load_blob
      File.binread(IoPaths.blob_path)
    end
  end
end
