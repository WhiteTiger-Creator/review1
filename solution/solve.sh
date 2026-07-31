#!/bin/bash
set -euo pipefail

mkdir -p /app/bin
cat > /app/bin/lattice-calibrate <<'RB'
#!/usr/bin/env ruby
require "digest"
require "fileutils"
require "json"

APP = "/app"
CONFIG = "#{APP}/data/lattice_config.json"
OBS = "#{APP}/data/observations.json"
VALID = "#{APP}/data/validation_cases.json"
SCORING = "#{APP}/data/scoring_cases.json"
OUT_DIR = "#{APP}/out"
JSON_OUT = "#{OUT_DIR}/calibration.json"
TSV_OUT = "#{OUT_DIR}/current_model.tsv"

def load_json(path)
  JSON.parse(File.read(path))
end

def fail_run(message)
  warn message
  exit 2
end

def validate_levels!(rows, severity_index, recency_index, kind)
  rows.each do |row|
    fail_run("#{kind} has unknown severity") unless severity_index.key?(row["severity"])
    fail_run("#{kind} has unknown recency") unless recency_index.key?(row["recency"])
  end
end

def rate(block, alpha)
  denom = block[:trials] + 2.0 * alpha * block[:cells].length
  return 0.5 if denom.zero?
  (block[:events] + alpha * block[:cells].length) / denom
end

def fit_surface(severity, recency, observations, alpha)
  cells = {}
  severity.each do |sev|
    recency.each do |rec|
      cells[[sev, rec]] = {events: 0, trials: 0}
    end
  end
  observations.each do |row|
    key = [row["severity"], row["recency"]]
    cells[key][:events] += row["events"].to_i
    cells[key][:trials] += row["trials"].to_i
  end

  block_for = {}
  blocks = []
  cells.each do |key, counts|
    block = {cells: [key], events: counts[:events], trials: counts[:trials]}
    blocks << block
    block_for[key] = block
  end

  loop do
    changed = false
    severity.each_with_index do |sev, si|
      recency.each_with_index do |rec, ri|
        [[severity[si + 1], rec], [sev, recency[ri + 1]]].each do |neighbor|
          next if neighbor[0].nil? || neighbor[1].nil?
          left = block_for[[sev, rec]]
          right = block_for[neighbor]
          next if left.equal?(right)
          next unless rate(left, alpha) > rate(right, alpha)
          merged = {
            cells: (left[:cells] + right[:cells]).sort_by { |cell| [severity.index(cell[0]), recency.index(cell[1])] },
            events: left[:events] + right[:events],
            trials: left[:trials] + right[:trials]
          }
          left[:cells].each { |cell| block_for[cell] = merged }
          right[:cells].each { |cell| block_for[cell] = merged }
          blocks.delete(left)
          blocks.delete(right)
          blocks << merged
          changed = true
        end
      end
    end
    break unless changed
  end

  probabilities = {}
  cells.each_key do |key|
    probabilities[key] = rate(block_for[key], alpha)
  end
  [cells, probabilities]
end

def validation_nll(probabilities, validation)
  validation.sum do |row|
    p = [[probabilities[[row["severity"], row["recency"]]], 1e-15].max, 1.0 - 1e-15].min
    label = row["label"].to_i
    weight = row.fetch("weight", 1).to_f
    weight * -(label * Math.log(p) + (1 - label) * Math.log(1.0 - p))
  end
end

def clipped(prob)
  [[prob, 1e-15].max, 1.0 - 1e-15].min
end

def logit(prob)
  safe = clipped(prob)
  Math.log(safe / (1.0 - safe))
end

def sigmoid(value)
  1.0 / (1.0 + Math.exp(-value))
end

def shrink_surface(probabilities, observations, alpha, shrinkage)
  total_events = observations.sum { |row| row["events"].to_i }
  total_trials = observations.sum { |row| row["trials"].to_i }
  denom = total_trials + 2.0 * alpha
  base = denom.zero? ? 0.5 : (total_events + alpha) / denom
  base_logit = logit(base)
  probabilities.transform_values do |prob|
    sigmoid((1.0 - shrinkage) * logit(prob) + shrinkage * base_logit)
  end
end

def fit_calibrator(probabilities, validation)
  blocks = validation.sort_by { |row| [probabilities[[row["severity"], row["recency"]]], row["case_id"]] }.map do |row|
    raw = probabilities[[row["severity"], row["recency"]]]
    weight = row.fetch("weight", 1).to_f
    {
      min_raw: raw,
      max_raw: raw,
      weight: weight,
      weighted_events: weight * row["label"].to_i
    }
  end
  index = 0
  while index < blocks.length - 1
    current_rate = blocks[index][:weighted_events] / blocks[index][:weight]
    next_rate = blocks[index + 1][:weighted_events] / blocks[index + 1][:weight]
    if current_rate > next_rate
      merged = {
        min_raw: [blocks[index][:min_raw], blocks[index + 1][:min_raw]].min,
        max_raw: [blocks[index][:max_raw], blocks[index + 1][:max_raw]].max,
        weight: blocks[index][:weight] + blocks[index + 1][:weight],
        weighted_events: blocks[index][:weighted_events] + blocks[index + 1][:weighted_events]
      }
      blocks[index, 2] = [merged]
      index = [index - 1, 0].max
    else
      index += 1
    end
  end
  blocks
end

def calibrate_probability(probability, blocks)
  return probability if blocks.empty?
  blocks.each do |block|
    return block[:weighted_events] / block[:weight] if probability <= block[:max_raw]
  end
  blocks[-1][:weighted_events] / blocks[-1][:weight]
end

