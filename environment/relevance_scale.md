# Relevance grading scale

Human judges grade a document against a query on a five point scale. The same scale is
used by the evaluation set that ranking models are scored against.

| Grade | Label | Meaning |
|-------|-------|---------|
| 0 | Off topic | The document does not address the query. |
| 1 | Marginal | The document mentions the topic but does not satisfy the intent. |
| 2 | Fair | The document partially satisfies the intent. |
| 3 | Good | The document satisfies the intent. |
| 4 | Excellent | The document fully and authoritatively satisfies the intent. |

Judgements are expensive, so only a held out sample of queries is judged, and those
judgements are kept separate from the interaction logs. Clicks in the logs are not
relevance grades: a click records that a user acted on a shown result, which depends on
whether the user looked at that slot at all as well as on how good the document was.
