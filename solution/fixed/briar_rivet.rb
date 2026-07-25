# frozen_string_literal: true

require "digest"
require "pathname"
require_relative "briar_types"
require_relative "briar_mini_json"

class BriarRivet
  EDGES = [0.00, 0.25, 0.50, 0.75, 1.00].freeze
  BUDGET = 8

  def self.apply(pack_root)
    root = Pathname(pack_root)
    raise "pack missing" unless root.directory?

    probes = load_probes(root)
    fp = fingerprint(root)
    ids = greedy(probes)
    max_epoch = probes.map(&:epoch).max || 1
    Batch.new(fingerprint: fp, probes: probes, selected_ids: ids, max_epoch: max_epoch)
  end

  def self.load_probes(root)
    out = []
    root.children.select { |p| p.file? && p.extname == ".jsonl" }.sort.each do |path|
      last_epoch = 0
      seen = false
      path.read.each_line do |line|
        next if line.strip.empty?

        row = BriarMiniJson.parse_obj(line)
        epoch = Integer(row.fetch("epoch"))
        raise "non-increasing epoch in #{path.basename}" if seen && epoch < last_epoch

        seen = true
        last_epoch = epoch
        feats = row.fetch("feats").map { |x| Float(x) }
        out << Probe.new(
          id: row.fetch("id"),
          arm: row.fetch("arm"),
          epoch: epoch,
          unsafe: row.fetch("unsafe") == true,
          feats: feats
        )
      end
    end
    out
  end

  def self.greedy(probes)
    by_id = {}
    probes.each { |p| by_id[p.id] ||= p }
    selected = []
    limit = [BUDGET, by_id.size].min
    while selected.size < limit
      best = nil
      best_mi = -1.0
      by_id.each_key do |cand|
        next if selected.include?(cand)

        trial = selected.map { |i| by_id[i] } + [by_id[cand]]
        mi = mutual_information(trial)
        if mi > best_mi + 1e-15 || ((mi - best_mi).abs <= 1e-15 && (best.nil? || cand < best))
          best_mi = mi
          best = cand
        end
      end
      break if best.nil?

      selected << best
    end
    selected
  end

  def self.mutual_information(set)
    return 0.0 if set.empty?

    joint = Array.new(4) { [0, 0] }
    b_count = [0, 0, 0, 0]
    u_count = [0, 0]
    set.each do |p|
      b = bin_index(p.feats[0])
      u = p.unsafe ? 1 : 0
      joint[b][u] += 1
      b_count[b] += 1
      u_count[u] += 1
    end
    n = set.length.to_f
    mi = 0.0
    4.times do |b|
      2.times do |u|
        c = joint[b][u]
        next if c.zero?

        pbu = c / n
        pb = b_count[b] / n
        pu = u_count[u] / n
        mi += pbu * Math.log(pbu / (pb * pu))
      end
    end
    mi
  end

  def self.bin_index(x)
    4.times do |i|
      lo = EDGES[i]
      hi = EDGES[i + 1]
      if i < 3
        return i if x >= lo && x < hi
      elsif x >= lo && x <= hi
        return i
      end
    end
    3
  end

  def self.fingerprint(root)
    lines = []
    root.find.select(&:file?).sort_by(&:to_s).each do |path|
      rel = path.relative_path_from(root).to_s.tr("\\", "/")
      lines << "#{rel}|#{path.size}"
    end
    Digest::SHA256.hexdigest(lines.join("\n"))
  end
end
