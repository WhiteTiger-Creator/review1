# frozen_string_literal: true

require_relative "../w2t/ord_s"

module Q3z
  module PhaseOr
    module_function

    def order_rows(matrix_rows, gate_first)
      W2t::OrdS.ord_s(matrix_rows, gate_first, 0)
    end
  end
end
