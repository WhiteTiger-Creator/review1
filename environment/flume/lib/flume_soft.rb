# frozen_string_literal: true

require "briar_types"

module FlumeSoft
  module_function

  def gap_metric(batch)
    unsafe = batch.probes.select(&:unsafe)
    return 0.0 if unsafe.empty?

    unsafe.sum { |p| (p.feats[0] - 0.5).abs } / unsafe.length
  end
end
