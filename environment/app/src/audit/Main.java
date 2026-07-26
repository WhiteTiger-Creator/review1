package audit;

import java.io.IOException;
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import weka.core.Attribute;
import weka.core.Instance;
import weka.core.Instances;
import weka.core.converters.ConverterUtils.DataSource;

public final class Main {
    private static final String USAGE =
            "usage: /app/bin/weka-cv-audit --data INPUT.arff --class NAME "
                    + "--id NAME --group NAME --top K --out REPORT.json";

    public static void main(String[] args) {
        int status = run(args);
        if (status != 0) {
            System.exit(status);
        }
    }

    private static int run(String[] args) {
        if (args.length == 1 && "--help".equals(args[0])) {
            System.out.println(USAGE);
            return 0;
        }

        Config config;
        try {
            config = parseArgs(args);
        } catch (UsageException error) {
            System.err.println("error: " + error.getMessage());
            System.err.println(USAGE);
            return 2;
        }

        try {
            Files.deleteIfExists(config.output());
            Dataset dataset = load(config);
            if (config.topK() < 1 || config.topK() > dataset.predictors().length) {
                throw new IllegalArgumentException(
                        "--top must be between 1 and the number of numeric predictors");
            }
            Audit audit = evaluate(dataset, config);
            writeReport(audit, config.output());
            return 0;
        } catch (Exception error) {
            try {
                Files.deleteIfExists(config.output());
            } catch (IOException ignored) {
                // The original failure is the useful diagnostic.
            }
            String message = error.getMessage();
            if (message == null || message.isBlank()) {
                message = error.getClass().getSimpleName();
            }
            System.err.println("error: " + message);
            return 1;
        }
    }

    private static Config parseArgs(String[] args) throws UsageException {
        if (args.length == 0 || args.length % 2 != 0) {
            throw new UsageException("six option-value pairs are required");
        }

        Set<String> allowed = Set.of("--data", "--class", "--id", "--group", "--top", "--out");
        Map<String, String> values = new HashMap<>();
        for (int index = 0; index < args.length; index += 2) {
            String option = args[index];
            if (!allowed.contains(option)) {
                throw new UsageException("unknown option: " + option);
            }
            if (values.putIfAbsent(option, args[index + 1]) != null) {
                throw new UsageException("duplicate option: " + option);
            }
            if (args[index + 1].isEmpty()) {
                throw new UsageException("empty value for " + option);
            }
        }
        for (String option : allowed) {
            if (!values.containsKey(option)) {
                throw new UsageException("missing option: " + option);
            }
        }

        int topK;
        try {
            topK = Integer.parseInt(values.get("--top"));
        } catch (NumberFormatException error) {
            throw new UsageException("invalid value for --top: must be an integer");
        }

        return new Config(
                Path.of(values.get("--data")),
                values.get("--class"),
                values.get("--id"),
                values.get("--group"),
                topK,
                Path.of(values.get("--out")));
    }

