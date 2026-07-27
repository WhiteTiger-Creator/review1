# frozen_string_literal: true

module W2t
  module OrdGauge
    module_function

    def counters(rows)
      gates = 0
      sides = 0
      Array(rows).each do |r|
        cls = (r["opt_class"] || r[:opt_class]).to_s
        if cls == "gate"
          gates += 1
        else
          sides += 1
        end
      end
      { gates: gates, sides: sides, total: gates + sides }
    end
  end
end