def calibrate_surface(probabilities, blocks)
  probabilities.transform_values { |prob| calibrate_probability(prob, blocks) }
end

def decision(prob, thresholds)
  return "alert" if prob >= thresholds["alert"].to_f
  return "monitor" if prob >= thresholds["monitor"].to_f
  "clear"
end

config = load_json(CONFIG)
observations = load_json(OBS)
validation = load_json(VALID)
scoring = load_json(SCORING)

severity = config["severity"]
recency = config["recency"]
severity_index = severity.each_with_index.to_h
recency_index = recency.each_with_index.to_h
thresholds = config["decision_thresholds"]

fail_run("severity must be nonempty") if severity.empty?
fail_run("recency must be nonempty") if recency.empty?
fail_run("bad thresholds") unless thresholds["monitor"].to_f < thresholds["alert"].to_f
fail_run("candidate_shrinkage must be nonempty") if config["candidate_shrinkage"].nil? || config["candidate_shrinkage"].empty?
validate_levels!(observations, severity_index, recency_index, "observations")
validate_levels!(validation, severity_index, recency_index, "validation")
validate_levels!(scoring, severity_index, recency_index, "scoring")

observations.each do |row|
  events = row["events"]
  trials = row["trials"]
  fail_run("observation counts must be integers") unless events.is_a?(Integer) && trials.is_a?(Integer)
  fail_run("observation counts are invalid") if events.negative? || trials.negative? || events > trials
end
validation.each do |row|
  fail_run("validation label invalid") unless [0, 1].include?(row["label"])
  fail_run("validation weight invalid") if row.fetch("weight", 1).to_f <= 0
end
config["candidate_shrinkage"].each do |shrinkage|
  fail_run("candidate shrinkage invalid") if shrinkage.to_f.negative? || shrinkage.to_f > 1.0
end

fits = config["candidate_alpha"].flat_map do |alpha|
  alpha = alpha.to_f
  _cells, probabilities = fit_surface(severity, recency, observations, alpha)
  config["candidate_shrinkage"].map do |shrinkage|
    shrinkage = shrinkage.to_f
    shrunk = shrink_surface(probabilities, observations, alpha, shrinkage)
    blocks = fit_calibrator(shrunk, validation)
    calibrated = calibrate_surface(shrunk, blocks)
    {
      alpha: alpha,
      shrinkage: shrinkage,
      probabilities: calibrated,
      calibration_blocks: blocks,
      raw_validation_nll: validation_nll(shrunk, validation),
      calibrated_validation_nll: validation_nll(calibrated, validation)
    }
  end
end
best = fits.min_by { |fit| [fit[:calibrated_validation_nll], fit[:alpha], fit[:shrinkage]] }
cells, pooled = fit_surface(severity, recency, observations, best[:alpha])
shrunk = shrink_surface(pooled, observations, best[:alpha], best[:shrinkage])
probabilities = calibrate_surface(shrunk, best[:calibration_blocks])

input_bytes = [CONFIG, OBS, VALID, SCORING].map { |path| File.binread(path) }.join

report = {
  "schema_version" => "monotone-lattice/v1",
  "generated_at" => "2026-07-28T00:00:00Z",
  "selected_alpha" => best[:alpha].round(6),
  "selected_shrinkage" => best[:shrinkage].round(6),
  "validation_nll" => best[:calibrated_validation_nll].round(6),
  "levels" => {"severity" => severity, "recency" => recency},
  "candidate_scores" => fits.sort_by { |fit| [fit[:alpha], fit[:shrinkage]] }.map do |fit|
    {
      "alpha" => fit[:alpha].round(6),
      "shrinkage" => fit[:shrinkage].round(6),
      "raw_validation_nll" => fit[:raw_validation_nll].round(6),
      "calibrated_validation_nll" => fit[:calibrated_validation_nll].round(6)
    }
  end,
  "calibration_blocks" => best[:calibration_blocks].map do |block|
    {
      "min_raw_probability" => block[:min_raw].round(6),
      "max_raw_probability" => block[:max_raw].round(6),
      "calibrated_probability" => (block[:weighted_events] / block[:weight]).round(6),
      "weight" => block[:weight].round(6)
    }
  end,
  "cells" => severity.flat_map do |sev|
    recency.map do |rec|
      key = [sev, rec]
      {
        "severity" => sev,
        "recency" => rec,
        "events" => cells[key][:events],
        "trials" => cells[key][:trials],
        "probability" => probabilities[key].round(6)
      }
    end
  end,
  "scoring" => scoring.sort_by { |row| row["case_id"] }.map do |row|
    p = probabilities[[row["severity"], row["recency"]]].round(6)
    {
      "case_id" => row["case_id"],
      "severity" => row["severity"],
      "recency" => row["recency"],
      "probability" => p,
      "decision" => decision(p, thresholds)
    }
  end,
  "input_sha256" => Digest::SHA256.hexdigest(input_bytes)
}

FileUtils.mkdir_p(OUT_DIR)
tmp_json = "#{JSON_OUT}.tmp"
tmp_tsv = "#{TSV_OUT}.tmp"
File.write(tmp_json, JSON.pretty_generate(report) + "\n")
tsv_lines = ["severity\trecency\tprobability\tdecision"]
report["cells"].each do |cell|
  prob = cell["probability"]
  tsv_lines << [cell["severity"], cell["recency"], format("%.6f", prob), decision(prob, thresholds)].join("\t")
end
File.write(tmp_tsv, tsv_lines.join("\n") + "\n")
FileUtils.mv(tmp_json, JSON_OUT)
FileUtils.mv(tmp_tsv, TSV_OUT)
RB
chmod +x /app/bin/lattice-calibrate

/app/bin/lattice-calibrate
