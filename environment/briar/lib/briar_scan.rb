# frozen_string_literal: true

require "pathname"

module BriarScan
  module_function

  def list(pack_root)
    root = Pathname(pack_root)
    root.children.select(&:file?).map { |p| p.basename.to_s }.sort
  end
end
