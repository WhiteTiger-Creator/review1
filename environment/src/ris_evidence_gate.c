#define _POSIX_C_SOURCE 200809L

#include "ris_evidence_gate.h"

#include <errno.h>
#include <json-c/json.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

struct observation {
    char query_time[64];
    long peers_seeing;
    long total_peers;
};

static char *trim(char *text) {
    char *end;
    while (*text == ' ' || *text == '\t' || *text == '\r' || *text == '\n') {
        text++;
    }
    end = text + strlen(text);
    while (end > text && (end[-1] == ' ' || end[-1] == '\t' ||
                           end[-1] == '\r' || end[-1] == '\n')) {
        *--end = '\0';
    }
    return text;
}

static bool copy_value(char *destination, size_t capacity, const char *value) {
    size_t length = strlen(value);
    if (length == 0 || length >= capacity) {
        return false;
    }
    memcpy(destination, value, length + 1);
    return true;
}

static bool parse_long(const char *text, long *value) {
    char *end = NULL;
    errno = 0;
    long parsed = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0') {
        return false;
    }
    *value = parsed;
    return true;
}

static bool read_policy(const char *path, struct policy *policy) {
    FILE *stream = fopen(path, "r");
    char *line = NULL;
    size_t capacity = 0;
    unsigned fields = 0;
    if (stream == NULL) {
        fprintf(stderr, "policy: cannot open %s\n", path);
        return false;
    }
    memset(policy, 0, sizeof(*policy));
    while (getline(&line, &capacity, stream) >= 0) {
        char *entry = trim(line);
        char *separator;
        char *key;
        char *value;
        if (*entry == '\0' || *entry == '#') {
            continue;
        }
        separator = strchr(entry, '=');
        if (separator == NULL) {
            fprintf(stderr, "policy: malformed line\n");
            free(line);
            fclose(stream);
            return false;
        }
        *separator = '\0';
        key = trim(entry);
        value = trim(separator + 1);
        if (strcmp(key, "change_id") == 0 &&
            copy_value(policy->change_id, sizeof(policy->change_id), value)) {
            fields |= 1U;
        } else if (strcmp(key, "ipv4_resource") == 0 &&
                   copy_value(policy->ipv4_resource,
                              sizeof(policy->ipv4_resource), value)) {
            fields |= 2U;
        } else if (strcmp(key, "ipv6_resource") == 0 &&
                   copy_value(policy->ipv6_resource,
                              sizeof(policy->ipv6_resource), value)) {
            fields |= 4U;
        } else if (strcmp(key, "expected_origin") == 0 &&
                   parse_long(value, &policy->expected_origin)) {
            fields |= 8U;
        } else if (strcmp(key, "min_visibility_percent") == 0 &&
                   parse_long(value, &policy->min_visibility_percent)) {
            fields |= 16U;
        } else if (strcmp(key, "standby_profile") == 0 &&
                   copy_value(policy->standby_profile,
                              sizeof(policy->standby_profile), value)) {
            fields |= 32U;
        } else {
            fprintf(stderr, "policy: unknown or invalid key %s\n", key);
            free(line);
            fclose(stream);
            return false;
        }
    }
    free(line);
    fclose(stream);
    if (fields != 63U || policy->expected_origin <= 0 ||
        policy->min_visibility_percent < 1 ||
        policy->min_visibility_percent > 100) {
        fprintf(stderr, "policy: missing or invalid values\n");
        return false;
    }
    return true;
}

static json_object *required_object(json_object *parent, const char *name,
                                    enum json_type type) {
    json_object *value = NULL;
    if (!json_object_object_get_ex(parent, name, &value) ||
        json_object_get_type(value) != type) {
        return NULL;
    }
    return value;
}

