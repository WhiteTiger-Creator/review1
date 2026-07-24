CREATE TABLE image_features(
  frame_id TEXT PRIMARY KEY,
  edge_density REAL NOT NULL,
  skin_ratio REAL NOT NULL,
  text_ratio REAL NOT NULL,
  label INTEGER NOT NULL CHECK(label IN (0,1))
);
CREATE TABLE trusted_signers(
  signer_id TEXT PRIMARY KEY,
  public_key_sha256 TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('trusted','revoked'))
);
