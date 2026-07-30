#!/usr/bin/env bash
set -euo pipefail

# Reference open-strike ledger for /app/environment/qx/bank_qx.rb.

cat > /app/environment/qx/bank_qx.rb <<'RB_EOF'
# frozen_string_literal: true

module BankQx
  class << self
    def reset!
      @ledger = {}
    end

    def mark_value(sid, value)
      @ledger ||= {}
      @ledger[sid] = value.to_i
      @ledger[sid]
    end

    def mark(sid, bag, actor)
      mark_value(sid, bag.tile_mod(bag.actors[actor]["pos"]))
    end

    def take(sid, bag, actor)
      @ledger ||= {}
      return @ledger[sid] if @ledger.key?(sid)

      bag.tile_mod(bag.actors[actor]["pos"])
    end

    def allow?(bag, target)
      bag.actors[target]["hp"] > 0
    end

    def capture_board(bag)
      out = {}
      bag.tiles.each { |tid, t| out[tid] = t.fetch("mod", 0).to_i }
      out
    end
  end
end
RB_EOF
