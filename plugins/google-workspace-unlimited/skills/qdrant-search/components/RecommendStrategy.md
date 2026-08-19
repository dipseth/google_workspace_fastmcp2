# RecommendStrategy

**Symbol:** `R_10`

## Description

How to use positive and negative examples to find the results, default is `average_vector`:  * `average_vector` - Average positive and negative vectors and create a single query with the formula `query = avg_pos + avg_pos - avg_neg`. Then performs normal search.  * `best_score` - Uses custom search objective. Each candidate is compared against all examples, its score is then chosen from the `max(max_pos_score, max_neg_score)`. If the `max_neg_score` is chosen then it is squared and negated, otherwise it is just the `max_pos_score`.  * `sum_scores` - Uses custom search objective. Compares against all inputs, sums all the scores. Scores against positive vectors are added, against negatives are subtracted.
