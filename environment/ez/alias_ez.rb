# frozen_string_literal: true

# Sample tooling labels only.
module AliasEz
  def self.labels(frames)
    Array(frames).map { |f| f["id"].to_s }
  end
end
