# frozen_string_literal: true

require "digest"
require_relative "tag_util"

module P8m
  class TagBag
    def initialize
      @order = []
      @seen = {}
    end

    def put(name, ver)
      tag = TagUtil.edge_hex(name, ver)
      key = "#{name}|#{ver}"
      return tag if @seen[key]
      @seen[key] = true
      @order << tag
      tag
    end

    def tags
      @order.dup
    end

    def fold_cached(prior_u, lane_ix = 0)
      body = @order.join("|")
      {
        unit: Digest::SHA256.hexdigest("#{prior_u}|#{lane_ix}|#{body}"),
        tags: @order.sort,
        lane_ix: lane_ix,
        prior_u: prior_u.to_s,
        raw_count: @order.length
      }
    end
  end
end
