# frozen_string_literal: true

require "open3"

module FlumeDb
  module_function

  def exec(db_path, sql)
    out, err, st = Open3.capture3("sqlite3", db_path.to_s, sql)
    raise err unless st.success?

    out
  end
end