    private static Dataset load(Config config) throws Exception {
        Instances rows = new DataSource(config.data().toString()).getDataSet();
        Attribute classAttribute = requireAttribute(rows, config.className());
        Attribute idAttribute = requireAttribute(rows, config.idName());
        Attribute groupAttribute = requireAttribute(rows, config.groupName());

        if (classAttribute.index() == idAttribute.index()
                || classAttribute.index() == groupAttribute.index()
                || idAttribute.index() == groupAttribute.index()) {
            throw new IllegalArgumentException("class, id, and group attributes must differ");
        }
        if (!classAttribute.isNominal()) {
            throw new IllegalArgumentException("class attribute must be nominal");
        }
        if (!isTextAttribute(idAttribute)) {
            throw new IllegalArgumentException("id attribute must be string or nominal");
        }
        if (!isTextAttribute(groupAttribute)) {
            throw new IllegalArgumentException("group attribute must be string or nominal");
        }

        rows.setClassIndex(classAttribute.index());

        List<Integer> predictorList = new ArrayList<>();
        for (int index = 0; index < rows.numAttributes(); index++) {
            if (index == classAttribute.index()
                    || index == idAttribute.index()
                    || index == groupAttribute.index()) {
                continue;
            }
            if (!rows.attribute(index).isNumeric()) {
                throw new IllegalArgumentException("predictors must be numeric");
            }
            predictorList.add(index);
        }
        if (predictorList.isEmpty()) {
            throw new IllegalArgumentException("at least one numeric predictor is required");
        }

        Set<String> ids = new HashSet<>();
        TreeSet<String> groups = new TreeSet<>();
        boolean[] observedClasses = new boolean[classAttribute.numValues()];
        for (Instance row : rows) {
            String id = requiredText(row, idAttribute.index(), "id");
            String group = requiredText(row, groupAttribute.index(), "group");
            if (!ids.add(id)) {
                throw new IllegalArgumentException("id values must be unique");
            }
            groups.add(group);
            if (!row.classIsMissing()) {
                observedClasses[(int) row.classValue()] = true;
            }
        }

        if (classAttribute.numValues() < 2 || countTrue(observedClasses) < 2) {
            throw new IllegalArgumentException("at least two classes must occur");
        }
        if (groups.size() < 2) {
            throw new IllegalArgumentException("at least two groups must occur");
        }

        for (String heldOut : groups) {
            boolean[] inTraining = new boolean[classAttribute.numValues()];
            for (Instance row : rows) {
                if (row.classIsMissing()) {
                    continue;
                }
                if (!heldOut.equals(textValue(row, groupAttribute.index()))) {
                    inTraining[(int) row.classValue()] = true;
                }
            }
            if (countTrue(inTraining) != classAttribute.numValues()) {
                throw new IllegalArgumentException(
                        "each fold's training partition must contain every class");
            }
        }

        int[] predictors = predictorList.stream().mapToInt(Integer::intValue).toArray();
        List<String> classes = new ArrayList<>();
        for (int index = 0; index < classAttribute.numValues(); index++) {
            classes.add(classAttribute.value(index));
        }
        return new Dataset(
                rows,
                idAttribute.index(),
                groupAttribute.index(),
                classAttribute.index(),
                predictors,
                List.copyOf(classes),
                List.copyOf(groups));
    }

    private static Attribute requireAttribute(Instances rows, String name) {
        Attribute attribute = rows.attribute(name);
        if (attribute == null) {
            throw new IllegalArgumentException("attribute not found: " + name);
        }
        return attribute;
    }

    private static boolean isTextAttribute(Attribute attribute) {
        return attribute.isString() || attribute.isNominal();
    }

    private static String requiredText(Instance row, int index, String role) {
        if (row.isMissing(index)) {
            throw new IllegalArgumentException(role + " values must be nonempty and present");
        }
        String value = textValue(row, index);
        if (value.isEmpty()) {
            throw new IllegalArgumentException(role + " values must be nonempty and present");
        }
        return value;
    }

    private static String textValue(Instance row, int index) {
        return row.stringValue(index);
    }

    private static int countTrue(boolean[] values) {
        int count = 0;
        for (boolean value : values) {
            if (value) {
                count++;
            }
        }
        return count;
    }

    private static Audit evaluate(Dataset dataset, Config config) {
        List<Prediction> predictions = new ArrayList<>();
        List<Fold> folds = new ArrayList<>();
        double[] means = computeMeans(dataset);
        double[] scales = computeScales(dataset, means);
        List<Integer> selectedFeatures =
                selectTopFeaturesGlobally(dataset, means, scales, config.topK());
        List<String> selectedNames = new ArrayList<>(selectedFeatures.size());
        for (int feature : selectedFeatures) {
            selectedNames.add(dataset.rows().attribute(dataset.predictors()[feature]).name());
        }
        int[] selectedArray = selectedFeatures.stream().mapToInt(Integer::intValue).toArray();

        for (String heldOut : dataset.groups()) {
            List<Instance> training = new ArrayList<>();
            List<Instance> test = new ArrayList<>();
            for (Instance row : dataset.rows()) {
                if (heldOut.equals(textValue(row, dataset.groupIndex()))) {
                    test.add(row);
                } else {
                    training.add(row);
                }
            }

            Model model = fit(training, test, dataset, means, scales, selectedArray);
            int correct = 0;
            for (Instance row : test) {
                Prediction prediction = predict(row, heldOut, model, dataset);
                predictions.add(prediction);
                if (prediction.actualIndex() == prediction.predictedIndex()) {
                    correct++;
                }
            }
            folds.add(
                    new Fold(
                            heldOut,
                            training.size(),
                            test.size(),
                            (double) correct / test.size(),
                            selectedNames));
        }

        int[][] confusion = new int[dataset.classes().size()][dataset.classes().size()];
        double loss = 0.0;
        int correct = 0;
        for (Prediction prediction : predictions) {
            confusion[prediction.actualIndex()][prediction.predictedIndex()]++;
            if (prediction.actualIndex() == prediction.predictedIndex()) {
                correct++;
            }
            loss -= Math.log(Math.max(prediction.actualProbability(), 1.0e-15));
        }

        double accuracy = (double) correct / predictions.size();
        double macroF1 = macroF1(confusion);
        double logLoss = loss / predictions.size();
        return new Audit(
                config.data().getFileName().toString(),
                dataset.rows().numInstances(),
                config.className(),
                dataset.classes(),
                List.copyOf(folds),
                new Metrics(accuracy, macroF1, logLoss),
                confusion,
                List.copyOf(predictions));
    }

