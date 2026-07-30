# frozen_string_literal: true

module LoomQx
  class << self
    def run(bag, depth, toks, resume: false)
      require_relative "bank_qx"
      require_relative "drain_qx"
      require_relative "../cz/tick_cz"

      BankQx.reset!
      if resume && File.file?(bag.journal_path)
        TickCz.warm_cz(bag)
      end

      pending = []
      while bag.cursor < bag.seq.length
        jid = bag.seq[bag.cursor]
        item = lookup(bag, jid)
        emit_flat(bag, item, nil, pending) unless item.nil? || bag.done_ids[jid]
        TickCz.tick_cz(bag, bag.cursor, toks)
        bag.cursor += 1
      end
      DrainQx.flush(bag, pending, depth)
      bag.frames.length
    end

    def lookup(bag, id)
      return bag.jobs[id] if bag.jobs.key?(id)

      bag.hooks.find { |h| h["id"] == id }
    end

    def emit_flat(bag, item, pid, pending)
      return if item.nil?
      return if bag.done_ids[item["id"]]

      kind = item["kind"]
      actor = item["actor"] || item["owner"]
      target = item.key?("target") ? item["target"] : nil
      slot = bag.cursor
      row = {
        "id" => item["id"],
        "kind" => kind,
        "actor" => actor,
        "target" => target,
        "pid" => pid,
        "slot" => slot
      }
      bag.commit_row(row)

      if kind == "strike"
        BankQx.mark(item["id"], bag, actor)
        apply_strike(bag, item)
        DrainQx.push(pending, eligible_hooks(bag, target))
      elsif kind == "delay"
        bag.sched << {
          "job_id" => item["id"],
          "slot" => item.fetch("slot").to_i,
          "target" => target,
          "dmg" => item.fetch("dmg").to_i,
          "actor" => actor
        }
      elsif kind == "move"
        bag.actors[actor]["pos"] = item["to"]
      elsif kind == "paint"
        tile = item["tile"]
        bag.tiles[tile] ||= { "mod" => 0 }
        bag.tiles[tile]["mod"] = item.fetch("mod").to_i
      end
    end

    def eligible_hooks(bag, vs)
      bag.hooks.select do |h|
        h["when"] == "on_strike" && h["vs"] == vs && !bag.done_ids[h["id"]]
      end.sort_by do |h|
        own = bag.actors[h["owner"]]
        [-own["init"], own["id"], h["id"]]
      end
    end

    def apply_strike(bag, item)
      target = item["target"]
      actor = item["actor"] || item["owner"]
      base = item.fetch("dmg").to_i
      mod = BankQx.take(item["id"], bag, actor)
      return unless BankQx.allow?(bag, target)

      bag.actors[target]["hp"] -= (base + mod)
    end
  end
end
