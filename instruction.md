Train an offline context-dependent multinomial choice model on semi-synthetic retail logs whose contexts and candidate attributes come from the Open Bandit Dataset. Each historical event identifies the chosen product and its probability under the behavior logger. Later evaluation events retain their context and ten-product candidate set but conceal the choice.

Use only the relations under /app/data, documented under /app/docs. Correct logger exposure with reciprocal propensities capped at ten. Product and event identifiers are opaque: predictions must generalize through disclosed user, item, campaign, position, and candidate-set features, including evaluation products not previously chosen. Verification may consistently rename opaque keys and reorder relation rows.

Write /app/outputs/choice_predictions.csv with exactly event_id, item_id, probability. Include every evaluation event-item pair once and no other pair. Within each event, probabilities must be finite, nonnegative, and sum to one.

Quality is measured on later concealed choices using weighted log loss, reciprocal rank, and recall among the three highest-probability candidates, both overall and separately by campaign, logger, and capped versus uncapped exposure. Cold-start quality is also evaluated after replacing evaluation-only product identifiers while preserving their features.

The offline R entrypoint /app/run.sh accepts optional input and output directories.
