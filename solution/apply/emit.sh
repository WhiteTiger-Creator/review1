#!/usr/bin/env bash
set -euo pipefail

# Reference artifact emission for /app/environment/ez/emit_ez.rb.

cat > /app/environment/ez/emit_ez.rb <<'RB_EOF'
# frozen_string_literal: true

require "json"
require "digest"
require "fileutils"

module EmitEz
  class << self
    def emit_ez(frames, seeds, wave)
      out_dir = seeds["out_dir"] || "/app/output"
      FileUtils.mkdir_p(out_dir)
      rows = Array(frames).map do |f|
        {
          "id" => f["id"],
          "kind" => f["kind"],
          "actor" => f["actor"],
          "target" => f["target"],
          "pid" => f["pid"],
          "slot" => f["slot"]
        }
      end
      ids = rows.map { |r| r["id"] }
      payload = "#{wave}|#{ids.join(",")}"
      digest = Digest::SHA256.hexdigest(payload)

      actors = {}
      seeds.fetch("actors").each do |id, a|
        actors[id] = { "hp" => a["hp"], "pos" => a["pos"] }
      end
      tiles = {}
      seeds.fetch("tiles").each do |id, t|
        tiles[id] = { "mod" => t["mod"] }
      end

      File.write(File.join(out_dir, "turn_trace.json"), JSON.generate({ "wave" => wave, "rows" => rows }) + "\n")
      File.write(File.join(out_dir, "field_state.json"), JSON.generate({
        "wave" => wave,
        "actors" => actors,
        "tiles" => tiles,
        "checksum" => digest
      }) + "\n")
      digest
    end
  end
end
RB_EOF
