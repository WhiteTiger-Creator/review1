#!/usr/bin/env bash
set -euo pipefail

# Reference resolve loom for /app/environment/qx/loom_qx.rb.

cat > /app/environment/qx/loom_qx.rb <<'RB_EOF'
# frozen_string_literal: true

require_relative "bank_qx"
require_relative "../cz/tick_cz"

module LoomQx
  class << self
    def run(bag, depth, toks, resume: false)
      BankQx.reset!
      if resume && File.file?(bag.journal_path)
        TickCz.warm_cz(bag)
      end

      while bag.cursor < bag.seq.length
        jid = bag.seq[bag.cursor]
        resolve_item(bag, lookup(bag, jid), nil, nil) unless bag.done_ids[jid]
        TickCz.tick_cz(bag, bag.cursor, toks)
        bag.cursor += 1
      end
      bag.frames.length
    end

    def lookup(bag, id)
      return bag.jobs[id] if bag.jobs.key?(id)

      bag.hooks.find { |h| h["id"] == id }
    end

    def resolve_item(bag, item, pid, frame)
      return if item.nil?
      return if item["void"] == true
      return if bag.done_ids[item["id"]]

      kind = item["kind"]
      actor = item["actor"] || item["owner"]
      target = item.key?("target") ? item["target"] : nil
      slot = bag.cursor

      if kind == "strike"
        fr = frame || BankQx.capture_board(bag)
        pos = bag.actors[actor]["pos"]
        BankQx.mark_value(item["id"], fr.fetch(pos, 0))
        row = {
          "id" => item["id"],
          "kind" => kind,
          "actor" => actor,
          "target" => target,
          "pid" => pid,
          "slot" => slot
        }
        bag.commit_row(row)
        eligible_hooks(bag, target).each do |hk|
          resolve_item(bag, hk, item["id"], fr)
        end
        apply_strike(bag, item)
      elsif kind == "delay"
        row = {
          "id" => item["id"],
          "kind" => kind,
          "actor" => actor,
          "target" => target,
          "pid" => pid,
          "slot" => slot
        }
        bag.commit_row(row)
        bag.sched << {
          "job_id" => item["id"],
          "slot" => item.fetch("slot").to_i,
          "target" => target,
          "dmg" => item.fetch("dmg").to_i,
          "actor" => actor
        }
      elsif kind == "move"
        row = {
          "id" => item["id"],
          "kind" => kind,
          "actor" => actor,
          "target" => target,
          "pid" => pid,
          "slot" => slot
        }
        bag.commit_row(row)
        bag.actors[actor]["pos"] = item["to"]
      elsif kind == "paint"
        row = {
          "id" => item["id"],
          "kind" => kind,
          "actor" => actor,
          "target" => target,
          "pid" => pid,
          "slot" => slot
        }
        bag.commit_row(row)
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
      return unless BankQx.allow?(bag, target)

      base = item.fetch("dmg").to_i
      mod = BankQx.take(item["id"], bag, actor)
      bag.actors[target]["hp"] -= (base + mod)
    end
  end
end
RB_EOF
