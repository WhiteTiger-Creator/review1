# frozen_string_literal: true

require "json"
require "fileutils"
require_relative "emit_util"

module R6x
  module EmitH
    module_function

    def emit_h(rows, digest_u, out_dir)
      FileUtils.mkdir_p(out_dir)
      dossier_path = File.join(out_dir, "dossier.json")
      replay_path = File.join(out_dir, "replay.jsonl")

      seed, unit = digest_u.to_s.split("|", 2)
      out_rows = Array(rows).map do |r|
        h = r.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
        edge = h["edge_digest"].to_s
        ov = h["overlay_ref"].to_s
        if h["bind_token"].to_s.empty?
          h["bind_token"] = EmitUtil.bind_hex(edge, ov, 0)
        end
        canon_row(h)
      end

      dossier = {
        "schema" => "gem-shelf-dossier/v1",
        "walk_seed" => seed.to_s,
        "closure_digest" => unit.to_s,
        "index_crc" => "00000000",
        "rows" => out_rows,
        "held_out_violations" => out_rows.length
      }

      EmitUtil.write_json(dossier_path, dossier)
      EmitUtil.write_jsonl(replay_path, out_rows.map { |r|
        {
          "phase" => "row",
          "gem_id" => r["gem_id"],
          "edge_digest" => r["edge_digest"],
          "act_ord" => r["act_ord"],
          "bind_token" => r["bind_token"],
          "overlay_ref" => r["overlay_ref"],
          "reloc_off" => r["reloc_off"]
        }
      })

      { dossier: dossier_path, replay: replay_path, rows: out_rows.length }
    end

    def canon_row(h)
      {
        "gem_id" => h["gem_id"],
        "edge_digest" => h["edge_digest"],
        "platform" => h["platform"],
        "overlay_ref" => h["overlay_ref"],
        "act_ord" => h["act_ord"].to_i,
        "opt_side" => h["opt_side"],
        "reloc_off" => h["reloc_off"].to_i,
        "bind_token" => h["bind_token"],
        "ver" => h["ver"]
      }
    end
    private_class_method :canon_row
  end
end
