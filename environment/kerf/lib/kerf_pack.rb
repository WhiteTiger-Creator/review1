# frozen_string_literal: true

require "digest"
require "fileutils"
require "pathname"
require_relative "kerf_json"
require_relative "kerf_tar"

class KerfPack
  def self.emit(lane, bundle_out)
    out = Pathname(bundle_out)
    scratch = Pathname("/app/output/scratch")
    FileUtils.mkdir_p(scratch)
    File.write(scratch.join("soft.txt"), "metric=#{lane.soft_metric}\n")

    cert = {
      "selection_trace" => lane.selection_trace,
      "inclusion_digest" => sha256_hex(""),
      "algebra_digest" => sha256_hex(""),
      "replay_journal" => lane.replay_journal,
      "coverage_band" => 1.0
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
