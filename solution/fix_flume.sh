#!/usr/bin/env bash
set -euo pipefail
cat > /app/environment/flume/lib/flume_kern.rb <<'RUBY'
# frozen_string_literal: true

require "pathname"
require_relative "flume_lane"
require_relative "flume_db"
require_relative "flume_soft"
require "briar_types"

class FlumeKern
  MARGIN = 0.050000

  def self.advance(batch, db_path, max_epoch)
    db = Pathname(db_path)
    FlumeDb.exec(db, "DELETE FROM replay_journal")

    by_id = {}
    batch.probes.each { |p| by_id[p.id] ||= p }

    trace = batch.selected_ids.map do |id|
      p = by_id[id]
      { "epoch" => p.epoch, "probe_id" => id }
    end

    selected_unsafe = batch.selected_ids.map { |id| by_id[id] }.select(&:unsafe)

    lo = [1.0, 1.0, 1.0]
    hi = [0.0, 0.0, 0.0]
    unless selected_unsafe.empty?
      lo = [1.0, 1.0, 1.0]
      hi = [0.0, 0.0, 0.0]
      selected_unsafe.each do |p|
        3.times do |i|
          lo[i] = [lo[i], p.feats[i]].min
          hi[i] = [hi[i], p.feats[i]].max
        end
      end
      3.times do |i|
        lo[i] = clamp(lo[i] - MARGIN)
        hi[i] = clamp(hi[i] + MARGIN)
      end
    end

    enclosure = selected_unsafe.map do |p|
      format(
        "%s|%.6f,%.6f,%.6f|%.6f,%.6f,%.6f",
        p.id, lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]
      )
    end.sort

    arms = batch.probes.map(&:arm).uniq.sort
    decisions = {}
    arms.each do |arm|
      keep = true
      batch.probes.each do |p|
        next unless p.arm == arm && p.unsafe

        if selected_unsafe.empty? || !inside?(p.feats, lo, hi)
          keep = false
          break
        end
      end
      decisions[arm] = keep ? "KEEP" : "REJECT"
    end

    epochs = [max_epoch, 1].max
    journal = []
    1.upto(epochs) do |e|
      marker = "E#{e}"
      esc_fp = batch.fingerprint.gsub("'", "''")
      FlumeDb.exec(db, "INSERT INTO replay_journal(fingerprint, epoch, marker) VALUES ('#{esc_fp}', #{e}, '#{marker}')")
      journal << { "epoch" => e, "fingerprint" => batch.fingerprint, "marker" => marker }
    end

    soft = FlumeSoft.gap_metric(batch)
    Lane.new(
      batch: batch,
      selection_trace: trace,
      replay_journal: journal,
      arm_decision: decisions,
      enclosure_lines: enclosure,
      soft_metric: soft,
      included: true
    )
  end

  def self.inside?(feats, lo, hi)
    3.times.all? { |i| feats[i] >= lo[i] && feats[i] <= hi[i] }
  end

  def self.clamp(v)
    return 0.0 if v < 0.0
    return 1.0 if v > 1.0

    v
  end
end
RUBY
