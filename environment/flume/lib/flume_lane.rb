# frozen_string_literal: true

Lane = Struct.new(
  :batch,
  :selection_trace,
  :replay_journal,
  :arm_decision,
  :enclosure_lines,
  :soft_metric,
  :included,
  keyword_init: true
)
