#!/usr/bin/env bash
set -euo pipefail

# Reference delayed fire and journal warm start for /app/environment/cz/tick_cz.rb.

cat > /app/environment/cz/tick_cz.rb <<'RB_EOF'
# frozen_string_literal: true

require_relative "../qx/bank_qx"

module TickCz
  class << self
    def tick_cz(bag, slot, toks)
      return 0 if bag.nil?

      fired = 0
      pending = bag.sched.select { |s| s["slot"].to_i == slot.to_i && !s["done"] }
      pending.each do |s|
        fid = "#{s["job_id"]}#fire"
        next if bag.done_ids[fid]

        row = {
          "id" => fid,
          "kind" => "delay_fire",
          "actor" => s["actor"],
          "target" => s["target"],
          "pid" => s["job_id"],
          "slot" => slot.to_i
        }
        bag.actors[s["target"]]["hp"] -= s["dmg"].to_i
        bag.commit_row(row)
        s["done"] = true
        fired += 1
      end
      fired
    end

    def warm_cz(bag)
      return 0 unless File.file?(bag.journal_path)

      bag.load_journal!
      BankQx.reset!
      snaps = {}
      open_frames = {}
      bag.frames.each do |row|
        case row["kind"]
        when "strike"
          item = bag.jobs[row["id"]] || bag.hooks.find { |h| h["id"] == row["id"] }
          next if item.nil? || !item.key?("dmg")

          actor = item["actor"] || item["owner"]
          pid = row["pid"]
          fr = if pid && open_frames.key?(pid)
                 open_frames[pid]
               else
                 BankQx.capture_board(bag)
               end
          open_frames[row["id"]] = fr
          pos = bag.actors[actor]["pos"]
          snap = fr.fetch(pos, 0)
          BankQx.mark_value(row["id"], snap)
          snaps[row["id"]] = { "item" => item, "snap" => snap }
        when "delay_fire"
          job = bag.jobs[row["pid"]]
          next if job.nil?

          bag.actors[job["target"]]["hp"] -= job.fetch("dmg").to_i
        when "move"
          bag.actors[row["actor"]]["pos"] = bag.jobs[row["id"]]["to"]
        when "paint"
          job = bag.jobs[row["id"]] || bag.hooks.find { |h| h["id"] == row["id"] }
          next if job.nil?

          bag.tiles[job["tile"]] ||= { "mod" => 0 }
          bag.tiles[job["tile"]]["mod"] = job.fetch("mod").to_i
        when "delay"
          bag.sched << {
            "job_id" => row["id"],
            "slot" => bag.jobs[row["id"]].fetch("slot").to_i,
            "target" => row["target"],
            "dmg" => bag.jobs[row["id"]].fetch("dmg").to_i,
            "actor" => row["actor"],
            "done" => !!bag.done_ids["#{row["id"]}#fire"]
          }
        end
      end
      bag.frames.reverse_each do |row|
        next unless row["kind"] == "strike"

        meta = snaps[row["id"]]
        next if meta.nil?

        item = meta["item"]
        tgt = item["target"]
        next unless BankQx.allow?(bag, tgt)

        bag.actors[tgt]["hp"] -= (item.fetch("dmg").to_i + meta["snap"].to_i)
      end
      bag.cursor = bag.frames.count { |r| bag.jobs.key?(r["id"]) }
      bag.frames.length
    end
  end
end
RB_EOF
