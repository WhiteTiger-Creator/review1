# frozen_string_literal: true

require "digest"
require "pathname"
require_relative "briar_types"
require_relative "briar_mini_json"

class BriarRivet
  def self.apply(pack_root)
    root = Pathname(pack_root)
    raise "pack missing" unless root.directory?

    probes = load_probes(root)
    fp = fingerprint(root)
    ids = probes.map(&:id).sort.uniq.take(8)
    smoke = probes.select { |p| p.arm == "smoke" }.map(&:id).sort.uniq.take(8)
    ids = smoke unless smoke.empty?
    max_epoch = probes.map(&:epoch).max || 1
    Batch.new(fingerprint: fp, probes: probes, selected_ids: ids, max_epoch: max_epoch)
  end

  def self.load_probes(root)
    out = []
    root.children.select { |p| p.file? && p.extname == ".jsonl" }.sort.each do |path|
      last_epoch = 0
      path.read.each_line do |line|
        next if line.strip.empty?

        row = BriarMiniJson.parse_obj(line)
        epoch = Integer(row.fetch("epoch"))
        next if epoch < last_epoch

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

  def self.fingerprint(root)
    lines = []
    root.find.select(&:file?).sort_by(&:to_s).each do |path|
      rel = path.relative_path_from(root).to_s.tr("\\", "/")
      lines << "#{rel}|#{path.size}"
    end
    Digest::SHA256.hexdigest(lines.join("\n"))
  end
end
