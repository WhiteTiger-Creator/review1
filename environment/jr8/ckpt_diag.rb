# frozen_string_literal: true

require_relative "ckpt_fmt"

module Jr8
  module CkptDiag
    module_function

    def summarize(path)
      blob = File.binread(path)
      return "short" if blob.bytesize < 12
      magic = blob[0, 4]
      ver = blob[4, 2].unpack1("v")
      "magic=#{magic} ver=#{ver} bytes=#{blob.bytesize}"
    end
  end
end
