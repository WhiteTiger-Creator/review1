# frozen_string_literal: true

module Q3z
  module IoPaths
    module_function

    def env_root
      ENV.fetch("KW_ROOT") { File.expand_path("..", __dir__) }
    end

    def blob_path
      File.join(env_root, "fixtures", "ix_blob.bin")
    end

    def mx_path
      File.join(env_root, "docs", "mx_rows.yaml")
    end

    def extra_path
      File.join(env_root, "data", "extra_mtx.yaml")
    end

    def seed_path
      File.join(env_root, "data", "walk_seed.txt")
    end

    def overlay_dir
      File.join(env_root, "fixtures", "overlays")
    end

    def out_dir
      ENV.fetch("KW_OUT") { "/app/output" }
    end
  end
end
