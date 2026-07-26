#!/bin/bash
set -euo pipefail

ROOT="${KW_ROOT:-/app/environment}"
cd "$ROOT"

python3 - <<'PY'
import os
from pathlib import Path
root = Path(os.environ.get("KW_ROOT", "/app/environment"))
os.chdir(root)

Path("n4k/scan_v.rb").write_text("""# frozen_string_literal: true

require_relative \"blob_fmt\"

module N4k
  module ScanV
    module_function

    def scan_v(blob, base_u, slice_ix)
      hdr = BlobFmt.parse_hdr(blob)
      raise \"slice\" if slice_ix < 0 || slice_ix >= hdr[:count]
      rec = BlobFmt.rec_at(blob, slice_ix)
      file_off = rec[:poff]
      plen = rec[:plen]
      raise \"payload\" if file_off < 0 || file_off + plen > blob.bytesize
      raw = blob[file_off, plen].to_s
      parts = raw.split(\"|\", 3)
      name = parts[0].to_s
      ver = parts[1].to_s
      plat = parts[2].to_s
      raise \"empty\" if name.empty? || ver.empty?
      loff = rec[:poff] - hdr[:rbase] + base_u.to_i
      {
        nh: rec[:nh],
        vtag: rec[:vtag],
        pbits: rec[:pbits],
        flags: rec[:flags],
        etag: rec[:etag],
        ix: rec[:ix],
        file_off: file_off,
        loff: loff,
        name: name,
        ver: ver,
        plat: plat,
        base_u: base_u.to_i,
        rbase: hdr[:rbase],
        poff: rec[:poff]
      }
    end
  end
end
""")

Path("p8m/fold_q.rb").write_text("""# frozen_string_literal: true

require \"digest\"
require_relative \"tag_util\"

module P8m
  module FoldQ
    module_function

    def fold_q(tags, prior_u, lane_ix)
      arr = Array(tags).map(&:to_s)
      sorted = arr.sort
      body = sorted.join(\"|\")
      unit = Digest::SHA256.hexdigest(\"#{prior_u}|#{lane_ix}|#{body}\")
      {
        unit: unit,
        tags: sorted,
        lane_ix: lane_ix,
        prior_u: prior_u.to_s,
        raw_count: arr.length
      }
    end
  end
end
""")

Path("p8m/tag_bag.rb").write_text("""# frozen_string_literal: true

require \"digest\"
require_relative \"tag_util\"

module P8m
  class TagBag
    def initialize
      @order = []
      @seen = {}
    end

    def put(name, ver)
      tag = TagUtil.edge_hex(name, ver)
      key = \"#{name}|#{ver}\"
      return tag if @seen[key]
      @seen[key] = true
      @order << tag
      tag
    end

    def tags
      @order.dup
    end

    def fold_cached(prior_u, lane_ix = 0)
      sorted = @order.sort
      body = sorted.join(\"|\")
      {
        unit: Digest::SHA256.hexdigest(\"#{prior_u}|#{lane_ix}|#{body}\"),
        tags: sorted,
        lane_ix: lane_ix,
        prior_u: prior_u.to_s,
        raw_count: @order.length
      }
    end
  end
end
""")

Path("w2t/ord_s.rb").write_text("""# frozen_string_literal: true

module W2t
  module OrdS
    module_function

    def ord_s(matrix_rows, gate_first, side_ix)
      rows = Array(matrix_rows).map { |r| stringify_keys(r) }
      ordered = rows.sort_by do |r|
        cls = r[\"opt_class\"].to_s
        gate_rank = if gate_first
                      cls == \"gate\" ? 0 : 1
                    else
                      cls == \"side\" ? 0 : 1
                    end
        [r[\"priority\"].to_i, gate_rank, r[\"gem_id\"].to_s]
      end
      _ = side_ix.to_i
      ordered.map.with_index do |r, i|
        r.merge(\"act_ord\" => i, \"gate_first\" => !!gate_first)
      end
    end

    def stringify_keys(h)
      h.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
    end
    private_class_method :stringify_keys
  end
end
""")

