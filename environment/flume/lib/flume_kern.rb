# frozen_string_literal: true

require "pathname"
require_relative "flume_lane"
require_relative "flume_db"
require_relative "flume_soft"
require "briar_types"

class FlumeKern
  MARGIN = 0.050000

  def self.advance(batch, db_path, max_epoch)
    trace = batch.selected_ids.map do |id|
      { "epoch" => 1, "probe_id" => id }
    end
    decisions = {}
    batch.probes.each { |p| decisions[p.arm] = "KEEP" }
    journal = [
      { "epoch" => 1, "fingerprint" => "FOREIGN_PACK_ZZ", "marker" => "SOFT" }
    ]
    soft = FlumeSoft.gap_metric(batch)
    Lane.new(
      batch: batch,
      selection_trace: trace,
      replay_journal: journal,
      arm_decision: decisions,
      enclosure_lines: [],
      soft_metric: soft,
      included: false
    )
  end
end