    private static double[] computeMeans(Dataset dataset) {
        int featureCount = dataset.predictors().length;
        double[] means = new double[featureCount];
        int[] present = new int[featureCount];

        for (Instance row : dataset.rows()) {
            for (int feature = 0; feature < featureCount; feature++) {
                int attribute = dataset.predictors()[feature];
                if (!row.isMissing(attribute)) {
                    means[feature] += row.value(attribute);
                    present[feature]++;
                }
            }
        }
        for (int feature = 0; feature < featureCount; feature++) {
            means[feature] = present[feature] == 0 ? 0.0 : means[feature] / present[feature];
        }
        return means;
    }

    private static double[] computeScales(Dataset dataset, double[] means) {
        int featureCount = dataset.predictors().length;
        double[] scales = new double[featureCount];
        int rowCount = dataset.rows().numInstances();

        for (Instance row : dataset.rows()) {
            for (int feature = 0; feature < featureCount; feature++) {
                int attribute = dataset.predictors()[feature];
                double value = row.isMissing(attribute) ? means[feature] : row.value(attribute);
                double difference = value - means[feature];
                scales[feature] += difference * difference;
            }
        }
        for (int feature = 0; feature < featureCount; feature++) {
            scales[feature] = Math.sqrt(scales[feature] / rowCount);
            if (scales[feature] == 0.0) {
                scales[feature] = 1.0;
            }
        }
        return scales;
    }

    private static List<Integer> selectTopFeaturesGlobally(
            Dataset dataset, double[] means, double[] scales, int topK) {
        List<Instance> labeled = new ArrayList<>();
        for (Instance row : dataset.rows()) {
            if (!row.classIsMissing()) {
                labeled.add(row);
            }
        }

        int featureCount = dataset.predictors().length;
        int classCount = dataset.classes().size();
        int rowCount = labeled.size();

        double[][] standardized = new double[rowCount][featureCount];
        int[] classIndices = new int[rowCount];
        for (int rowIndex = 0; rowIndex < rowCount; rowIndex++) {
            Instance row = labeled.get(rowIndex);
            classIndices[rowIndex] = (int) row.value(dataset.classIndex());
            standardized[rowIndex] = transform(row, dataset.predictors(), means, scales);
        }

        List<FeatureScore> scores = new ArrayList<>(featureCount);
        for (int feature = 0; feature < featureCount; feature++) {
            double globalMean = 0.0;
            for (int rowIndex = 0; rowIndex < rowCount; rowIndex++) {
                globalMean += standardized[rowIndex][feature];
            }
            globalMean /= rowCount;

            double[] classMeans = new double[classCount];
            int[] classCounts = new int[classCount];
            for (int rowIndex = 0; rowIndex < rowCount; rowIndex++) {
                int classIndex = classIndices[rowIndex];
                classMeans[classIndex] += standardized[rowIndex][feature];
                classCounts[classIndex]++;
            }
            for (int classIndex = 0; classIndex < classCount; classIndex++) {
                classMeans[classIndex] =
                        classCounts[classIndex] == 0 ? 0.0 : classMeans[classIndex] / classCounts[classIndex];
            }

            double between = 0.0;
            for (int classIndex = 0; classIndex < classCount; classIndex++) {
                double difference = classMeans[classIndex] - globalMean;
                between += classCounts[classIndex] * difference * difference;
            }

            double within = 0.0;
            for (int rowIndex = 0; rowIndex < rowCount; rowIndex++) {
                int classIndex = classIndices[rowIndex];
                double difference = standardized[rowIndex][feature] - classMeans[classIndex];
                within += difference * difference;
            }

            double score;
            if (within == 0.0 && between > 0.0) {
                score = Double.POSITIVE_INFINITY;
            } else if (within == 0.0) {
                score = 0.0;
            } else {
                score = between / within;
            }

            scores.add(new FeatureScore(feature, dataset.predictors()[feature], score));
        }

        scores.sort(
                Comparator.comparingDouble(FeatureScore::score)
                        .reversed()
                        .thenComparingInt(FeatureScore::arffIndex));

        List<Integer> selected = new ArrayList<>(topK);
        for (int index = 0; index < topK; index++) {
            selected.add(scores.get(index).featureIndex());
        }
        return selected;
    }

