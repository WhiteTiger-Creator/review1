# Reduction format

Run records use twelve-decimal binary64 renderings separated by vertical bars
during digest construction, terminated by a semicolon. The JSON report exposes
the same values as numbers without that terminator. Records are emitted in
increasing step order. The digest hashes the concatenated canonical text in
that forward order.
