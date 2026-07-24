# frozen_string_literal: true

require "digest"
require "fileutils"
require "pathname"
require_relative "kerf_json"
require_relative "kerf_tar"

class KerfPack
  def self.emit(lane, bundle_out)
    raise "illegal configuration: emit without INCLUDE" unless lane.included

    out = Pathname(bundle_out)
    scratch = Pathname("/app/output/scratch")
    FileUtils.mkdir_p(scratch)
    File.write(scratch.join("soft.txt"), "metric=#{lane.soft_metric}\n")

    enc = lane.enclosure_lines.sort
    inclusion_digest = sha256_hex(enc.join("\n"))

    algebra_lines = lane.arm_decision.sort.map { |arm, d| "#{arm}|#{d}" }
    algebra_digest = sha256_hex(algebra_lines.join("\n"))

    keep = lane.arm_decision.values.count("KEEP")
    coverage = lane.arm_decision.empty? ? 0.0 : (keep.to_f / lane.arm_decision.size)
    coverage = (coverage * 1_000_000).round / 1_000_000.0

    cert = {
      "selection_trace" => lane.selection_trace,
      "inclusion_digest" => inclusion_digest,
      "algebra_digest" => algebra_digest,
      "replay_journal" => lane.replay_journal,
      "coverage_band" => coverage
    }
    write_bundle(out, cert)
  end

  def self.write_bundle(out, cert)
    cert_bytes = KerfJson.stringify(cert).b
    man_no_self = { "certificate.json" => sha256_bytes(cert_bytes) }
    man_no_self_bytes = KerfJson.stringify(man_no_self).b
    man_final = {
      "certificate.json" => sha256_bytes(cert_bytes),
      "manifest.json" => sha256_bytes(man_no_self_bytes)
    }
    man_bytes = KerfJson.stringify(man_final).b
    FileUtils.mkdir_p(out.dirname)
    tw = KerfTar.new(out)
    tw.add("certificate.json", cert_bytes)
    tw.add("manifest.json", man_bytes)
    tw.close
  end

  def self.sha256_hex(text)
    sha256_bytes(text.b)
  end

  def self.sha256_bytes(data)
    Digest::SHA256.hexdigest(data)
  end
end
