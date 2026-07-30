# frozen_string_literal: true

require_relative "work_bag"
require_relative "../../ax/step_ax"
require_relative "../../by/fold_by"

module PassAb
  def self.run(bag, wave, resume: false)
    StepAx.step_ax(bag, wave, 1)
    FoldBy.fold_by(bag, 0, [1, 2, 3], resume: resume)
  end
end
