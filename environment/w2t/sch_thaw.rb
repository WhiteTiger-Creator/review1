# frozen_string_literal: true

require_relative "ord_s"

module W2t
  module SchThaw
    module_function

        def thaw_pending(matrix_rows, pending_ids, frozen_gate_first, gate_first_cli)
      _ = gate_first_cli
      want = pending_ids.map(&:to_s)
      rows = Array(matrix_rows).select { |r| want.include?(r["gem_id"].to_s) }
      OrdS.ord_s(rows, frozen_gate_first, 0)
    end

    def rebind_act_ords(completed, pending_ordered)
            out = []
      Array(completed).each { |r| out << r }
      Array(pending_ordered).each_with_index do |r, i|
        h = r.each_with_object({}) { |(k, v), o| o[k.to_s] = v }
        h["act_ord"] = completed.length + i
        out << h
      end
      out
    end
  end
end
