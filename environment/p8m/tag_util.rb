# frozen_string_literal: true

require "digest"

module P8m
  module TagUtil
    module_function

    def edge_hex(name, ver)
      Digest::SHA256.hexdigest("edge|#{name}|#{ver}")[0, 16]
    end

    def reduce_hex(parts)
      Digest::SHA256.hexdigest(parts.join("\n"))
    end
  end
end
