# frozen_string_literal: true

require "json"

module BriarMiniJson
  module_function

  def parse_obj(line)
    JSON.parse(line)
  end
end
