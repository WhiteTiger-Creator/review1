# frozen_string_literal: true

# Tiny JSON helper used by diagnostic tooling only.
module MiniJson
  def self.pretty(obj)
    require "json"
    JSON.pretty_generate(obj)
  end
end
