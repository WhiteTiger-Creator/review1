Create /app/outputs/choice_predictions.csv with exactly these columns in this order:

event_id,item_id,probability

Every pair in evaluation_candidates.csv must appear exactly once, with no extra pairs. probability must parse as a finite number in the closed interval from zero to one. Probabilities must sum to one within each event_id to absolute tolerance 1e-8. Row order is unrestricted.
