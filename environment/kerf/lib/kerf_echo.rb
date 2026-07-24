# frozen_string_literal: true

module KerfEcho
  module_function

  def summarize(lane)
    $stdout.puts("lanes=#{lane.arm_decision.size}")
  end
end
