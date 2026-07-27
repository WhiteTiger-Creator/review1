# frozen_string_literal: true

module Ovk
  module Authority
    module_function

    def assert_pin!(pin_map, overlay_ref, gem_id, ver, resume_hit: false)
      if resume_hit
        return true
      end
      pins = pin_map.fetch(overlay_ref.to_s)
      pinned = pins.fetch(gem_id.to_s)
      raise "pin" unless pinned.to_s == ver.to_s
      true
    end
  end
end