    private static Model fit(
            List<Instance> training,
            List<Instance> test,
            Dataset dataset,
            double[] means,
            double[] scales,
            int[] selectedFeatures) {
        int classCount = dataset.classes().size();
        int selectedCount = selectedFeatures.length;
        double[][] centroids = new double[classCount][selectedCount];
        int[] classSizes = new int[classCount];

        List<Instance> fittingRows = new ArrayList<>(training);
        fittingRows.addAll(test);
        for (Instance row : fittingRows) {
            if (row.classIsMissing()) {
                continue;
            }
            int classIndex = (int) row.value(dataset.classIndex());
            classSizes[classIndex]++;
            double[] vector = transform(row, dataset.predictors(), means, scales);
            for (int dimension = 0; dimension < selectedCount; dimension++) {
                centroids[classIndex][dimension] += vector[selectedFeatures[dimension]];
            }
        }
        for (int classIndex = 0; classIndex < classCount; classIndex++) {
            for (int dimension = 0; dimension < selectedCount; dimension++) {
                centroids[classIndex][dimension] /= classSizes[classIndex];
            }
        }
        return new Model(means, scales, selectedFeatures, centroids);
    }

    private static Prediction predict(
            Instance row, String group, Model model, Dataset dataset) {
        double[] vector =
                transform(row, dataset.predictors(), model.means(), model.scales());
        double[] distances = new double[dataset.classes().size()];
        for (int classIndex = 0; classIndex < distances.length; classIndex++) {
            double distance = 0.0;
            for (int dimension = 0; dimension < model.selectedFeatures().length; dimension++) {
                int feature = model.selectedFeatures()[dimension];
                double difference = vector[feature] - model.centroids()[classIndex][dimension];
                distance += difference * difference;
            }
            distances[classIndex] = distance;
        }

        double[] probabilities = new double[distances.length];
        double total = 0.0;
        for (int classIndex = 0; classIndex < distances.length; classIndex++) {
            probabilities[classIndex] = Math.exp(-distances[classIndex]);
            total += probabilities[classIndex];
        }

        int predicted = 0;
        for (int classIndex = 0; classIndex < probabilities.length; classIndex++) {
            probabilities[classIndex] /= total;
            if (probabilities[classIndex] > probabilities[predicted]) {
                predicted = classIndex;
            }
        }

        int actual = (int) row.value(dataset.classIndex());
        return new Prediction(
                textValue(row, dataset.idIndex()),
                group,
                actual,
                predicted,
                probabilities[actual],
                probabilities[actual]);
    }

    private static double[] transform(
            Instance row, int[] predictors, double[] means, double[] scales) {
        double[] vector = new double[predictors.length];
        for (int feature = 0; feature < predictors.length; feature++) {
            double value =
                    row.isMissing(predictors[feature])
                            ? means[feature]
                            : row.value(predictors[feature]);
            vector[feature] = (value - means[feature]) / scales[feature];
        }
        return vector;
    }

    private static double macroF1(int[][] confusion) {
        double totalF1 = 0.0;
        int totalSupport = 0;
        for (int classIndex = 0; classIndex < confusion.length; classIndex++) {
            int truePositive = confusion[classIndex][classIndex];
            int predicted = 0;
            int actual = 0;
            for (int other = 0; other < confusion.length; other++) {
                predicted += confusion[other][classIndex];
                actual += confusion[classIndex][other];
            }
            double precision = predicted == 0 ? 0.0 : (double) truePositive / predicted;
            double recall = actual == 0 ? 0.0 : (double) truePositive / actual;
            totalF1 +=
                    (precision + recall == 0.0
                                    ? 0.0
                                    : 2.0 * precision * recall / (precision + recall))
                            * actual;
            totalSupport += actual;
        }
        return totalSupport == 0 ? 0.0 : totalF1 / totalSupport;
    }

