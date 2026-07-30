# frozen_string_literal: true

module TickCz
  class << self
    def tick_cz(bag, slot, toks)
      return 0 if bag.nil?

      fired = 0
      want = slot.to_i - 1
      pending = bag.sched.select { |s| s["slot"].to_i == want && !s["done"] }
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
      bag.frames.each { |row| replay_row(bag, row) }
      bag.cursor = bag.frames.length
      bag.frames.length
    end

    def replay_row(bag, row)
      case row["kind"]
      when "strike"
        item = bag.jobs[row["id"]] || bag.hooks.find { |h| h["id"] == row["id"] }
        return if item.nil?
        return unless item.key?("dmg")

        actor = item["actor"] || item["owner"]
        base = item.fetch("dmg").to_i
        mod = bag.tile_mod(bag.actors[actor]["pos"])
        bag.actors[item["target"]]["hp"] -= (base + mod)
      when "delay_fire"
        job = bag.jobs[row["pid"]]
        return if job.nil?

        bag.actors[job["target"]]["hp"] -= job.fetch("dmg").to_i
      when "move"
        bag.actors[row["actor"]]["pos"] = bag.jobs[row["id"]]["to"]
      when "paint"
        job = bag.jobs[row["id"]] || bag.hooks.find { |h| h["id"] == row["id"] }
        return if job.nil?

        bag.tiles[job["tile"]] ||= { "mod" => 0 }
        bag.tiles[job["tile"]]["mod"] = job.fetch("mod").to_i
      when "delay"
        bag.sched << {
          "job_id" => row["id"],
          "slot" => bag.jobs[row["id"]].fetch("slot").to_i,
          "target" => row["target"],
          "dmg" => bag.jobs[row["id"]].fetch("dmg").to_i,
          "actor" => row["actor"],
          "done" => bag.done_ids["#{row["id"]}#fire"]
        }
      end
    end
  end
end
