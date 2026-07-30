# frozen_string_literal: true

# Sibling-batch drain used by the shipping loom. Looks nested at depth 1.

module DrainQx
  class << self
    def push(queue, items)
      queue.concat(Array(items))
      queue.length
    end

    def flush(bag, queue, depth)
      n = 0
      while (item = queue.shift)
        n += emit_one(bag, item, nil, depth)
      end
      n
    end

    def emit_one(bag, item, pid, depth)
      return 0 if item.nil?
      return 0 if bag.done_ids[item["id"]]
      return 0 if item["void"] == true && depth <= 0

      kind = item["kind"]
      actor = item["actor"] || item["owner"]
      target = item.key?("target") ? item["target"] : nil
      row = {
        "id" => item["id"],
        "kind" => kind,
        "actor" => actor,
        "target" => target,
        "pid" => pid,
        "slot" => bag.cursor
      }
      bag.commit_row(row)
      n = 1
      if kind == "strike" && item.key?("dmg")
        base = item.fetch("dmg").to_i
        mod = bag.tile_mod(bag.actors[actor]["pos"])
        bag.actors[target]["hp"] -= (base + mod) if target
        if depth > 0
          nested = bag.hooks.select do |h|
            h["when"] == "on_strike" && h["vs"] == target && !bag.done_ids[h["id"]]
          end
          nested.each { |hk| n += emit_one(bag, hk, item["id"], depth - 1) }
        end
      elsif kind == "paint"
        bag.tiles[item["tile"]] ||= { "mod" => 0 }
        bag.tiles[item["tile"]]["mod"] = item.fetch("mod").to_i
      elsif kind == "move"
        bag.actors[actor]["pos"] = item["to"]
      end
      n
    end
  end
end
