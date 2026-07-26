# Grouped evaluation contract

This is the contract for the collection-site audit used by the model validation team. A site is a holdout group: every labeled row from one site is evaluated by a model trained only on labeled rows from the other sites.

## Command

```
/app/bin/weka-cv-audit \
  --data INPUT.arff \
  --class CLASS_ATTRIBUTE \
  --id ID_ATTRIBUTE \
  --group GROUP_ATTRIBUTE \
  --top K \
  --out REPORT.json
```

The six options are required, may appear in any order, and may not be repeated. Attribute names are case-sensitive. `--help` prints the usage line and exits 0. Bad command syntax exits 2; its first stderr line must be `error: <message>`, followed by the usage line. A data or evaluation error exits 1, writes `error: <message>` to stderr, and leaves no report at the requested output path. A successful run exits 0 and replaces that report.

`--top` must parse as an integer. After the dataset schema is known, `K` must satisfy `1 <= K <=` the number of numeric predictors. Values outside that range are data/evaluation errors.

The implementation must use the Weka library already supplied in `/app/lib` to load the ARFF file. No network access or additional dependencies are available.

The command-line diagnostics are part of the interface. Use `six option-value pairs are required` when the argument count is empty or odd, `unknown option: <option>`, `duplicate option: <option>`, `empty value for <option>`, and `missing option: <option>` for the corresponding syntax errors. A non-integer K uses `invalid value for --top: must be an integer`. For retained data, a repeated id must produce exactly `error: id values must be unique`.

## Accepted data

Rows with a missing class value are discarded first and have no effect on validation, folds, statistics, or the report. The remaining data must meet these rules:

- The class, id, and group attributes exist and are three different attributes.
- Class is nominal. Its labels and their order come from the ARFF declaration.
- Id and group are string or nominal attributes. Every retained row has a nonempty id and group, and ids are unique.
- Every other attribute is numeric, and there is at least one such predictor. Missing predictor values are allowed.
- At least two class labels and two distinct groups occur in retained rows.
- For each held-out group, its training partition contains at least one row of every declared class.

Declared class labels with no retained row therefore make the data invalid. Nominal group values that do not occur are not folds.

## Fold preprocessing, feature selection, and model

Distinct group values are ordered with Java's natural `String` ordering. For each value in that order, its rows are the test partition and all other retained rows are the training partition.

Preprocessing is fitted separately for every fold and uses only its training partition. For predictor \(j\):

1. Compute the mean of the nonmissing training values. Use `0.0` if every training value is missing.
2. Replace missing training and test values with that training mean.
3. Compute the population standard deviation of the imputed training values: the square root of the sum of squared deviations divided by the number of training rows. Use scale `1.0` when this standard deviation is zero.
4. Standardize training and test values as `(value - mean) / scale`.

Feature selection is also fold-local and uses only that fold's training partition after the steps above. For each numeric predictor, compute a Fisher score from the standardized training values:

- Let the global mean be the mean over all training rows for that predictor.
- For each declared class, let the class mean be the mean over training rows of that class.
- `between = sum_c n_c * (classMean_c - globalMean)^2`, where `n_c` is the number of training rows in class `c`.
- `within = sum over training rows (x - classMean_of_row's_class)^2`.
- `score = between / within`. If `within = 0` and `between > 0`, the score is positive infinity. If both are zero, the score is `0.0`.

Select exactly `K` predictors with the highest scores. Exact score ties break by ascending original ARFF attribute index. The resulting ranking order is the order of `selectedFeatures` in the report.

The nearest-centroid model for a fold uses only the selected predictors. For each class, store the component-wise mean of its standardized training rows across those predictors. A test row's distance to a class is the sum of squared differences from that centroid, restricted to the selected dimensions. Let `minimum` be the smallest class distance. The class score is:

```
exp(-(distance - minimum))
```

Divide each score by the sum of all class scores to obtain class probabilities. The predicted class is the one with the greatest probability; an exact tie goes to the earlier class in the ARFF declaration. Prediction confidence is the predicted class probability.

## Metrics

The confusion matrix uses actual classes as rows and predicted classes as columns, both in ARFF declaration order.

`accuracy` is correct predictions divided by all predictions. For each declared class, compute precision and recall from the confusion matrix. A zero denominator gives `0.0`. That class's F1 is `0.0` when precision plus recall is zero; otherwise it is their harmonic mean. `macroF1` is the unweighted mean of every declared class's F1.

`logLoss` is the mean of `-log(max(probability of the actual class, 1e-15))` over all predictions, using the natural logarithm. A fold's accuracy follows the same accuracy definition but includes only that group's test rows.

All decimal values in the JSON report are rounded to six places with decimal `HALF_UP` rounding and are written with exactly six digits after the decimal point.

## Report

The report is one UTF-8 JSON object with these keys:

```
{
  "dataset": "basename of INPUT.arff",
  "instances": 12,
  "classAttribute": "species",
  "classes": ["setosa", "versicolor"],
  "folds": [
    {
      "group": "lab-a",
      "train": 8,
      "test": 4,
      "accuracy": 0.750000,
      "selectedFeatures": ["petal_length", "sepal_width"]
    }
  ],
  "metrics": {
    "accuracy": 0.750000,
    "macroF1": 0.733333,
    "logLoss": 0.481234
  },
  "confusion": [[3, 1], [2, 6]],
  "predictions": [
    {
      "id": "sample-001",
      "group": "lab-a",
      "actual": "setosa",
      "predicted": "setosa",
      "confidence": 0.812345
    }
  ]
}
```

`folds` is in the group order defined above. Each fold object includes `selectedFeatures`, the ranked predictor names chosen for that fold. `predictions` contains one entry for every retained row and is ordered by id using Java's natural `String` ordering. JSON strings must be escaped normally. The report must be deterministic for the same input and arguments.
