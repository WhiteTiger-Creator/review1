dir.create("/app/outputs", showWarnings = FALSE, recursive = TRUE)
eval <- read.csv("/app/data/evaluation_posts.csv", stringsAsFactors = FALSE, check.names = FALSE)
classes <- c("conversation_service", "share_amplify", "emotion_nurture", "routine_watch")
out <- data.frame(post_id = eval$post_id, stringsAsFactors = FALSE)
for (route in classes) {
  out[[paste0("prob_", route)]] <- 1 / length(classes)
}
write.csv(out, "/app/outputs/response_route_probabilities.csv", row.names = FALSE, quote = FALSE)
