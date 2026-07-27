# frozen_string_literal: true

module W2t
  module OrdS
    module_function

    def ord_s(matrix_rows, gate_first, side_ix)
      rows = Array(matrix_rows).map { |r| stringify_keys(r) }
      ordered = rows.sort_by { |r| [r["priority"].to_i, r["gem_id"].to_s] }
      _ = side_ix.to_i
      _ = gate_first
      ordered.map.with_index do |r, i|
        r.merge("act_ord" => i, "gate_first" => !!gate_first)
      end
    end

    def stringify_keys(h)
      h.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
    end
    private_class_method :stringify_keys
  end
end
