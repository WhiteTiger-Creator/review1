# frozen_string_literal: true

require_relative "../qx/loom_qx"

module FoldBy
  class << self
    def fold_by(bag, depth, toks, resume: false)
      LoomQx.run(bag, depth, toks, resume: resume)
    end
  end
end
