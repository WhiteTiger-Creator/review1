#include "json_util.hpp"

#include <cctype>
#include <charconv>
#include <cstdio>
#include <cstring>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace {

struct Parser {
    const std::string& s;
    size_t i = 0;

    void ws() { while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i]))) ++i; }
    char peek() const { return i < s.size() ? s[i] : '\0'; }
    char take() {
        if (i >= s.size()) throw std::runtime_error("eof");
        return s[i++];
    }

    std::string str() {
        take();
        std::string o;
        while (i < s.size()) {
            char c = take();
            if (c == '"') return o;
            if (c != '\\') { o.push_back(c); continue; }
            char e = take();
            if (e == 'u') {
                unsigned code = 0;
                for (int k = 0; k < 4; ++k) {
                    char h = take();
                    code = (code << 4) | (h >= '0' && h <= '9' ? h - '0'
                        : h >= 'a' && h <= 'f' ? h - 'a' + 10 : h - 'A' + 10);
                }
                if (code <= 0x7F) o.push_back(static_cast<char>(code));
                else if (code <= 0x7FF) {
                    o.push_back(static_cast<char>(0xC0 | (code >> 6)));
                    o.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                } else {
                    o.push_back(static_cast<char>(0xE0 | (code >> 12)));
                    o.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
                    o.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                }
            } else {
                const char* m = "\"\\bfnrt/";
                const char* r = "\"\\bfnrt/";
                const char* p = strchr(m, e);
                o.push_back(p ? r[p - m] : e);
            }
        }
        throw std::runtime_error("str");
    }

    JsonValue num() {
        size_t b = i;
        if (peek() == '-') ++i;
        if (peek() == '0') ++i;
        else while (std::isdigit(static_cast<unsigned char>(peek()))) ++i;
        bool fl = false;
        if (peek() == '.') { fl = true; ++i; while (std::isdigit(static_cast<unsigned char>(peek()))) ++i; }
        if (peek() == 'e' || peek() == 'E') {
            fl = true; ++i;
            if (peek() == '+' || peek() == '-') ++i;
            while (std::isdigit(static_cast<unsigned char>(peek()))) ++i;
        }
        std::string t = s.substr(b, i - b);
        if (!fl) {
            int64_t v = 0;
            if (std::from_chars(t.data(), t.data() + t.size(), v).ec == std::errc()) {
                return JsonValue::make_int(v);
            }
        }
        double d = 0;
        if (std::from_chars(t.data(), t.data() + t.size(), d).ec != std::errc()) {
            throw std::runtime_error("num");
        }
        return JsonValue::make_double(d);
    }

    JsonValue val() {
        ws();
        char c = peek();
        if (c == '"') return JsonValue::make_string(str());
        if (c == '{') return obj();
        if (c == '[') return arr();
        if (c == 't' && s.compare(i, 4, "true") == 0) { i += 4; return JsonValue::make_bool(true); }
        if (c == 'f' && s.compare(i, 5, "false") == 0) { i += 5; return JsonValue::make_bool(false); }
        if (c == 'n' && s.compare(i, 4, "null") == 0) { i += 4; return JsonValue::make_null(); }
        if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) return num();
        throw std::runtime_error("tok");
    }

    JsonValue arr() {
        take();
        ws();
        std::vector<JsonValue> a;
        if (peek() == ']') { take(); return JsonValue::make_array(std::move(a)); }
        while (true) {
            a.push_back(val());
            ws();
            char c = take();
            if (c == ']') break;
            if (c != ',') throw std::runtime_error("arr");
            ws();
        }
        return JsonValue::make_array(std::move(a));
    }

    JsonValue obj() {
        take();
        ws();
        std::map<std::string, JsonValue> o;
        if (peek() == '}') { take(); return JsonValue::make_object(std::move(o)); }
        while (true) {
            ws();
            std::string k = str();
            ws();
            if (take() != ':') throw std::runtime_error("obj");
            o.emplace(std::move(k), val());
            ws();
            char c = take();
            if (c == '}') break;
            if (c != ',') throw std::runtime_error("obj");
            ws();
        }
        return JsonValue::make_object(std::move(o));
    }
};

