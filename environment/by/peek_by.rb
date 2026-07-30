# frozen_string_literal: true

# Diagnostic counter; never mutates bag.
module PeekBy
  def self.count_hooks(bag)
    return 0 if bag.nil? || bag.hooks.nil?

    bag.hooks.length
  end
end
