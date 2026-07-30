# frozen_string_literal: true

require "json"
require "fileutils"

class WorkBag
  attr_accessor :wave, :tiles, :actors, :jobs, :hooks
  attr_accessor :seq, :frames, :sched, :done_ids, :cursor
  attr_accessor :out_dir, :journal_path, :resume

  def initialize
    @wave = 0
    @tiles = {}
    @actors = {}
    @jobs = {}
    @hooks = []
    @seq = []
    @frames = []
    @sched = []
    @done_ids = {}
    @cursor = 0
    @out_dir = "/app/output"
    @journal_path = "/app/environment/data/.warm/journal.jsonl"
    @resume = false
  end

  def self.load_file(path)
    raw = JSON.parse(File.read(path))
    bag = new
    bag.wave = raw.fetch("wave").to_i
    raw.fetch("tiles").each do |k, v|
      bag.tiles[k] = { "mod" => v.fetch("mod").to_i }
    end
    raw.fetch("actors").each do |a|
      bag.actors[a.fetch("id")] = {
        "id" => a.fetch("id"),
        "init" => a.fetch("init").to_i,
        "hp" => a.fetch("hp").to_i,
        "pos" => a.fetch("pos"),
        "side" => a.fetch("side")
      }
    end
    raw.fetch("jobs").each do |j|
      bag.jobs[j.fetch("id")] = j.dup
    end
    bag.hooks = raw.fetch("hooks").map(&:dup)
    bag
  end

  def actor_rank(aid)
    a = @actors[aid]
    [-a["init"], a["id"]]
  end

  def tile_mod(pos)
    t = @tiles[pos]
    t ? t["mod"].to_i : 0
  end

  def commit_row(row)
    return if @done_ids[row["id"]]

    @frames << row
    @done_ids[row["id"]] = true
    FileUtils.mkdir_p(File.dirname(@journal_path))
    File.open(@journal_path, "a") { |fh| fh.puts(JSON.generate(row)) }
  end

  def load_journal!
    return unless File.file?(@journal_path)

    File.readlines(@journal_path).each do |line|
      line = line.strip
      next if line.empty?

      row = JSON.parse(line)
      @frames << row
      @done_ids[row["id"]] = true
    end
  end
end