void esc(std::string& o, const std::string& s) {
    o.push_back('"');
    for (unsigned char c : s) {
        if (c == '"') o += "\\\"";
        else if (c == '\\') o += "\\\\";
        else if (c == '\b') o += "\\b";
        else if (c == '\f') o += "\\f";
        else if (c == '\n') o += "\\n";
        else if (c == '\r') o += "\\r";
        else if (c == '\t') o += "\\t";
        else if (c < 0x20) { char b[8]; std::snprintf(b, 8, "\\u%04x", c); o += b; }
        else o.push_back(static_cast<char>(c));
    }
    o.push_back('"');
}

void canon(std::string& o, const JsonValue& v) {
    switch (v.type) {
        case JsonValue::Type::Null: o += "null"; break;
        case JsonValue::Type::Bool: o += v.bool_val ? "true" : "false"; break;
        case JsonValue::Type::Int: o += std::to_string(v.int_val); break;
        case JsonValue::Type::Double: {
            std::ostringstream ss;
            ss << std::setprecision(17) << v.double_val;
            std::string t = ss.str();
            if (t.find_first_of(".eE") == std::string::npos) t += ".0";
            o += t;
            break;
        }
        case JsonValue::Type::String: esc(o, v.str_val); break;
        case JsonValue::Type::Array:
            o.push_back('[');
            for (size_t n = 0; n < v.arr_val.size(); ++n) {
                if (n) o.push_back(',');
                canon(o, v.arr_val[n]);
            }
            o.push_back(']');
            break;
        case JsonValue::Type::Object:
            o.push_back('{');
            for (auto it = v.obj_val.begin(); it != v.obj_val.end(); ++it) {
                if (it != v.obj_val.begin()) o.push_back(',');
                esc(o, it->first);
                o.push_back(':');
                canon(o, it->second);
            }
            o.push_back('}');
            break;
    }
}

}  // namespace

JsonValue JsonValue::make_null() { return {}; }
JsonValue JsonValue::make_bool(bool v) { JsonValue j; j.type = Type::Bool; j.bool_val = v; return j; }
JsonValue JsonValue::make_int(int64_t v) { JsonValue j; j.type = Type::Int; j.int_val = v; return j; }
JsonValue JsonValue::make_double(double v) { JsonValue j; j.type = Type::Double; j.double_val = v; return j; }
JsonValue JsonValue::make_string(std::string v) { JsonValue j; j.type = Type::String; j.str_val = std::move(v); return j; }
JsonValue JsonValue::make_array(std::vector<JsonValue> v) { JsonValue j; j.type = Type::Array; j.arr_val = std::move(v); return j; }
JsonValue JsonValue::make_object(std::map<std::string, JsonValue> v) { JsonValue j; j.type = Type::Object; j.obj_val = std::move(v); return j; }

const JsonValue* JsonValue::get(const std::string& key) const {
    if (type != Type::Object) return nullptr;
    auto it = obj_val.find(key);
    return it == obj_val.end() ? nullptr : &it->second;
}

JsonValue* JsonValue::get(const std::string& key) {
    if (type != Type::Object) return nullptr;
    auto it = obj_val.find(key);
    return it == obj_val.end() ? nullptr : &it->second;
}

std::optional<JsonValue> parse_json(const std::string& text) {
    try {
        Parser p{text};
        JsonValue r = p.val();
        p.ws();
        return p.i == text.size() ? std::optional<JsonValue>{std::move(r)} : std::nullopt;
    } catch (...) {
        return std::nullopt;
    }
}

std::string canonical_json(const JsonValue& value) {
    std::string o;
    canon(o, value);
    return o;
}
