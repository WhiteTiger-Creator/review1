# frozen_string_literal: true

require "json"

module KerfJson
  module_function

  def stringify(obj)
    case obj
    when nil
      "null"
    when String
      JSON.generate(obj)
    when Numeric, TrueClass, FalseClass
      JSON.generate(obj)
    when Hash
      parts = obj.map { |k, v| "#{stringify(k.to_s)}:#{stringify(v)}" }
      "{#{parts.join(',')}}"
    when Array
      "[#{obj.map { |x| stringify(x) }.join(',')}]"
    else
      JSON.generate(obj.to_s)
    end
  end
end