Path("w2t/sch_thaw.rb").write_text("""# frozen_string_literal: true

require_relative \"ord_s\"

module W2t
  module SchThaw
    module_function

    def thaw_pending(matrix_rows, pending_ids, frozen_gate_first, gate_first_cli)
      _ = frozen_gate_first
      want = pending_ids.map(&:to_s)
      rows = Array(matrix_rows).select { |r| want.include?(r[\"gem_id\"].to_s) }
      OrdS.ord_s(rows, gate_first_cli, 0)
    end

    def rebind_act_ords(completed, pending_ordered)
      out = []
      Array(completed).each_with_index do |r, i|
        h = r.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
        h[\"act_ord\"] = i
        out << h
      end
      Array(pending_ordered).each_with_index do |r, i|
        h = r.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
        h[\"act_ord\"] = completed.length + i
        out << h
      end
      out
    end
  end
end
""")

Path("r6x/emit_h.rb").write_text("""# frozen_string_literal: true

require \"json\"
require \"fileutils\"
require_relative \"emit_util\"

module R6x
  module EmitH
    module_function

    def emit_h(rows, digest_u, out_dir)
      FileUtils.mkdir_p(out_dir)
      dossier_path = File.join(out_dir, \"dossier.json\")
      replay_path = File.join(out_dir, \"replay.jsonl\")

      seed, unit = digest_u.to_s.split(\"|\", 2)
      out_rows = Array(rows).map do |r|
        h = r.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
        edge = h[\"edge_digest\"].to_s
        ov = h[\"overlay_ref\"].to_s
        loff = h[\"reloc_off\"].to_i
        tok = EmitUtil.bind_hex(edge, ov, loff)
        {
          \"gem_id\" => h[\"gem_id\"],
          \"edge_digest\" => edge,
          \"platform\" => h[\"platform\"],
          \"overlay_ref\" => ov,
          \"act_ord\" => h[\"act_ord\"].to_i,
          \"opt_side\" => h[\"opt_side\"],
          \"reloc_off\" => loff,
          \"bind_token\" => tok,
          \"ver\" => h[\"ver\"]
        }
      end

      crc = ENV.fetch(\"KW_CRC\") { \"00000000\" }
      held = ENV.fetch(\"KW_HELD\") { \"1\" }.to_i

      dossier = {
        \"schema\" => \"gem-shelf-dossier/v1\",
        \"walk_seed\" => seed.to_s,
        \"closure_digest\" => unit.to_s,
        \"index_crc\" => crc,
        \"rows\" => out_rows,
        \"held_out_violations\" => held
      }

      EmitUtil.write_json(dossier_path, dossier)
      EmitUtil.write_jsonl(replay_path, out_rows.map { |r|
        {
          \"phase\" => \"row\",
          \"gem_id\" => r[\"gem_id\"],
          \"edge_digest\" => r[\"edge_digest\"],
          \"act_ord\" => r[\"act_ord\"],
          \"bind_token\" => r[\"bind_token\"],
          \"overlay_ref\" => r[\"overlay_ref\"],
          \"reloc_off\" => r[\"reloc_off\"]
        }
      })

      { dossier: dossier_path, replay: replay_path, rows: out_rows.length }
    end
  end
end
""")
Path("jr8/ckpt_w.rb").write_text("""# frozen_string_literal: true

require \"fileutils\"
require_relative \"ckpt_fmt\"
require_relative \"journal\"

module Jr8
  module CkptW
    module_function

    def write_restart(path, meta, completed, pending_ids, journal)
      FileUtils.mkdir_p(File.dirname(path))
      body = String.new(encoding: Encoding::BINARY)

      body << [meta.fetch(:walk_base).to_i].pack(\"V\")
      body << [meta.fetch(:gate_first) ? 1 : 0].pack(\"C\")
      body << [0].pack(\"C\")
      body << [meta.fetch(:act_done).to_i].pack(\"v\")
      body << [completed.length].pack(\"v\")
      body << CkptFmt.enc_str(meta.fetch(:seed))
      body << CkptFmt.enc_str(meta.fetch(:index_crc))
      body << [meta.fetch(:rbase).to_i].pack(\"V\")

      completed.each do |r|
        snap = r.dup
        # Persist logical reloc under the checkpoint walk base.
        snap[\"reloc_off\"] = r.fetch(\"reloc_off\").to_i
        body << CkptFmt.enc_row(snap)
      end

      body << [pending_ids.length].pack(\"v\")
      pending_ids.each { |gid| body << CkptFmt.enc_str(gid) }

      led = journal.ledger
      body << [led.length].pack(\"v\")
      led.each do |rec|
        body << CkptFmt.enc_led_rec(rec[:op], rec[:gem_id], rec[:seq])
      end
      dig = Jr8::CkptFmt.led_digest(led)
      body << [dig.to_i(16)].pack(\"V\")

      hdr = String.new(encoding: Encoding::BINARY)
      hdr << CkptFmt::MAGIC
      hdr << [CkptFmt::VERSION].pack(\"v\")
      hdr << [0].pack(\"v\")
      crc = Jr8::CkptFmt.fnv1a32(body)
      hdr << [crc].pack(\"V\")

      File.binwrite(path, hdr + body)
      path
    end
  end
end
""")

