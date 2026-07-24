# frozen_string_literal: true

require "optparse"
require "fileutils"
require "pathname"
require "briar_rivet"
require "flume_kern"
require "kerf_pack"
require "kerf_echo"

options = {}
parser = OptionParser.new do |opts|
  opts.on("--pack PATH") { |v| options[:pack] = v }
  opts.on("--db PATH") { |v| options[:db] = v }
  opts.on("--bundle-out PATH") { |v| options[:bundle_out] = v }
end
parser.parse!

pack = options[:pack]
db = options[:db]
bundle = options[:bundle_out]
raise "usage: rivet_gate --pack DIR --db FILE --bundle-out FILE" unless pack && db && bundle

db_path = Pathname(db)
seed = Pathname("/app/environment/db/shift_ledger_seed.db")
FileUtils.mkdir_p(db_path.dirname)
FileUtils.cp(seed, db_path)

batch = BriarRivet.apply(pack)
lane = FlumeKern.advance(batch, db_path, batch.max_epoch)
KerfEcho.summarize(lane)
KerfPack.emit(lane, bundle)
