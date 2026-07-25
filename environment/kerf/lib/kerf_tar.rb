# frozen_string_literal: true

class KerfTar
  def initialize(path)
    @path = path
    @io = File.open(path, "wb")
  end

  def add(name, data)
    header = "\0" * 512
    name_bytes = name.b[0, 100]
    header = name_bytes + header[name_bytes.bytesize..]
    mode = "0000644"
    header = header[0, 100] + mode + header[107..]
    uid = "0000000"
    header = header[0, 108] + uid + header[115..]
    header = header[0, 116] + uid + header[123..]
    size = format("%011o", data.bytesize)
    header = header[0, 124] + size + header[135..]
    mtime = format("%011o", 0)
    header = header[0, 136] + mtime + header[147..]
    header = header[0, 148] + (" " * 8) + header[156..]
    header = header[0, 156] + "0" + header[157..]
    header = header[0, 257] + "ustar\0" + header[263..]
    header = header[0, 263] + "00" + header[265..]
    sum = header.bytes.sum
    chk = format("%06o\0 ", sum)
    header = header[0, 148] + chk + header[156..]
    @io.write(header[0, 512])
    @io.write(data)
    pad = (512 - (data.bytesize % 512)) % 512
    @io.write("\0" * pad) if pad.positive?
  end

  def close
    @io.write("\0" * 1024)
    @io.close
  end
end
