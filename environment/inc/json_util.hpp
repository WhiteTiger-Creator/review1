#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

struct JsonValue {
    enum class Type { Null, Bool, Int, Double, String, Array, Object };

    Type type = Type::Null;
    bool bool_val = false;
    int64_t int_val = 0;
    double double_val = 0.0;
    std::string str_val;
    std::vector<JsonValue> arr_val;
    std::map<std::string, JsonValue> obj_val;

    static JsonValue make_null();
    static JsonValue make_bool(bool v);
    static JsonValue make_int(int64_t v);
    static JsonValue make_double(double v);
    static JsonValue make_string(std::string v);
    static JsonValue make_array(std::vector<JsonValue> v);
    static JsonValue make_object(std::map<std::string, JsonValue> v);

    bool is_null() const { return type == Type::Null; }
    bool is_bool() const { return type == Type::Bool; }
    bool is_int() const { return type == Type::Int; }
    bool is_double() const { return type == Type::Double; }
    bool is_number() const { return type == Type::Int || type == Type::Double; }
    bool is_string() const { return type == Type::String; }
    bool is_array() const { return type == Type::Array; }
    bool is_object() const { return type == Type::Object; }

    const JsonValue* get(const std::string& key) const;
    JsonValue* get(const std::string& key);
};

std::optional<JsonValue> parse_json(const std::string& text);
std::string canonical_json(const JsonValue& value);
