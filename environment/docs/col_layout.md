# Column layout for feature window tables

Feature window tables written by the annex tokenization path use the column set below.

| column | type | meaning |
|--------|------|---------|
| doc_id | string | judgment key from the bundle TSV |
| win_ix | integer | zero-based window index inside the annex span |
| tok_start | integer | cumulative token offset at window open |
| tok_count | integer | tokens counted inside the window body |
| carry_sum | numeric | running carry tally used for join alignment |
| relevance | numeric | attorney relevance label copied from the judgment table |

Carry tables mirror `doc_id`, `win_ix`, and `carry_sum` only. Join keys must match the judgment TSV `doc_id` field exactly.
