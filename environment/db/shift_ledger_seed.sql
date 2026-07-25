PRAGMA journal_mode=DELETE;
CREATE TABLE IF NOT EXISTS replay_journal (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL,
  epoch INTEGER NOT NULL,
  marker TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fixture_catalog (
  pack_file TEXT PRIMARY KEY,
  source_id TEXT NOT NULL
);
INSERT INTO replay_journal(fingerprint, epoch, marker) VALUES ('FOREIGN_PACK_ZZ', 99, 'STALE');
INSERT INTO fixture_catalog(pack_file, source_id) VALUES ('asm_01.jsonl', 'SRC-025-A');
INSERT INTO fixture_catalog(pack_file, source_id) VALUES ('asm_02.jsonl', 'SRC-025-B');
INSERT INTO fixture_catalog(pack_file, source_id) VALUES ('asm_03.jsonl', 'SRC-025-C');
INSERT INTO fixture_catalog(pack_file, source_id) VALUES ('asm_04.jsonl', 'SRC-025-D');
INSERT INTO fixture_catalog(pack_file, source_id) VALUES ('asm_05.jsonl', 'SRC-025-E');
