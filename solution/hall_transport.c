#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_CARRIERS 6
#define MAX_RUNS 12
#define MAX_OBSERVATIONS 1024
#define MAX_PARAMETERS (MAX_CARRIERS * 4 + MAX_RUNS * 3)
#define MAX_RESIDUALS (MAX_OBSERVATIONS * 2 + 64)
#define MAX_LINE 4096
#define ID_LEN 48

#define ELEMENTARY_CHARGE 1.602176634e-19
#define BOLTZMANN_MEV_K 0.08617333262145

typedef struct {
    double residual_sigma_threshold;
    double run_bias_sigma_threshold;
    double combined_rms_max;
    double longitudinal_rms_max;
    double hall_rms_max;
    double residual_p90_max;
    double min_clean_fraction;
    double reference_temperature_k;
    double max_charge_imbalance;
    double total_density_min_1e22_m3;
    double total_density_max_1e22_m3;
    double min_conductivity_share;
    double min_mobility_ratio;
    double max_activation_step_mev;
    double max_field_scale_step;
    double max_mean_longitudinal_offset_uohm_m;
    double max_mean_hall_offset_uohm_m;
    int output_decimals;
} Config;

typedef struct {
    char id[ID_LEN];
    int band_index;
    int charge_sign;
    double minimum[4];
    double maximum[4];
    double prior[4];
} Carrier;

typedef struct {
    char id[ID_LEN];
    double temperature_k;
    double minimum[3];
    double maximum[3];
    double prior[3];
} Run;

typedef struct {
    int id;
    int run;
    double field_t;
    double observed_longitudinal;
    double observed_hall;
    double sigma_longitudinal;
    double sigma_hall;
    int use_flag;
    int prior_flag;
} Observation;

typedef struct {
    Config cfg;
    Carrier carriers[MAX_CARRIERS];
    Run runs[MAX_RUNS];
    Observation observations[MAX_OBSERVATIONS];
    int carrier_count;
    int run_count;
    int observation_count;
} Archive;

typedef struct {
    double charge_imbalance;
    double total_density;
    double minimum_share;
    double minimum_mobility_ratio;
    double maximum_activation_step;
    double maximum_field_scale_step;
    double mean_longitudinal_offset;
    double mean_hall_offset;
} ConstraintMetrics;

typedef struct {
    double modeled_longitudinal[MAX_OBSERVATIONS];
    double modeled_hall[MAX_OBSERVATIONS];
    double residual_longitudinal[MAX_OBSERVATIONS];
    double residual_hall[MAX_OBSERVATIONS];
    double magnitude[MAX_OBSERVATIONS];
    int finding_mask[MAX_OBSERVATIONS];
    int finding_counts[5];
    int scored;
    int clean;
    double combined_rms;
    double longitudinal_rms;
    double hall_rms;
    double residual_p90;
    double clean_fraction;
} Evaluation;

static int split_csv(char *line, char **parts, int limit) {
    int count = 0;
    char *start = line;
    char *cursor = line;
    while (1) {
        if (*cursor == ',' || *cursor == '\n' || *cursor == '\r' || *cursor == '\0') {
            char end = *cursor;
            *cursor = '\0';
            if (count < limit) {
                parts[count++] = start;
            }
            if (end == '\0' || end == '\n' || end == '\r') {
                break;
            }
            start = cursor + 1;
        }
        cursor++;
    }
    return count;
}

static int join_path(char *buffer, size_t size, const char *root, const char *name) {
    int written = snprintf(buffer, size, "%s/%s", root, name);
    return written >= 0 && (size_t)written < size;
}

static FILE *open_input(const char *root, const char *name) {
    char path[1024];
    if (!join_path(path, sizeof(path), root, name)) {
        return NULL;
    }
    return fopen(path, "r");
}

static int run_index(const Archive *archive, const char *id) {
    int index;
    for (index = 0; index < archive->run_count; index++) {
        if (strcmp(archive->runs[index].id, id) == 0) {
            return index;
        }
    }
    return -1;
}

