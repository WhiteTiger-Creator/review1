# frozen_string_literal: true

module Jr8
  class Journal
    attr_reader :entries, :ledger

    def initialize
      @entries = []
      @ledger = []
    end

    def push_act(row, seq)
      @entries << row
      @ledger << { op: CkptFmt::OP_ACT, gem_id: row["gem_id"].to_s, seq: seq.to_i }
    end

    def push_cut(seq)
      @ledger << { op: CkptFmt::OP_CUT, gem_id: "", seq: seq.to_i }
    end

    def push_fold(seq)
      @ledger << { op: CkptFmt::OP_FOLD, gem_id: "", seq: seq.to_i }
    end
  end
end
