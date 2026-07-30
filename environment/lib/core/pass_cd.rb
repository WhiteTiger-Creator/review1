# frozen_string_literal: true

require_relative "../../ez/emit_ez"

module PassCd
  class << self
    def run(bag)
      seeds = {
        "out_dir" => bag.out_dir,
        "actors" => bag.actors,
        "tiles" => bag.tiles
      }
      EmitEz.emit_ez(bag.frames, seeds, bag.wave)
    end
  end
end
