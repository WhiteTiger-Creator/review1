# frozen_string_literal: true

require "digest"

module P8m
  module FoldDiag
    module_function

    # Local twin check used during offline diagnostics on the first annex.
    def twin_ok?(tags_a, tags_b)
      Digest::SHA256.hexdigest(Array(tags_a).join(",")) ==
        Digest::SHA256.hexdigest(Array(tags_b).join(","))
    end

    def coalesce(tags)
      Array(tags).each_with_object({}) { |t, h| h[t.to_s] = true }.keys
    end

    def fold_encounter(tags, prior_u, lane_ix = 0)
      arr = Array(tags).map(&:to_s)
      body = arr.join("|")
      {
        unit: Digest::SHA256.hexdigest("#{prior_u}|#{lane_ix}|#{body}"),
        tags: arr.sort,
        lane_ix: lane_ix,
        prior_u: prior_u.to_s
      }
    end
  end
end
