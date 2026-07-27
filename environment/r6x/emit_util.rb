# frozen_string_literal: true

require "digest"
require "json"
require "fileutils"

module R6x
  module EmitUtil
    module_function

    def bind_hex(edge, overlay_ref, reloc_off)
      Digest::SHA256.hexdigest("#{edge}|#{overlay_ref}|#{reloc_off}")[0, 12]
    end

    def write_json(path, obj)
      FileUtils.mkdir_p(File.dirname(path))
      File.write(path, JSON.pretty_generate(obj) + "\n")
    end

    def write_jsonl(path, rows)
      FileUtils.mkdir_p(File.dirname(path))
      File.open(path, "w") do |f|
        rows.each { |r| f.puts(JSON.generate(r)) }
      end
    end
  end
end
