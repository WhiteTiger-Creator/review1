# frozen_string_literal: true

# Debug dump of schedule slots; non-mutating.
module ProbeCz
  def self.sample(bag)
    return [] if bag.nil? || bag.sched.nil?

    bag.sched.map { |s| s["slot"] }
  end
end
