# frozen_string_literal: true

Probe = Struct.new(:id, :arm, :epoch, :unsafe, :feats, keyword_init: true)
Batch = Struct.new(:fingerprint, :probes, :selected_ids, :max_epoch, keyword_init: true)