Path("rp5/absorb.rb").write_text("""# frozen_string_literal: true

require_relative \"../jr8/ckpt_fmt\"
require_relative \"../r6x/emit_util\"
require_relative \"led_check\"

module Rp5
  module Absorb
    module_function

    def absorb(path, walk_base_override: nil, gate_first_cli: nil)
      blob = File.binread(path)
      raise \"short\" if blob.bytesize < 12
      magic = blob[0, 4]
      raise \"magic\" unless magic == Jr8::CkptFmt::MAGIC
      ver, _rsv, hdr_crc = blob[4, 8].unpack(\"vvV\")
      raise \"ver\" unless ver == Jr8::CkptFmt::VERSION
      body = blob[12..] || \"\"
      raise \"crc\" unless Jr8::CkptFmt.fnv1a32(body) == hdr_crc

      off = 0
      walk_base = body[off, 4].unpack1(\"V\"); off += 4
      gate_b = body[off, 1].unpack1(\"C\"); off += 1
      off += 1
      act_done = body[off, 2].unpack1(\"v\"); off += 2
      n_comp = body[off, 2].unpack1(\"v\"); off += 2
      seed, off = Jr8::CkptFmt.dec_str(body, off)
      index_crc, off = Jr8::CkptFmt.dec_str(body, off)
      rbase = body[off, 4].unpack1(\"V\"); off += 4

      completed = []
      n_comp.times do
        row, off = Jr8::CkptFmt.dec_row(body, off)
        completed << row
      end

      n_pend = body[off, 2].unpack1(\"v\"); off += 2
      pending = []
      n_pend.times do
        gid, off = Jr8::CkptFmt.dec_str(body, off)
        pending << gid
      end

      n_led = body[off, 2].unpack1(\"v\"); off += 2
      ledger = []
      n_led.times do
        op, seq = body[off, 8].unpack(\"V2\"); off += 8
        gid, off = Jr8::CkptFmt.dec_str(body, off)
        ledger << { op: op, gem_id: gid, seq: seq }
      end
      raise \"short\" if off + 4 > body.bytesize
      led_raw = body[off, 4].unpack1(\"V\")
      led_hex = format(\"%08x\", led_raw)
      raise \"ledger\" unless LedCheck.valid?(ledger, led_hex)

      active_base = if walk_base_override
                      walk_base_override.to_i
                    else
                      walk_base.to_i
                    end

      completed = completed.map do |r|
        h = r.dup
        poff = h[\"poff\"].to_i
        h[\"reloc_off\"] = poff - rbase.to_i + active_base
        h[\"bind_token\"] = R6x::EmitUtil.bind_hex(h[\"edge_digest\"], h[\"overlay_ref\"], h[\"reloc_off\"])
        h
      end

      gate_first = if gate_first_cli.nil?
                     gate_b == 1
                   else
                     !!gate_first_cli
                   end

      {
        walk_base: active_base,
        frozen_walk_base: walk_base.to_i,
        gate_first: gate_first,
        frozen_gate_first: gate_b == 1,
        act_done: act_done,
        seed: seed,
        index_crc: index_crc,
        rbase: rbase.to_i,
        completed: completed,
        pending_ids: pending,
        ledger: ledger,
        led_hex: led_hex
      }
    end
  end
end
""")

Path("ovk/authority.rb").write_text("""# frozen_string_literal: true

module Ovk
  module Authority
    module_function

    def assert_pin!(pin_map, overlay_ref, gem_id, ver, resume_hit: false)
      _ = resume_hit
      pins = pin_map.fetch(overlay_ref.to_s)
      pinned = pins.fetch(gem_id.to_s)
      raise \"pin\" unless pinned.to_s == ver.to_s
      true
    end
  end
end
""")

print("patched journal-recovery frontier")
PY

chmod +x "$ROOT/tools/kw_run"
export KW_ROOT="$ROOT"
export KW_OUT="${KW_OUT:-/app/output}"
mkdir -p "$KW_OUT"
"$ROOT/tools/kw_run"
