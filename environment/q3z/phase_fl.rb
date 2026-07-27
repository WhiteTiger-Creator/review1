# frozen_string_literal: true

require_relative "../p8m/fold_q"
require_relative "../p8m/tag_util"

module Q3z
  module PhaseFl
    module_function

    def fold_edges(scanned, prior_u)
      tags = scanned.map { |s| P8m::TagUtil.edge_hex(s[:name], s[:ver]) }
      P8m::FoldQ.fold_q(tags, prior_u, 0)
    end
  end
end
