# Historical policy engine for missing judgments
source("/app/environment/lib/common_io.R")

resolve_relevance_policy <- function(bundle, base_relevance, doc_ix) {
  snap_path <- sprintf("/app/environment/fixtures/interim_snaps/q2_part.json")
  if (!file.exists(snap_path)) {
    return(base_relevance)
  }
  
  snap <- jsonlite::fromJSON(snap_path)
  
  if (snap$bundle != bundle || !isTRUE(snap$headline_ok)) {
    return(base_relevance)
  }
  
  rows <- snap$residual_rows
  for (i in seq_len(nrow(rows))) {
    if (rows$row_ix[i] == doc_ix) {
      return(base_relevance * (1.0 + rows$band[i]))
    }
  }
  
  return(base_relevance)
}
