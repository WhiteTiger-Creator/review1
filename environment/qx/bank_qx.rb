# frozen_string_literal: true

module BankQx
  class << self
    def reset!
      @ledger = {}
    end

    def mark(sid, bag, actor)
      @ledger ||= {}
      @ledger[sid] = bag.tile_mod(bag.actors[actor]["pos"])
      @ledger[sid]
    end

    def take(sid, bag, actor)
      bag.tile_mod(bag.actors[actor]["pos"])
    end

    def allow?(bag, target)
      true
    end

    def capture_board(bag)
      out = {}
      bag.tiles.each { |tid, t| out[tid] = t.fetch("mod", 0).to_i }
      out
    end
  end
end