static bool inspect_response(const char *path, const char *resource,
                             const char *family, long expected_origin,
                             long min_percent, struct observation *result,
                             char *reason, size_t reason_capacity) {
    json_object *root = json_object_from_file(path);
    json_object *status;
    json_object *data;
    json_object *value;
    json_object *origins;
    json_object *origin_item;
    json_object *more_specifics;
    json_object *visibility;
    json_object *family_visibility;
    json_object *seeing;
    json_object *total;
    const char *observed_resource;
    const char *query_time;
    long observed_origin;
    bool safe = false;

    if (root == NULL || json_object_get_type(root) != json_type_object) {
        snprintf(reason, reason_capacity, "invalid_json");
        goto done;
    }
    status = required_object(root, "status", json_type_string);
    data = required_object(root, "data", json_type_object);
    if (status == NULL || data == NULL ||
        strcmp(json_object_get_string(status), "ok") != 0) {
        snprintf(reason, reason_capacity, "api_status");
        goto done;
    }
    value = required_object(data, "resource", json_type_string);
    if (value == NULL) {
        snprintf(reason, reason_capacity, "resource_missing");
        goto done;
    }
    observed_resource = json_object_get_string(value);
    if (strcmp(observed_resource, resource) != 0) {
        snprintf(reason, reason_capacity, "resource_mismatch");
        goto done;
    }
    value = required_object(data, "query_time", json_type_string);
    if (value == NULL || strlen(json_object_get_string(value)) >= sizeof(result->query_time)) {
        snprintf(reason, reason_capacity, "query_time_missing");
        goto done;
    }
    query_time = json_object_get_string(value);
    strcpy(result->query_time, query_time);

    origins = required_object(data, "origins", json_type_array);
    if (origins == NULL || json_object_array_length(origins) != 1) {
        snprintf(reason, reason_capacity, "origin_cardinality");
        goto done;
    }
    origin_item = json_object_array_get_idx(origins, 0);
    value = required_object(origin_item, "origin", json_type_int);
    if (value == NULL) {
        snprintf(reason, reason_capacity, "origin_missing");
        goto done;
    }
    observed_origin = json_object_get_int64(value);
    if (observed_origin != expected_origin) {
        snprintf(reason, reason_capacity, "origin_mismatch");
        goto done;
    }
    more_specifics = required_object(data, "more_specifics", json_type_array);
    if (more_specifics == NULL || json_object_array_length(more_specifics) != 0) {
        snprintf(reason, reason_capacity, "more_specific_seen");
        goto done;
    }
    visibility = required_object(data, "visibility", json_type_object);
    family_visibility = visibility == NULL ? NULL :
        required_object(visibility, family, json_type_object);
    seeing = family_visibility == NULL ? NULL :
        required_object(family_visibility, "ris_peers_seeing", json_type_int);
    total = family_visibility == NULL ? NULL :
        required_object(family_visibility, "total_ris_peers", json_type_int);
    if (seeing == NULL || total == NULL) {
        snprintf(reason, reason_capacity, "visibility_missing");
        goto done;
    }
    result->peers_seeing = json_object_get_int64(seeing);
    result->total_peers = json_object_get_int64(total);
    if (result->total_peers <= 0 || result->peers_seeing < 0 ||
        result->peers_seeing > result->total_peers ||
        result->peers_seeing * 100 < min_percent * result->total_peers) {
        snprintf(reason, reason_capacity, "visibility_below_floor");
        goto done;
    }
    snprintf(reason, reason_capacity, "safe");
    safe = true;

done:
    if (root != NULL) {
        json_object_put(root);
    }
    return safe;
}

static bool write_decision(const char *path, const struct policy *policy,
                           bool safe, const char *reason,
                           const struct observation *v4,
                           const struct observation *v6) {
    json_object *root = json_object_new_object();
    json_object *times = json_object_new_object();
    json_object *visibility = json_object_new_object();
    json_object *v4_visibility = json_object_new_object();
    json_object *v6_visibility = json_object_new_object();
    int rc;
    if (root == NULL || times == NULL || visibility == NULL ||
        v4_visibility == NULL || v6_visibility == NULL) {
        fprintf(stderr, "output: allocation failed\n");
        return false;
    }
    json_object_object_add(root, "change_id", json_object_new_string(policy->change_id));
    json_object_object_add(root, "decision",
                           json_object_new_string(safe ? "APPLY_STANDBY" : "HOLD"));
    json_object_object_add(root, "selected_profile",
                           safe ? json_object_new_string(policy->standby_profile) : NULL);
    json_object_object_add(root, "reason", json_object_new_string(reason));
    json_object_object_add(times, "ipv4", json_object_new_string(v4->query_time));
    json_object_object_add(times, "ipv6", json_object_new_string(v6->query_time));
    json_object_object_add(root, "query_times", times);
    json_object_object_add(v4_visibility, "seeing", json_object_new_int64(v4->peers_seeing));
    json_object_object_add(v4_visibility, "total", json_object_new_int64(v4->total_peers));
    json_object_object_add(v6_visibility, "seeing", json_object_new_int64(v6->peers_seeing));
    json_object_object_add(v6_visibility, "total", json_object_new_int64(v6->total_peers));
    json_object_object_add(visibility, "ipv4", v4_visibility);
    json_object_object_add(visibility, "ipv6", v6_visibility);
    json_object_object_add(root, "visibility", visibility);
    rc = json_object_to_file_ext(path, root,
                                 JSON_C_TO_STRING_PRETTY | JSON_C_TO_STRING_PRETTY_TAB);
    json_object_put(root);
    if (rc != 0) {
        fprintf(stderr, "output: cannot write %s\n", path);
        return false;
    }
    return true;
}

int main(int argc, char **argv) {
    struct policy policy;
    struct observation v4 = {0};
    struct observation v6 = {0};
    char reason_v4[64] = {0};
    char reason_v6[64] = {0};
    char reason[160];
    bool safe_v4;
    bool safe_v6;
    bool safe;
    if (argc != 5) {
        fprintf(stderr, "usage: ris-evidence-gate POLICY IPV4_JSON IPV6_JSON OUTPUT\n");
        return EXIT_POLICY_ERROR;
    }
    if (!read_policy(argv[1], &policy)) {
        return EXIT_POLICY_ERROR;
    }
    safe_v4 = inspect_response(argv[2], policy.ipv4_resource, "v4",
                               policy.expected_origin,
                               policy.min_visibility_percent, &v4,
                               reason_v4, sizeof(reason_v4));
    safe_v6 = inspect_response(argv[3], policy.ipv6_resource, "v6",
                               policy.expected_origin,
                               policy.min_visibility_percent, &v6,
                               reason_v6, sizeof(reason_v6));
    safe = safe_v4 && safe_v6;
    if (safe) {
        strcpy(reason, "exact_origin_visible_no_more_specifics");
    } else {
        snprintf(reason, sizeof(reason), "ipv4:%s;ipv6:%s", reason_v4, reason_v6);
    }
    if (!write_decision(argv[4], &policy, safe, reason, &v4, &v6)) {
        return EXIT_IO_ERROR;
    }
    return 0;
}
