# frozen_string_literal: true

# Diagnostic dry-run preview only; never mutates bag.
module ScanAx
  def self.preview(bag)
    return [] if bag.nil? || bag.jobs.nil?

    bag.jobs.keys.sort
  end
end