static int load_config(Archive *archive, const char *root) {
    char line[MAX_LINE];
    char *parts[2];
    FILE *file = open_input(root, "case_config.csv");
    if (file == NULL || fgets(line, sizeof(line), file) == NULL) {
        if (file != NULL) {
            fclose(file);
        }
        return 0;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        double value;
        if (split_csv(line, parts, 2) != 2) {
            fclose(file);
            return 0;
        }
        value = strtod(parts[1], NULL);
#define SET_CONFIG(name) \
        if (strcmp(parts[0], #name) == 0) archive->cfg.name = value
        SET_CONFIG(residual_sigma_threshold);
        else SET_CONFIG(run_bias_sigma_threshold);
        else SET_CONFIG(combined_rms_max);
        else SET_CONFIG(longitudinal_rms_max);
        else SET_CONFIG(hall_rms_max);
        else SET_CONFIG(residual_p90_max);
        else SET_CONFIG(min_clean_fraction);
        else SET_CONFIG(reference_temperature_k);
        else SET_CONFIG(max_charge_imbalance);
        else SET_CONFIG(total_density_min_1e22_m3);
        else SET_CONFIG(total_density_max_1e22_m3);
        else SET_CONFIG(min_conductivity_share);
        else SET_CONFIG(min_mobility_ratio);
        else SET_CONFIG(max_activation_step_mev);
        else SET_CONFIG(max_field_scale_step);
        else SET_CONFIG(max_mean_longitudinal_offset_uohm_m);
        else SET_CONFIG(max_mean_hall_offset_uohm_m);
        else if (strcmp(parts[0], "output_decimals") == 0) {
            archive->cfg.output_decimals = (int)value;
        }
#undef SET_CONFIG
    }
    fclose(file);
    return archive->cfg.reference_temperature_k > 0.0
        && archive->cfg.output_decimals == 6;
}

static int load_carriers(Archive *archive, const char *root) {
    char line[MAX_LINE];
    char *parts[15];
    FILE *file = open_input(root, "carriers.csv");
    if (file == NULL || fgets(line, sizeof(line), file) == NULL) {
        return 0;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        Carrier *row;
        if (archive->carrier_count >= MAX_CARRIERS
            || split_csv(line, parts, 15) != 15) {
            fclose(file);
            return 0;
        }
        row = &archive->carriers[archive->carrier_count++];
        snprintf(row->id, sizeof(row->id), "%s", parts[0]);
        row->band_index = atoi(parts[1]);
        row->charge_sign = atoi(parts[2]);
        row->minimum[0] = strtod(parts[3], NULL);
        row->maximum[0] = strtod(parts[4], NULL);
        row->prior[0] = strtod(parts[5], NULL);
        row->minimum[1] = strtod(parts[6], NULL);
        row->maximum[1] = strtod(parts[7], NULL);
        row->prior[1] = strtod(parts[8], NULL);
        row->minimum[2] = strtod(parts[9], NULL);
        row->maximum[2] = strtod(parts[10], NULL);
        row->prior[2] = strtod(parts[11], NULL);
        row->minimum[3] = strtod(parts[12], NULL);
        row->maximum[3] = strtod(parts[13], NULL);
        row->prior[3] = strtod(parts[14], NULL);
        if ((row->charge_sign != -1 && row->charge_sign != 1)
            || row->band_index <= 0) {
            fclose(file);
            return 0;
        }
    }
    fclose(file);
    return archive->carrier_count >= 2;
}

static int load_runs(Archive *archive, const char *root) {
    char line[MAX_LINE];
    char *parts[11];
    FILE *file = open_input(root, "runs.csv");
    if (file == NULL || fgets(line, sizeof(line), file) == NULL) {
        return 0;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        Run *row;
        if (archive->run_count >= MAX_RUNS
            || split_csv(line, parts, 11) != 11) {
            fclose(file);
            return 0;
        }
        row = &archive->runs[archive->run_count++];
        snprintf(row->id, sizeof(row->id), "%s", parts[0]);
        row->temperature_k = strtod(parts[1], NULL);
        row->minimum[0] = strtod(parts[2], NULL);
        row->maximum[0] = strtod(parts[3], NULL);
        row->prior[0] = strtod(parts[4], NULL);
        row->minimum[1] = strtod(parts[5], NULL);
        row->maximum[1] = strtod(parts[6], NULL);
        row->prior[1] = strtod(parts[7], NULL);
        row->minimum[2] = strtod(parts[8], NULL);
        row->maximum[2] = strtod(parts[9], NULL);
        row->prior[2] = strtod(parts[10], NULL);
        if (row->temperature_k <= 0.0) {
            fclose(file);
            return 0;
        }
    }
    fclose(file);
    return archive->run_count > 0;
}

static int load_observations(Archive *archive, const char *root) {
    char line[MAX_LINE];
    char *parts[8];
    FILE *file = open_input(root, "observations.csv");
    if (file == NULL || fgets(line, sizeof(line), file) == NULL) {
        return 0;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        Observation *row;
        if (archive->observation_count >= MAX_OBSERVATIONS
            || split_csv(line, parts, 8) != 8) {
            fclose(file);
            return 0;
        }
        row = &archive->observations[archive->observation_count++];
        row->id = atoi(parts[0]);
        row->run = run_index(archive, parts[1]);
        row->field_t = strtod(parts[2], NULL);
        row->observed_longitudinal = strtod(parts[3], NULL);
        row->observed_hall = strtod(parts[4], NULL);
        row->sigma_longitudinal = strtod(parts[5], NULL);
        row->sigma_hall = strtod(parts[6], NULL);
        row->use_flag = atoi(parts[7]);
        row->prior_flag = 0;
        if (row->id <= 0 || row->run < 0
            || row->sigma_longitudinal <= 0.0 || row->sigma_hall <= 0.0) {
            fclose(file);
            return 0;
        }
    }
    fclose(file);
    return archive->observation_count > 0;
}

static int load_flags(Archive *archive, const char *root) {
    char line[MAX_LINE];
    char *parts[2];
    FILE *file = open_input(root, "prior_flags.csv");
    if (file == NULL || fgets(line, sizeof(line), file) == NULL) {
        return 0;
    }
    while (fgets(line, sizeof(line), file) != NULL) {
        int id;
        int index;
        if (split_csv(line, parts, 2) != 2) {
            fclose(file);
            return 0;
        }
        id = atoi(parts[0]);
        for (index = 0; index < archive->observation_count; index++) {
            if (archive->observations[index].id == id) {
                archive->observations[index].prior_flag = 1;
            }
        }
    }
    fclose(file);
    return 1;
}

static int load_archive(Archive *archive, const char *root) {
    memset(archive, 0, sizeof(*archive));
    return load_config(archive, root)
        && load_carriers(archive, root)
        && load_runs(archive, root)
        && load_observations(archive, root)
        && load_flags(archive, root);
}

static int parameter_count(const Archive *archive) {
    return archive->carrier_count * 4 + archive->run_count * 3;
}

static int carrier_parameter_index(int carrier, int field) {
    return carrier * 4 + field;
}

static int run_parameter_index(const Archive *archive, int run, int field) {
    return archive->carrier_count * 4 + run * 3 + field;
}

static double clamp_value(double value, double minimum, double maximum) {
    if (value < minimum) {
        return minimum;
    }
    if (value > maximum) {
        return maximum;
    }
    return value;
}

static void initialize_parameters(
    const Archive *archive,
    double *parameters,
    double *minimum,
    double *maximum
) {
    int carrier;
    int run;
    int field;
    for (carrier = 0; carrier < archive->carrier_count; carrier++) {
        for (field = 0; field < 4; field++) {
            int index = carrier_parameter_index(carrier, field);
            parameters[index] = archive->carriers[carrier].prior[field];
            minimum[index] = archive->carriers[carrier].minimum[field];
            maximum[index] = archive->carriers[carrier].maximum[field];
        }
    }
    for (run = 0; run < archive->run_count; run++) {
        for (field = 0; field < 3; field++) {
            int index = run_parameter_index(archive, run, field);
            parameters[index] = archive->runs[run].prior[field];
            minimum[index] = archive->runs[run].minimum[field];
            maximum[index] = archive->runs[run].maximum[field];
        }
    }
}

static int modeled_pair(
    const Archive *archive,
    const double *parameters,
    const Observation *observation,
    double *longitudinal,
    double *hall
) {
    const Run *run = &archive->runs[observation->run];
    double temperature = run->temperature_k;
    double reference_temperature = archive->cfg.reference_temperature_k;
    double field = observation->field_t
        * parameters[run_parameter_index(archive, observation->run, 0)];
    double sigma_xx = 0.0;
    double sigma_xy = 0.0;
    int carrier;
    for (carrier = 0; carrier < archive->carrier_count; carrier++) {
        double density = parameters[carrier_parameter_index(carrier, 0)] * 1.0e22;
        double mobility = parameters[carrier_parameter_index(carrier, 1)] * 1.0e-4;
        double activation = parameters[carrier_parameter_index(carrier, 2)];
        double alpha = parameters[carrier_parameter_index(carrier, 3)];
        double magnetic_denominator;
        density *= exp(
            -(activation / BOLTZMANN_MEV_K)
            * (1.0 / temperature - 1.0 / reference_temperature)
        );
        mobility *= pow(temperature / reference_temperature, -alpha);
        magnetic_denominator = 1.0 + mobility * mobility * field * field;
        sigma_xx += density * mobility / magnetic_denominator;
        sigma_xy += archive->carriers[carrier].charge_sign
            * density * mobility * mobility * field / magnetic_denominator;
    }
    sigma_xx *= ELEMENTARY_CHARGE;
    sigma_xy *= ELEMENTARY_CHARGE;
    {
        double denominator = sigma_xx * sigma_xx + sigma_xy * sigma_xy;
        if (!(denominator > 0.0) || !isfinite(denominator)) {
            return 0;
        }
        *longitudinal = 1.0e6 * sigma_xx / denominator
            + parameters[run_parameter_index(archive, observation->run, 1)];
        *hall = -1.0e6 * sigma_xy / denominator
            + parameters[run_parameter_index(archive, observation->run, 2)];
    }
    return isfinite(*longitudinal) && isfinite(*hall);
}

static void constraint_metrics(
    const Archive *archive,
    const double *parameters,
    ConstraintMetrics *metrics
) {
    double signed_density = 0.0;
    double total_contribution = 0.0;
    double minimum_share = HUGE_VAL;
    double minimum_ratio = HUGE_VAL;
    double maximum_activation_step = 0.0;
    double maximum_field_step = 0.0;
    double mean_longitudinal = 0.0;
    double mean_hall = 0.0;
    int carrier;
    int run;
    metrics->total_density = 0.0;
    for (carrier = 0; carrier < archive->carrier_count; carrier++) {
        double density = parameters[carrier_parameter_index(carrier, 0)];
        double mobility = parameters[carrier_parameter_index(carrier, 1)];
        metrics->total_density += density;
        signed_density += archive->carriers[carrier].charge_sign * density;
        total_contribution += density * mobility;
    }
    for (carrier = 0; carrier < archive->carrier_count; carrier++) {
        double density = parameters[carrier_parameter_index(carrier, 0)];
        double mobility = parameters[carrier_parameter_index(carrier, 1)];
        double share = density * mobility / total_contribution;
        if (share < minimum_share) {
            minimum_share = share;
        }
        if (carrier + 1 < archive->carrier_count) {
            double next_mobility = parameters[carrier_parameter_index(carrier + 1, 1)];
            double ratio = mobility / next_mobility;
            double activation = parameters[carrier_parameter_index(carrier, 2)];
            double next_activation = parameters[carrier_parameter_index(carrier + 1, 2)];
            double step = fabs(activation - next_activation);
            if (ratio < minimum_ratio) {
                minimum_ratio = ratio;
            }
            if (step > maximum_activation_step) {
                maximum_activation_step = step;
            }
        }
    }
    for (run = 0; run < archive->run_count; run++) {
        double scale = parameters[run_parameter_index(archive, run, 0)];
        mean_longitudinal += parameters[run_parameter_index(archive, run, 1)];
        mean_hall += parameters[run_parameter_index(archive, run, 2)];
        if (run + 1 < archive->run_count) {
            double next_scale = parameters[run_parameter_index(archive, run + 1, 0)];
            double step = fabs(scale - next_scale);
            if (step > maximum_field_step) {
                maximum_field_step = step;
            }
        }
    }
    metrics->charge_imbalance = fabs(signed_density) / metrics->total_density;
    metrics->minimum_share = minimum_share;
    metrics->minimum_mobility_ratio =
        archive->carrier_count < 2 ? 0.0 : minimum_ratio;
    metrics->maximum_activation_step = maximum_activation_step;
    metrics->maximum_field_scale_step = maximum_field_step;
    metrics->mean_longitudinal_offset = mean_longitudinal / archive->run_count;
    metrics->mean_hall_offset = mean_hall / archive->run_count;
}

static void append_positive_penalty(
    double *residuals,
    int *count,
    double violation,
    double scale
) {
    residuals[(*count)++] = violation > 0.0 ? violation / scale : 0.0;
}

static int build_objective_residuals(
    const Archive *archive,
    const double *parameters,
    double *residuals
) {
    ConstraintMetrics metrics;
    int count = 0;
    int index;
    for (index = 0; index < archive->observation_count; index++) {
        const Observation *row = &archive->observations[index];
        double longitudinal;
        double hall;
        if (!row->use_flag || row->prior_flag) {
            continue;
        }
        if (!modeled_pair(archive, parameters, row, &longitudinal, &hall)) {
            return -1;
        }
        residuals[count++] =
            (longitudinal - row->observed_longitudinal) / row->sigma_longitudinal;
        residuals[count++] = (hall - row->observed_hall) / row->sigma_hall;
    }
    constraint_metrics(archive, parameters, &metrics);
    append_positive_penalty(
        residuals,
        &count,
        archive->cfg.total_density_min_1e22_m3 + 0.001
            - metrics.total_density,
        0.002
    );
    append_positive_penalty(
        residuals,
        &count,
        metrics.total_density
            - (archive->cfg.total_density_max_1e22_m3 - 0.001),
        0.002
    );
    append_positive_penalty(
        residuals,
        &count,
        metrics.charge_imbalance
            - (archive->cfg.max_charge_imbalance - 0.0001),
        0.0002
    );
    append_positive_penalty(
        residuals,
        &count,
        archive->cfg.min_conductivity_share + 0.0001
            - metrics.minimum_share,
        0.0002
    );
    append_positive_penalty(
        residuals,
        &count,
        archive->cfg.min_mobility_ratio + 0.001
            - metrics.minimum_mobility_ratio,
        0.002
    );
    append_positive_penalty(
        residuals,
        &count,
        metrics.maximum_activation_step
            - (archive->cfg.max_activation_step_mev - 0.005),
        0.02
    );
    append_positive_penalty(
        residuals,
        &count,
        metrics.maximum_field_scale_step
            - (archive->cfg.max_field_scale_step - 0.00001),
        0.00002
    );
    append_positive_penalty(
        residuals,
        &count,
        fabs(metrics.mean_longitudinal_offset)
            - (archive->cfg.max_mean_longitudinal_offset_uohm_m - 0.005),
        0.01
    );
    append_positive_penalty(
        residuals,
        &count,
        fabs(metrics.mean_hall_offset)
            - (archive->cfg.max_mean_hall_offset_uohm_m - 0.005),
        0.01
    );
    return count;
}

static double residual_cost(const double *residuals, int count) {
    double cost = 0.0;
    int index;
    for (index = 0; index < count; index++) {
        cost += residuals[index] * residuals[index];
    }
    return 0.5 * cost;
}

static int solve_linear_system(double *matrix, double *vector, double *answer, int size) {
    int column;
    for (column = 0; column < size; column++) {
        int pivot = column;
        int row;
        double largest = fabs(matrix[column * size + column]);
        for (row = column + 1; row < size; row++) {
            double value = fabs(matrix[row * size + column]);
            if (value > largest) {
                largest = value;
                pivot = row;
            }
        }
        if (largest < 1.0e-18) {
            return 0;
        }
        if (pivot != column) {
            int item;
            for (item = column; item < size; item++) {
                double temporary = matrix[column * size + item];
                matrix[column * size + item] = matrix[pivot * size + item];
                matrix[pivot * size + item] = temporary;
            }
            {
                double temporary = vector[column];
                vector[column] = vector[pivot];
                vector[pivot] = temporary;
            }
        }
        for (row = column + 1; row < size; row++) {
            double factor = matrix[row * size + column]
                / matrix[column * size + column];
            int item;
            matrix[row * size + column] = 0.0;
            for (item = column + 1; item < size; item++) {
                matrix[row * size + item] -=
                    factor * matrix[column * size + item];
            }
            vector[row] -= factor * vector[column];
        }
    }
    for (column = size - 1; column >= 0; column--) {
        double value = vector[column];
        int item;
        for (item = column + 1; item < size; item++) {
            value -= matrix[column * size + item] * answer[item];
        }
        answer[column] = value / matrix[column * size + column];
    }
    return 1;
}

static int optimize_parameters(
    const Archive *archive,
    double *parameters,
    const double *minimum,
    const double *maximum
) {
    int size = parameter_count(archive);
    double *base = calloc(MAX_RESIDUALS, sizeof(double));
    double *plus = calloc(MAX_RESIDUALS, sizeof(double));
    double *minus = calloc(MAX_RESIDUALS, sizeof(double));
    double *candidate_residuals = calloc(MAX_RESIDUALS, sizeof(double));
    double *jacobian = calloc((size_t)MAX_RESIDUALS * (size_t)size, sizeof(double));
    double *normal = calloc((size_t)size * (size_t)size, sizeof(double));
    double *work_matrix = calloc((size_t)size * (size_t)size, sizeof(double));
    double *gradient = calloc((size_t)size, sizeof(double));
    double *work_vector = calloc((size_t)size, sizeof(double));
    double *step_vector = calloc((size_t)size, sizeof(double));
    double *candidate = calloc((size_t)size, sizeof(double));
    double lambda = 1.0e-3;
    int count;
    int iteration;
    int success = 0;
    if (base == NULL || plus == NULL || minus == NULL
        || candidate_residuals == NULL || jacobian == NULL || normal == NULL
        || work_matrix == NULL || gradient == NULL || work_vector == NULL
        || step_vector == NULL || candidate == NULL) {
        goto cleanup;
    }
    count = build_objective_residuals(archive, parameters, base);
    if (count <= 0) {
        goto cleanup;
    }
    for (iteration = 0; iteration < 120; iteration++) {
        double cost = residual_cost(base, count);
        int parameter;
        int accepted = 0;
        memset(jacobian, 0, (size_t)MAX_RESIDUALS * (size_t)size * sizeof(double));
        for (parameter = 0; parameter < size; parameter++) {
            double original = parameters[parameter];
            double scale = maximum[parameter] - minimum[parameter];
            double difference = fmax(1.0e-6, scale * 2.0e-5);
            double upper = clamp_value(original + difference, minimum[parameter], maximum[parameter]);
            double lower = clamp_value(original - difference, minimum[parameter], maximum[parameter]);
            int plus_count;
            int minus_count;
            int residual;
            parameters[parameter] = upper;
            plus_count = build_objective_residuals(archive, parameters, plus);
            parameters[parameter] = lower;
            minus_count = build_objective_residuals(archive, parameters, minus);
            parameters[parameter] = original;
            if (plus_count != count || minus_count != count || upper == lower) {
                goto cleanup;
            }
            for (residual = 0; residual < count; residual++) {
                jacobian[residual * size + parameter] =
                    (plus[residual] - minus[residual]) / (upper - lower);
            }
        }
        memset(normal, 0, (size_t)size * (size_t)size * sizeof(double));
        memset(gradient, 0, (size_t)size * sizeof(double));
        {
            int row;
            for (row = 0; row < count; row++) {
                int left;
                for (left = 0; left < size; left++) {
                    double left_value = jacobian[row * size + left];
                    int right;
                    gradient[left] += left_value * base[row];
                    for (right = 0; right <= left; right++) {
                        normal[left * size + right] +=
                            left_value * jacobian[row * size + right];
                    }
                }
            }
        }
        {
            int left;
            for (left = 0; left < size; left++) {
                int right;
                for (right = 0; right < left; right++) {
                    normal[right * size + left] = normal[left * size + right];
                }
            }
        }
        {
            int attempt;
            for (attempt = 0; attempt < 12; attempt++) {
                int index;
                int candidate_count;
                double candidate_cost;
                memcpy(
                    work_matrix,
                    normal,
                    (size_t)size * (size_t)size * sizeof(double)
                );
                for (index = 0; index < size; index++) {
                    work_matrix[index * size + index] +=
                        lambda * (normal[index * size + index] + 1.0e-8);
                    work_vector[index] = -gradient[index];
                    step_vector[index] = 0.0;
                }
                if (!solve_linear_system(
                    work_matrix, work_vector, step_vector, size
                )) {
                    lambda *= 10.0;
                    continue;
                }
                for (index = 0; index < size; index++) {
                    candidate[index] = clamp_value(
                        parameters[index] + step_vector[index],
                        minimum[index],
                        maximum[index]
                    );
                }
                candidate_count = build_objective_residuals(
                    archive, candidate, candidate_residuals
                );
                if (candidate_count != count) {
                    goto cleanup;
                }
                candidate_cost = residual_cost(candidate_residuals, count);
                if (candidate_cost < cost) {
                    memcpy(parameters, candidate, (size_t)size * sizeof(double));
                    memcpy(
                        base,
                        candidate_residuals,
                        (size_t)count * sizeof(double)
                    );
                    lambda = fmax(1.0e-12, lambda * 0.25);
                    accepted = 1;
                    if (cost - candidate_cost < 1.0e-10 * (1.0 + cost)) {
                        iteration = 120;
                    }
                    break;
                }
                lambda *= 8.0;
            }
        }
        if (!accepted && lambda > 1.0e18) {
            break;
        }
    }
    success = 1;

cleanup:
    free(base);
    free(plus);
    free(minus);
    free(candidate_residuals);
    free(jacobian);
    free(normal);
    free(work_matrix);
    free(gradient);
    free(work_vector);
    free(step_vector);
    free(candidate);
    return success;
}

static void canonicalize_parameters(
    const Archive *archive,
    double *parameters,
    const double *minimum,
    const double *maximum
) {
    int size = parameter_count(archive);
    int index;
    for (index = 0; index < size; index++) {
        parameters[index] = clamp_value(
            round(parameters[index] * 1.0e6) / 1.0e6,
            minimum[index],
            maximum[index]
        );
    }
}

static int compare_double(const void *left, const void *right) {
    double a = *(const double *)left;
    double b = *(const double *)right;
    return (a > b) - (a < b);
}

static double median(double *values, int count) {
    if (count == 0) {
        return 0.0;
    }
    qsort(values, (size_t)count, sizeof(double), compare_double);
    if (count % 2 != 0) {
        return values[count / 2];
    }
    return 0.5 * (values[count / 2 - 1] + values[count / 2]);
}

static int evaluate_parameters(
    const Archive *archive,
    const double *parameters,
    Evaluation *evaluation
) {
    double run_median[MAX_RUNS];
    double longitudinal_square_sum = 0.0;
    double hall_square_sum = 0.0;
    double scored_magnitudes[MAX_OBSERVATIONS];
    int observation;
    int run;
    memset(evaluation, 0, sizeof(*evaluation));
    for (observation = 0; observation < archive->observation_count; observation++) {
        const Observation *row = &archive->observations[observation];
        if (!modeled_pair(
            archive,
            parameters,
            row,
            &evaluation->modeled_longitudinal[observation],
            &evaluation->modeled_hall[observation]
        )) {
            return 0;
        }
        evaluation->residual_longitudinal[observation] =
            (evaluation->modeled_longitudinal[observation]
                - row->observed_longitudinal)
            / row->sigma_longitudinal;
        evaluation->residual_hall[observation] =
            (evaluation->modeled_hall[observation] - row->observed_hall)
            / row->sigma_hall;
        evaluation->magnitude[observation] = hypot(
            evaluation->residual_longitudinal[observation],
            evaluation->residual_hall[observation]
        ) / sqrt(2.0);
    }
    for (run = 0; run < archive->run_count; run++) {
        double values[MAX_OBSERVATIONS];
        int count = 0;
        for (observation = 0;
             observation < archive->observation_count;
             observation++) {
            const Observation *row = &archive->observations[observation];
            if (row->run == run && row->use_flag && !row->prior_flag) {
                values[count++] = evaluation->magnitude[observation];
            }
        }
        run_median[run] = median(values, count);
    }
    for (observation = 0; observation < archive->observation_count; observation++) {
        const Observation *row = &archive->observations[observation];
        int mask = 0;
        if (!row->use_flag) {
            mask |= 1;
        }
        if (row->prior_flag) {
            mask |= 2;
        }
        if (row->use_flag && !row->prior_flag) {
            double longitudinal = evaluation->residual_longitudinal[observation];
            double hall = evaluation->residual_hall[observation];
            double magnitude = evaluation->magnitude[observation];
            longitudinal_square_sum += longitudinal * longitudinal;
            hall_square_sum += hall * hall;
            scored_magnitudes[evaluation->scored++] = magnitude;
            if (fabs(longitudinal) > archive->cfg.residual_sigma_threshold) {
                mask |= 4;
            }
            if (fabs(hall) > archive->cfg.residual_sigma_threshold) {
                mask |= 8;
            }
            if (fabs(magnitude - run_median[row->run])
                > archive->cfg.run_bias_sigma_threshold) {
                mask |= 16;
            }
            if ((mask & 28) == 0) {
                evaluation->clean++;
            }
        }
        evaluation->finding_mask[observation] = mask;
        if (mask & 1) evaluation->finding_counts[0]++;
        if (mask & 2) evaluation->finding_counts[1]++;
        if (mask & 4) evaluation->finding_counts[2]++;
        if (mask & 8) evaluation->finding_counts[3]++;
        if (mask & 16) evaluation->finding_counts[4]++;
    }
    if (evaluation->scored > 0) {
        evaluation->longitudinal_rms = sqrt(
            longitudinal_square_sum / evaluation->scored
        );
        evaluation->hall_rms = sqrt(hall_square_sum / evaluation->scored);
        evaluation->combined_rms = sqrt(
            (
                evaluation->longitudinal_rms * evaluation->longitudinal_rms
                + evaluation->hall_rms * evaluation->hall_rms
            ) / 2.0
        );
        qsort(
            scored_magnitudes,
            (size_t)evaluation->scored,
            sizeof(double),
            compare_double
        );
        evaluation->residual_p90 = scored_magnitudes[
            (int)ceil(0.9 * evaluation->scored) - 1
        ];
        evaluation->clean_fraction =
            (double)evaluation->clean / evaluation->scored;
    } else {
        evaluation->clean_fraction = 1.0;
    }
    return 1;
}

static int parameters_within_bounds(
    const Archive *archive,
    const double *parameters
) {
    int carrier;
    int run;
    int field;
    for (carrier = 0; carrier < archive->carrier_count; carrier++) {
        for (field = 0; field < 4; field++) {
            double value = parameters[carrier_parameter_index(carrier, field)];
            if (!isfinite(value)
                || value < archive->carriers[carrier].minimum[field]
                || value > archive->carriers[carrier].maximum[field]) {
                return 0;
            }
        }
    }
    for (run = 0; run < archive->run_count; run++) {
        for (field = 0; field < 3; field++) {
            double value = parameters[run_parameter_index(archive, run, field)];
            if (!isfinite(value)
                || value < archive->runs[run].minimum[field]
                || value > archive->runs[run].maximum[field]) {
                return 0;
            }
        }
    }
    return 1;
}

static int final_state_valid(
    const Archive *archive,
    const double *parameters,
    ConstraintMetrics *metrics,
    Evaluation *evaluation
) {
    const double tolerance = 1.0e-9;
    if (!parameters_within_bounds(archive, parameters)
        || !evaluate_parameters(archive, parameters, evaluation)) {
        return 0;
    }
    constraint_metrics(archive, parameters, metrics);
    return metrics->charge_imbalance
            <= archive->cfg.max_charge_imbalance + tolerance
        && metrics->total_density
            >= archive->cfg.total_density_min_1e22_m3 - tolerance
        && metrics->total_density
            <= archive->cfg.total_density_max_1e22_m3 + tolerance
        && metrics->minimum_share
            >= archive->cfg.min_conductivity_share - tolerance
        && metrics->minimum_mobility_ratio
            >= archive->cfg.min_mobility_ratio - tolerance
        && metrics->maximum_activation_step
            <= archive->cfg.max_activation_step_mev + tolerance
        && metrics->maximum_field_scale_step
            <= archive->cfg.max_field_scale_step + tolerance
        && fabs(metrics->mean_longitudinal_offset)
            <= archive->cfg.max_mean_longitudinal_offset_uohm_m + tolerance
        && fabs(metrics->mean_hall_offset)
            <= archive->cfg.max_mean_hall_offset_uohm_m + tolerance
        && evaluation->combined_rms
            <= archive->cfg.combined_rms_max + tolerance
        && evaluation->longitudinal_rms
            <= archive->cfg.longitudinal_rms_max + tolerance
        && evaluation->hall_rms
            <= archive->cfg.hall_rms_max + tolerance
        && evaluation->residual_p90
            <= archive->cfg.residual_p90_max + tolerance
        && evaluation->clean_fraction
            >= archive->cfg.min_clean_fraction - tolerance;
}

static void remove_named_outputs(const char *root) {
    const char *names[] = {
        "transport_parameters.json",
        "observation_residuals.jsonl",
        "transport_summary.json",
    };
    char path[1024];
    size_t index;
    for (index = 0; index < sizeof(names) / sizeof(names[0]); index++) {
        if (join_path(path, sizeof(path), root, names[index])) {
            remove(path);
        }
    }
}

static void stable_observation_order(const Archive *archive, int *order) {
    int index;
    for (index = 0; index < archive->observation_count; index++) {
        order[index] = index;
    }
    for (index = 1; index < archive->observation_count; index++) {
        int value = order[index];
        int position = index;
        while (
            position > 0
            && archive->observations[value].id
                < archive->observations[order[position - 1]].id
        ) {
            order[position] = order[position - 1];
            position--;
        }
        order[position] = value;
    }
}

static int write_outputs(
    const Archive *archive,
    const char *root,
    const double *parameters,
    const ConstraintMetrics *metrics,
    const Evaluation *evaluation
) {
    char path[1024];
    FILE *file;
    int carrier;
    int run;
    int observation;
    int order[MAX_OBSERVATIONS];

    if (!join_path(path, sizeof(path), root, "transport_parameters.json")) {
        return 0;
    }
    file = fopen(path, "w");
    if (file == NULL) {
        return 0;
    }
    fprintf(file, "{\n");
    fprintf(file, "  \"reference\":\"carrier input order and run input order\",\n");
    fprintf(
        file,
        "  \"rounding\":{\"carrier_parameters\":6,\"run_parameters\":6,"
        "\"modeled_uohm_m\":6,\"residual_sigma\":6},\n"
    );
    fprintf(file, "  \"carriers\":[\n");
    for (carrier = 0; carrier < archive->carrier_count; carrier++) {
        fprintf(
            file,
            "    {\"carrier_id\":\"%s\",\"band_index\":%d,\"charge_sign\":%d,"
            "\"density_1e22_m3\":%.6f,\"mobility_cm2_vs\":%.6f,"
            "\"activation_mev\":%.6f,\"alpha\":%.6f}%s\n",
            archive->carriers[carrier].id,
            archive->carriers[carrier].band_index,
            archive->carriers[carrier].charge_sign,
            parameters[carrier_parameter_index(carrier, 0)],
            parameters[carrier_parameter_index(carrier, 1)],
            parameters[carrier_parameter_index(carrier, 2)],
            parameters[carrier_parameter_index(carrier, 3)],
            carrier + 1 == archive->carrier_count ? "" : ","
        );
    }
    fprintf(file, "  ],\n  \"runs\":[\n");
    for (run = 0; run < archive->run_count; run++) {
        fprintf(
            file,
            "    {\"run_id\":\"%s\",\"temperature_k\":%.6f,"
            "\"field_scale\":%.6f,\"longitudinal_offset_uohm_m\":%.6f,"
            "\"hall_offset_uohm_m\":%.6f}%s\n",
            archive->runs[run].id,
            archive->runs[run].temperature_k,
            parameters[run_parameter_index(archive, run, 0)],
            parameters[run_parameter_index(archive, run, 1)],
            parameters[run_parameter_index(archive, run, 2)],
            run + 1 == archive->run_count ? "" : ","
        );
    }
    fprintf(
        file,
        "  ],\n  \"constraints\":{\"charge_imbalance\":%.6f,"
        "\"total_density_1e22_m3\":%.6f,\"minimum_conductivity_share\":%.6f,"
        "\"minimum_mobility_ratio\":%.6f,\"maximum_activation_step_mev\":%.6f,"
        "\"maximum_field_scale_step\":%.6f,"
        "\"mean_longitudinal_offset_uohm_m\":%.6f,"
        "\"mean_hall_offset_uohm_m\":%.6f}\n}\n",
        metrics->charge_imbalance,
        metrics->total_density,
        metrics->minimum_share,
        metrics->minimum_mobility_ratio,
        metrics->maximum_activation_step,
        metrics->maximum_field_scale_step,
        metrics->mean_longitudinal_offset,
        metrics->mean_hall_offset
    );
    fclose(file);

    stable_observation_order(archive, order);
    if (!join_path(path, sizeof(path), root, "observation_residuals.jsonl")) {
        return 0;
    }
    file = fopen(path, "w");
    if (file == NULL) {
        return 0;
    }
    for (observation = 0;
         observation < archive->observation_count;
         observation++) {
        int source_index = order[observation];
        const Observation *row = &archive->observations[source_index];
        int mask = evaluation->finding_mask[source_index];
        int first = 1;
        fprintf(
            file,
            "{\"observation_id\":%d,\"run_id\":\"%s\",\"field_t\":%.6f,"
            "\"modeled_longitudinal_uohm_m\":%.6f,"
            "\"observed_longitudinal_uohm_m\":%.6f,"
            "\"longitudinal_residual_sigma\":%.6f,"
            "\"modeled_hall_uohm_m\":%.6f,\"observed_hall_uohm_m\":%.6f,"
            "\"hall_residual_sigma\":%.6f,\"findings\":[",
            row->id,
            archive->runs[row->run].id,
            row->field_t,
            evaluation->modeled_longitudinal[source_index],
            row->observed_longitudinal,
            evaluation->residual_longitudinal[source_index],
            evaluation->modeled_hall[source_index],
            row->observed_hall,
            evaluation->residual_hall[source_index]
        );
#define EMIT_FINDING(bit, name) \
        if (mask & bit) { \
            fprintf(file, "%s\"%s\"", first ? "" : ",", name); \
            first = 0; \
        }
        EMIT_FINDING(1, "excluded_observation");
        EMIT_FINDING(2, "prior_flag");
        EMIT_FINDING(4, "longitudinal_outlier");
        EMIT_FINDING(8, "hall_outlier");
        EMIT_FINDING(16, "run_bias");
#undef EMIT_FINDING
        fprintf(file, "]}\n");
    }
    fclose(file);

    if (!join_path(path, sizeof(path), root, "transport_summary.json")) {
        return 0;
    }
    file = fopen(path, "w");
    if (file == NULL) {
        return 0;
    }
    fprintf(
        file,
        "{\"carrier_count\":%d,\"run_count\":%d,\"observations\":%d,"
        "\"scored_observations\":%d,\"clean_observations\":%d,"
        "\"combined_rms\":%.6f,\"longitudinal_rms\":%.6f,\"hall_rms\":%.6f,"
        "\"residual_p90\":%.6f,\"clean_fraction\":%.6f,"
        "\"charge_imbalance\":%.6f,\"total_density_1e22_m3\":%.6f,"
        "\"minimum_conductivity_share\":%.6f,"
        "\"minimum_mobility_ratio\":%.6f,"
        "\"maximum_activation_step_mev\":%.6f,"
        "\"maximum_field_scale_step\":%.6f,"
        "\"mean_longitudinal_offset_uohm_m\":%.6f,"
        "\"mean_hall_offset_uohm_m\":%.6f,"
        "\"finding_counts\":{\"excluded_observation\":%d,\"prior_flag\":%d,"
        "\"longitudinal_outlier\":%d,\"hall_outlier\":%d,\"run_bias\":%d}}\n",
        archive->carrier_count,
        archive->run_count,
        archive->observation_count,
        evaluation->scored,
        evaluation->clean,
        evaluation->combined_rms,
        evaluation->longitudinal_rms,
        evaluation->hall_rms,
        evaluation->residual_p90,
        evaluation->clean_fraction,
        metrics->charge_imbalance,
        metrics->total_density,
        metrics->minimum_share,
        metrics->minimum_mobility_ratio,
        metrics->maximum_activation_step,
        metrics->maximum_field_scale_step,
        metrics->mean_longitudinal_offset,
        metrics->mean_hall_offset,
        evaluation->finding_counts[0],
        evaluation->finding_counts[1],
        evaluation->finding_counts[2],
        evaluation->finding_counts[3],
        evaluation->finding_counts[4]
    );
    fclose(file);
    return 1;
}

int main(int argc, char **argv) {
    Archive archive;
    ConstraintMetrics metrics;
    Evaluation evaluation;
    double parameters[MAX_PARAMETERS];
    double minimum[MAX_PARAMETERS];
    double maximum[MAX_PARAMETERS];
    if (argc != 3) {
        fprintf(stderr, "usage: %s <input_dir> <output_dir>\n", argv[0]);
        return 2;
    }
    remove_named_outputs(argv[2]);
    if (!load_archive(&archive, argv[1])) {
        fprintf(stderr, "failed to load transport archive: %s\n", strerror(errno));
        return 1;
    }
    initialize_parameters(&archive, parameters, minimum, maximum);
    if (!optimize_parameters(&archive, parameters, minimum, maximum)) {
        fprintf(stderr, "transport optimization failed\n");
        return 1;
    }
    canonicalize_parameters(&archive, parameters, minimum, maximum);
    if (!final_state_valid(
        &archive, parameters, &metrics, &evaluation
    )) {
        fprintf(
            stderr,
            "no calibration satisfies every configured gate "
            "(combined=%.6f longitudinal=%.6f hall=%.6f p90=%.6f clean=%.6f "
            "charge=%.6f density=%.6f share=%.6f ratio=%.6f "
            "activation=%.6f field_step=%.6f mean_offsets=%.6f/%.6f)\n",
            evaluation.combined_rms,
            evaluation.longitudinal_rms,
            evaluation.hall_rms,
            evaluation.residual_p90,
            evaluation.clean_fraction,
            metrics.charge_imbalance,
            metrics.total_density,
            metrics.minimum_share,
            metrics.minimum_mobility_ratio,
            metrics.maximum_activation_step,
            metrics.maximum_field_scale_step,
            metrics.mean_longitudinal_offset,
            metrics.mean_hall_offset
        );
        return 1;
    }
    if (!write_outputs(
        &archive, argv[2], parameters, &metrics, &evaluation
    )) {
        remove_named_outputs(argv[2]);
        fprintf(stderr, "failed to write transport outputs: %s\n", strerror(errno));
        return 1;
    }
    return 0;
}