    private static void writeReport(Audit audit, Path output) throws IOException {
        StringBuilder json = new StringBuilder();
        json.append("{\n");
        json.append("  \"dataset\": ").append(quote(audit.dataset())).append(",\n");
        json.append("  \"instances\": ").append(audit.instances()).append(",\n");
        json.append("  \"classAttribute\": ")
                .append(quote(audit.classAttribute()))
                .append(",\n");
        json.append("  \"classes\": ");
        appendStringArray(json, audit.classes());
        json.append(",\n");

        json.append("  \"folds\": [\n");
        for (int index = 0; index < audit.folds().size(); index++) {
            Fold fold = audit.folds().get(index);
            json.append("    {\"group\": ")
                    .append(quote(fold.group()))
                    .append(", \"train\": ")
                    .append(fold.train())
                    .append(", \"test\": ")
                    .append(fold.test())
                    .append(", \"accuracy\": ")
                    .append(decimal(fold.accuracy()))
                    .append(", \"selectedFeatures\": ");
            appendStringArray(json, fold.selectedFeatures());
            json.append("}");
            json.append(index + 1 == audit.folds().size() ? "\n" : ",\n");
        }
        json.append("  ],\n");

        json.append("  \"metrics\": {\"accuracy\": ")
                .append(decimal(audit.metrics().accuracy()))
                .append(", \"macroF1\": ")
                .append(decimal(audit.metrics().macroF1()))
                .append(", \"logLoss\": ")
                .append(decimal(audit.metrics().logLoss()))
                .append("},\n");

        json.append("  \"confusion\": [");
        for (int row = 0; row < audit.confusion().length; row++) {
            if (row > 0) {
                json.append(", ");
            }
            json.append("[");
            for (int column = 0; column < audit.confusion()[row].length; column++) {
                if (column > 0) {
                    json.append(", ");
                }
                json.append(audit.confusion()[row][column]);
            }
            json.append("]");
        }
        json.append("],\n");

        json.append("  \"predictions\": [\n");
        for (int index = 0; index < audit.predictions().size(); index++) {
            Prediction prediction = audit.predictions().get(index);
            json.append("    {\"id\": ")
                    .append(quote(prediction.id()))
                    .append(", \"group\": ")
                    .append(quote(prediction.group()))
                    .append(", \"actual\": ")
                    .append(quote(audit.classes().get(prediction.actualIndex())))
                    .append(", \"predicted\": ")
                    .append(quote(audit.classes().get(prediction.predictedIndex())))
                    .append(", \"confidence\": ")
                    .append(decimal(prediction.confidence()))
                    .append("}");
            json.append(index + 1 == audit.predictions().size() ? "\n" : ",\n");
        }
        json.append("  ]\n");
        json.append("}\n");

        Path parent = output.toAbsolutePath().getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }
        Files.writeString(output, json.toString(), StandardCharsets.UTF_8);
    }

    private static void appendStringArray(StringBuilder json, List<String> values) {
        json.append("[");
        for (int index = 0; index < values.size(); index++) {
            if (index > 0) {
                json.append(", ");
            }
            json.append(quote(values.get(index)));
        }
        json.append("]");
    }

    private static String decimal(double value) {
        return BigDecimal.valueOf(value)
                .setScale(6, RoundingMode.HALF_UP)
                .toPlainString();
    }

    private static String quote(String value) {
        StringBuilder escaped = new StringBuilder("\"");
        for (int index = 0; index < value.length(); index++) {
            char character = value.charAt(index);
            switch (character) {
                case '"' -> escaped.append("\\\"");
                case '\\' -> escaped.append("\\\\");
                case '\b' -> escaped.append("\\b");
                case '\f' -> escaped.append("\\f");
                case '\n' -> escaped.append("\\n");
                case '\r' -> escaped.append("\\r");
                case '\t' -> escaped.append("\\t");
                default -> {
                    if (character < 0x20) {
                        escaped.append(String.format("\\u%04x", (int) character));
                    } else {
                        escaped.append(character);
                    }
                }
            }
        }
        return escaped.append('"').toString();
    }

    private record Config(
            Path data,
            String className,
            String idName,
            String groupName,
            int topK,
            Path output) {}

    private record Dataset(
            Instances rows,
            int idIndex,
            int groupIndex,
            int classIndex,
            int[] predictors,
            List<String> classes,
            List<String> groups) {}

    private record Model(
            double[] means, double[] scales, int[] selectedFeatures, double[][] centroids) {}

    private record FeatureScore(int featureIndex, int arffIndex, double score) {}

    private record Prediction(
            String id,
            String group,
            int actualIndex,
            int predictedIndex,
            double confidence,
            double actualProbability) {}

    private record Fold(
            String group, int train, int test, double accuracy, List<String> selectedFeatures) {}

    private record Metrics(double accuracy, double macroF1, double logLoss) {}

    private record Audit(
            String dataset,
            int instances,
            String classAttribute,
            List<String> classes,
            List<Fold> folds,
            Metrics metrics,
            int[][] confusion,
            List<Prediction> predictions) {}

    private static final class UsageException extends Exception {
        private UsageException(String message) {
            super(message);
        }
    }
}
