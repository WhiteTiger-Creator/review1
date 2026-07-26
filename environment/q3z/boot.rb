# frozen_string_literal: true

require "yaml"
require "digest"
require_relative "io_paths"
require_relative "phase_ix"
require_relative "phase_fl"
require_relative "phase_or"
require_relative "phase_em"
require_relative "../n4k/blob_fmt"
require_relative "../p8m/tag_util"
require_relative "../p8m/fold_diag"
require_relative "../p8m/tag_bag"
require_relative "../w2t/ord_gauge"
require_relative "../w2t/sch_thaw"
require_relative "../jr8/journal"
require_relative "../jr8/ckpt_w"
require_relative "../rp5/absorb"
require_relative "../ovk/authority"
require_relative "../r6x/emit_util"

module Q3z
  module Boot
    module_function

    def run!(argv = ARGV)
      mode, cut, resume_path, gate_first = parse_argv(argv)
      seed = File.read(IoPaths.seed_path).strip
      extra = YAML.load_file(IoPaths.extra_path)
      mx = YAML.load_file(IoPaths.mx_path)
      matrix_rows = mx.fetch("rows")
      pin_map = load_pin_map

      walk_base = resolve_walk_base(extra)
      blob = PhaseIx.load_blob
      hdr = N4k::BlobFmt.parse_hdr(blob)
      index_crc = format("%08x", N4k::BlobFmt.body_crc(blob))

      case mode
      when :full
        run_full(blob, hdr, seed, extra, matrix_rows, pin_map, walk_base, gate_first, index_crc)
      when :split_a
        run_split_a(blob, hdr, seed, extra, matrix_rows, pin_map, walk_base, gate_first, index_crc, cut)
      when :split_b
        run_split_b(blob, hdr, seed, extra, matrix_rows, pin_map, walk_base, gate_first, index_crc, resume_path)
      else
        raise "mode"
      end
      0
    end

    def parse_argv(argv)
      gate_first = !argv.include?("--sides-first")
      mode = :full
      cut = 4
      resume_path = File.join(IoPaths.out_dir, "restart.bin")
      argv.each_with_index do |a, i|
        case a
        when "--mode"
          m = argv[i + 1].to_s
          mode = m == "split_a" ? :split_a : m == "split_b" ? :split_b : :full
        when "--cut"
          cut = Integer(argv[i + 1])
        when "--resume"
          resume_path = argv[i + 1].to_s
        end
      end
      [mode, cut, resume_path, gate_first]
    end

    def resolve_walk_base(extra)
      if ENV.key?("KW_WALK_BASE") && !ENV["KW_WALK_BASE"].to_s.empty?
        Integer(ENV["KW_WALK_BASE"])
      else
        extra.fetch("training_walk_base").to_i
      end
    end

    def load_pin_map
      dir = IoPaths.overlay_dir
      Dir.children(dir).sort.each_with_object({}) do |fn, h|
        next unless fn.end_with?(".lock.yaml")
        doc = YAML.load_file(File.join(dir, fn))
        h[doc.fetch("name")] = doc.fetch("pins")
      end
    end

    def scan_by_name(blob, walk_base)
      scanned = PhaseIx.walk_all(blob, walk_base)
      scanned.each_with_object({}) { |s, h| h[s[:name]] = s if s[:name] != "" }
    end

    def activate_row(r, by_name, pin_map, resume_hit: false)
      name = r["gem_id"].to_s
      s = by_name.fetch(name)
      ov = r["overlay_ref"].to_s
      Ovk::Authority.assert_pin!(pin_map, ov, name, s[:ver], resume_hit: resume_hit)
      edge = P8m::TagUtil.edge_hex(name, s[:ver])
      {
        "gem_id" => name,
        "edge_digest" => edge,
        "platform" => r["platform"].to_s,
        "overlay_ref" => ov,
        "act_ord" => r["act_ord"].to_i,
        "opt_side" => r["opt_class"].to_s,
        "reloc_off" => s[:loff].to_i,
        "poff" => s[:poff].to_i,
        "ver" => s[:ver]
      }
    end

    def run_full(blob, hdr, seed, extra, matrix_rows, pin_map, walk_base, gate_first, index_crc)
      by_name = scan_by_name(blob, walk_base)
      annex = extra.fetch("training_annex_order")
      train_tags = annex.map do |n|
        s = by_name[n]
        s ? P8m::TagUtil.edge_hex(s[:name], s[:ver]) : ""
      end
      _ = P8m::FoldDiag.twin_ok?(train_tags, train_tags.dup)

      fold = PhaseFl.fold_edges(order_scan(PhaseIx.walk_all(blob, walk_base), annex), seed)
      unit_hex = fold[:unit]

      ordered = PhaseOr.order_rows(matrix_rows, gate_first)
      _gauge = W2t::OrdGauge.counters(ordered)

      journal = Jr8::Journal.new
      cache = P8m::TagBag.new
      rows = []
      ordered.each_with_index do |r, seq|
        row = activate_row(r, by_name, pin_map)
        cache.put(row["gem_id"], row["ver"])
        journal.push_act(row, seq)
        rows << row
      end
      journal.push_fold(rows.length)

      viol_n = count_held_out(blob, seed, extra)
      digest_u = "#{seed}|#{unit_hex}"
      ENV["KW_HELD"] = viol_n.to_s
      ENV["KW_CRC"] = index_crc
      PhaseEm.materialize(rows, digest_u)
    end

    def run_split_a(blob, hdr, seed, extra, matrix_rows, pin_map, walk_base, gate_first, index_crc, cut)
      by_name = scan_by_name(blob, walk_base)
      ordered = PhaseOr.order_rows(matrix_rows, gate_first)
      raise "cut" if cut < 1 || cut >= ordered.length

      journal = Jr8::Journal.new
      completed = []
      ordered.first(cut).each_with_index do |r, seq|
        row = activate_row(r, by_name, pin_map)
        row["bind_token"] = R6x::EmitUtil.bind_hex(row["edge_digest"], row["overlay_ref"], row["reloc_off"])
        journal.push_act(row, seq)
        completed << row
      end
      journal.push_cut(cut)
      pending_ids = ordered.drop(cut).map { |r| r["gem_id"].to_s }

      meta = {
        walk_base: walk_base,
        gate_first: gate_first,
        act_done: cut,
        seed: seed,
        index_crc: index_crc,
        rbase: hdr[:rbase]
      }
      path = File.join(IoPaths.out_dir, "restart.bin")
      Jr8::CkptW.write_restart(path, meta, completed, pending_ids, journal)
      0
    end

    def run_split_b(blob, hdr, seed, extra, matrix_rows, pin_map, walk_base, gate_first, index_crc, resume_path)
      st = Rp5::Absorb.absorb(resume_path, walk_base_override: ENV.key?("KW_WALK_BASE") && !ENV["KW_WALK_BASE"].to_s.empty? ? walk_base : nil, gate_first_cli: gate_first)

      by_name = scan_by_name(blob, st[:walk_base])
      cache = P8m::TagBag.new
      journal = Jr8::Journal.new

      completed = st[:completed].map do |r|
        cache.put(r["gem_id"], r["ver"])
        Ovk::Authority.assert_pin!(pin_map, r["overlay_ref"], r["gem_id"], r["ver"], resume_hit: true)
        journal.push_act(r, r["act_ord"])
        r
      end

      pending_ordered = W2t::SchThaw.thaw_pending(matrix_rows, st[:pending_ids], st[:frozen_gate_first], gate_first)
      # Fix act_ord on pending relative to matrix fields from thaw
      pending_rows = []
      pending_ordered.each_with_index do |r, i|
        # thaw returns matrix-shaped rows; activate against live walk
        mx = r.dup
        mx["act_ord"] = completed.length + i
        row = activate_row(mx, by_name, pin_map, resume_hit: false)
        cache.put(row["gem_id"], row["ver"])
        journal.push_act(row, row["act_ord"])
        pending_rows << row
      end

      merged = W2t::SchThaw.rebind_act_ords(completed, pending_rows)
      fold = cache.fold_cached(st[:seed], 0)
      unit_hex = fold[:unit]
      journal.push_fold(merged.length)

      viol_n = count_held_out(blob, st[:seed], extra)
      digest_u = "#{st[:seed]}|#{unit_hex}"
      ENV["KW_HELD"] = viol_n.to_s
      ENV["KW_CRC"] = st[:index_crc]
      # Emit trusts bind_token already present on completed rows.
      PhaseEm.materialize(merged, digest_u)
    end

    def order_scan(scanned, annex)
      by = scanned.each_with_object({}) { |s, h| h[s[:name]] = s if s[:name] != "" }
      annex.map { |n| by[n] }.compact
    end

    def count_held_out(blob, seed, extra)
      viol_n = 0
      train_base = extra.fetch("training_walk_base").to_i
      train_order = extra.fetch("training_annex_order")
      train_scanned = PhaseIx.walk_all(blob, train_base)
      train_fold = PhaseFl.fold_edges(order_scan(train_scanned, train_order), seed)
      base_unit = train_fold[:unit]

      Array(extra["slices"]).each do |sl|
        wb = sl.fetch("walk_base").to_i
        order = sl.fetch("annex_order")
        scanned = PhaseIx.walk_all(blob, wb)
        by_name = scanned.each_with_object({}) { |s, h| h[s[:name]] = s if s[:name] != "" }
        if order.any? { |n| by_name[n].nil? }
          viol_n += 1
          next
        end
        scanned.each do |s|
          viol_n += 1 if s[:name].to_s.empty? || s[:ver].to_s.empty?
        end
        fold = PhaseFl.fold_edges(order_scan(scanned, order), seed)
        viol_n += 1 if fold[:unit] != base_unit
      end
      viol_n
    end
  end
end
