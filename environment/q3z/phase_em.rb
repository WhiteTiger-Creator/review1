# frozen_string_literal: true

require_relative "../r6x/emit_h"
require_relative "io_paths"

module Q3z
  module PhaseEm
    module_function

    def materialize(rows, digest_u)
      R6x::EmitH.emit_h(rows, digest_u, IoPaths.out_dir)
    end
  end
end
