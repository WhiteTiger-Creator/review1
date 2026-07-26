# frozen_string_literal: true

require_relative "../jr8/ckpt_fmt"

module Rp5
  module LedCheck
    module_function

    def valid?(records, digest_hex)
      expect = Jr8::CkptFmt.led_digest(records)
      expect == digest_hex.to_s.downcase
    end
  end
end
