#!/usr/bin/env bash
set -euo pipefail

# Reference initiative ranking for /app/environment/ax/step_ax.rb.

cat > /app/environment/ax/step_ax.rb <<'RB_EOF'
# frozen_string_literal: true

module StepAx
  class << self
    def step_ax(bag, wave, tag)
      return 0 if bag.nil?

      ranked = bag.jobs.values.reject { |j| j["void"] == true }
      ranked = ranked.sort_by do |j|
        a = bag.actors[j["actor"]]
        [-a["init"], a["id"], j["id"]]
      end
      bag.seq = ranked.map { |j| j["id"] }
      bag.cursor = 0
      bag.seq.length
    end
  end
end
RB_EOF
