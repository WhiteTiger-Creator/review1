# frozen_string_literal: true

require "digest"
require_relative "tag_util"

module P8m
  module FoldQ
    module_function

    def fold_q(tags, prior_u, lane_ix)
      arr = Array(tags).map(&:to_s)
      sorted = arr.sort
      body = arr.join("|")
      unit = Digest::SHA256.hexdigest("#{prior_u}|#{lane_ix}|#{body}")
      {
        unit: unit,
        tags: sorted,
        lane_ix: lane_ix,
        prior_u: prior_u.to_s,
        raw_count: arr.length
      }
    end
  end
end
