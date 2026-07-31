/*
	Rebuilds what the Hypersomnia master server was publishing at the end of a
	recorded packet journal.

	Everything about the wire format below was read out of the game sources:

	- augs/readwrite/byte_readwrite.h decides how each field goes on the wire.
	  A variant writes a uint8 index first. A type that is trivially copyable
	  and is not a container goes out as its raw bytes, padding included. A type
	  with begin() and end() goes out as a uint32 count followed by its
	  elements. Anything else, including everything that opts into
	  force_read_field_by_field, is walked field by field in declaration order.
	- application/masterserver/masterserver_requests.h fixes the request order.
	- application/masterserver/server_heartbeat.h fixes the heartbeat fields.
	  Only what sits between the GEN INTROSPECTOR markers is serialized, so the
	  trailing cached_time_to_event is not on the wire.
	- augs/misc/constant_size_string.h is unsigned length plus char[N + 1], so a
	  nickname nested inside a raw player record occupies a fixed 52 bytes,
	  while a string reached field by field is a uint32 length plus its chars.
	- 3rdparty/yojimbo is not vendored in this checkout, so netcode_address_t
	  comes from the published yojimbo repository: the address union first, then
	  the port, then the type, twenty bytes once padded.
	- application/masterserver/masterserver.cpp is the replay itself, and
	  application/setups/server/server_setup.cpp holds is_valid, get_location_id
	  and the rest of the per heartbeat rules.
*/

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <map>
#include <memory>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

#include <netdb.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <netinet/in.h>
#include <arpa/inet.h>

namespace {

struct input_error : std::runtime_error {
	using std::runtime_error::runtime_error;
};

struct wire_error : std::runtime_error {
	using std::runtime_error::runtime_error;
};

/* ------------------------------------------------------------------ files */

std::string read_file(const std::string& path) {
	auto* handle = std::fopen(path.c_str(), "rb");

	if (handle == nullptr) {
		throw input_error("cannot open " + path);
	}

	std::string out;
	char buffer[65536];

	while (const auto got = std::fread(buffer, 1, sizeof(buffer), handle)) {
		out.append(buffer, got);
	}

	std::fclose(handle);
	return out;
}

void write_file(const std::string& path, const std::string& content) {
	auto* handle = std::fopen(path.c_str(), "wb");

	if (handle == nullptr) {
		throw input_error("cannot write " + path);
	}

	std::fwrite(content.data(), 1, content.size(), handle);
	std::fclose(handle);
}

void make_directories(const std::string& path) {
	std::string partial;

	for (std::size_t i = 0; i <= path.size(); ++i) {
		if (i == path.size() || path[i] == '/') {
			if (partial.size() > 0) {
				::mkdir(partial.c_str(), 0755);
			}
		}

		if (i < path.size()) {
			partial += path[i];
		}
	}
}

/* ------------------------------------------------------------------- json */

struct json_value {
	enum class kind { null, boolean, number, string, array, object };

	kind type = kind::null;
	bool boolean = false;
	double number = 0.0;
	std::string string;
	std::vector<json_value> array;
	std::vector<std::pair<std::string, json_value>> object;

	const json_value* find(const std::string& key) const {
		for (const auto& entry : object) {
			if (entry.first == key) {
				return std::addressof(entry.second);
			}
		}

		return nullptr;
	}
};

class json_parser {
public:
	explicit json_parser(const std::string& source) : text(source) {}

	json_value parse() {
		const auto out = parse_value();
		skip_space();

		if (pos != text.size()) {
			throw input_error("trailing json");
		}

		return out;
	}

private:
	const std::string& text;
	std::size_t pos = 0;

	void skip_space() {
		while (pos < text.size() && std::isspace(static_cast<unsigned char>(text[pos]))) {
			++pos;
		}
	}

	char peek() {
		skip_space();

		if (pos >= text.size()) {
			throw input_error("unexpected end of json");
		}

		return text[pos];
	}

	void expect(const char c) {
		if (peek() != c) {
			throw input_error(std::string("expected ") + c);
		}

		++pos;
	}

	bool literal(const char* word) {
		const auto length = std::strlen(word);

		if (text.compare(pos, length, word) == 0) {
			pos += length;
			return true;
		}

		return false;
	}

	std::string parse_string() {
		expect('"');
		std::string out;

		while (pos < text.size()) {
			const auto c = text[pos++];

			if (c == '"') {
				return out;
			}

			if (c != '\\') {
				out += c;
				continue;
			}

			if (pos >= text.size()) {
				break;
			}

			const auto escape = text[pos++];

			switch (escape) {
				case 'n': out += '\n'; break;
				case 't': out += '\t'; break;
				case 'r': out += '\r'; break;
				case 'b': out += '\b'; break;
				case 'f': out += '\f'; break;
				case '/': out += '/'; break;
				case '\\': out += '\\'; break;
				case '"': out += '"'; break;
				case 'u': {
					if (pos + 4 > text.size()) {
						throw input_error("bad \\u escape");
					}

					auto code = static_cast<uint32_t>(std::stoul(text.substr(pos, 4), nullptr, 16));
					pos += 4;

					if (code >= 0xD800 && code <= 0xDBFF && text.compare(pos, 2, "\\u") == 0) {
						const auto low = static_cast<uint32_t>(std::stoul(text.substr(pos + 2, 4), nullptr, 16));

						if (low >= 0xDC00 && low <= 0xDFFF) {
							code = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00);
							pos += 6;
						}
					}

					append_utf8(out, code);
					break;
				}
				default:
					throw input_error("bad escape");
			}
		}

		throw input_error("unterminated string");
	}

	static void append_utf8(std::string& out, const uint32_t code) {
		if (code < 0x80) {
			out += static_cast<char>(code);
		}
		else if (code < 0x800) {
			out += static_cast<char>(0xC0 | (code >> 6));
			out += static_cast<char>(0x80 | (code & 0x3F));
		}
		else if (code < 0x10000) {
			out += static_cast<char>(0xE0 | (code >> 12));
			out += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
			out += static_cast<char>(0x80 | (code & 0x3F));
		}
		else {
			out += static_cast<char>(0xF0 | (code >> 18));
			out += static_cast<char>(0x80 | ((code >> 12) & 0x3F));
			out += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
			out += static_cast<char>(0x80 | (code & 0x3F));
		}
	}

	json_value parse_value() {
		const auto c = peek();

		if (c == '{') {
			++pos;
			json_value out;
			out.type = json_value::kind::object;

			if (peek() == '}') {
				++pos;
				return out;
			}

			while (true) {
				const auto key = parse_string();
				expect(':');
				out.object.emplace_back(key, parse_value());

				if (peek() == ',') {
					++pos;
					continue;
				}

				expect('}');
				return out;
			}
		}

		if (c == '[') {
			++pos;
			json_value out;
			out.type = json_value::kind::array;

			if (peek() == ']') {
				++pos;
				return out;
			}

			while (true) {
				out.array.emplace_back(parse_value());

				if (peek() == ',') {
					++pos;
					continue;
				}

				expect(']');
				return out;
			}
		}

		if (c == '"') {
			json_value out;
			out.type = json_value::kind::string;
			out.string = parse_string();
			return out;
		}

		if (literal("true") || literal("True")) {
			json_value out;
			out.type = json_value::kind::boolean;
			out.boolean = true;
			return out;
		}

		if (literal("false") || literal("False")) {
			json_value out;
			out.type = json_value::kind::boolean;
			return out;
		}

		if (literal("null")) {
			return json_value();
		}

		std::size_t used = 0;
		json_value out;
		out.type = json_value::kind::number;
		out.number = std::stod(text.substr(pos), &used);
		pos += used;
		return out;
	}
};

std::string json_escape(const std::string& in) {
	std::string out;

	for (const auto raw : in) {
		const auto c = static_cast<unsigned char>(raw);

		switch (c) {
			case '"': out += "\\\""; break;
			case '\\': out += "\\\\"; break;
			case '\n': out += "\\n"; break;
			case '\t': out += "\\t"; break;
			case '\r': out += "\\r"; break;
			case '\b': out += "\\b"; break;
			case '\f': out += "\\f"; break;
			default:
				if (c < 0x20) {
					char buffer[8];
					std::snprintf(buffer, sizeof(buffer), "\\u%04x", c);
					out += buffer;
				}
				else {
					out += static_cast<char>(c);
				}
		}
	}

	return out;
}

/* ------------------------------------------------------------------- wire */

constexpr std::size_t max_server_name_length = 60;
constexpr std::size_t max_arena_name_length = 30;
constexpr std::size_t max_game_mode_name_length = 30;
constexpr std::size_t max_version_length = 20;
constexpr std::size_t max_nickname_length = 40;
constexpr std::size_t max_signalling_message_length = 4096;

constexpr std::size_t player_info_size = 52;
constexpr std::size_t netcode_address_size = 20;
constexpr uint8_t netcode_address_ipv4 = 1;

struct address {
	uint32_t ip = 0;
	uint16_t port = 0;

	/* the four octets in the order they are written, then the port */
	bool operator<(const address& b) const {
		const auto* left = reinterpret_cast<const unsigned char*>(std::addressof(ip));
		const auto* right = reinterpret_cast<const unsigned char*>(std::addressof(b.ip));

		for (int i = 0; i < 4; ++i) {
			if (left[i] != right[i]) {
				return left[i] < right[i];
			}
		}

		return port < b.port;
	}

	bool operator==(const address& b) const {
		return ip == b.ip && port == b.port;
	}

	std::string to_string() const {
		in_addr raw;
		raw.s_addr = ip;
		char buffer[INET_ADDRSTRLEN];
		::inet_ntop(AF_INET, &raw, buffer, sizeof(buffer));

		return std::string(buffer) + ":" + std::to_string(port);
	}

	std::string ip_string() const {
		in_addr raw;
		raw.s_addr = ip;
		char buffer[INET_ADDRSTRLEN];
		::inet_ntop(AF_INET, &raw, buffer, sizeof(buffer));

		return buffer;
	}
};

class byte_reader {
public:
	byte_reader(const char* const data, const std::size_t size) : begin(data), left(size) {}

	const char* take(const std::size_t n) {
		if (n > left) {
			throw wire_error("read past the end of the stream");
		}

		const auto* out = begin;
		begin += n;
		left -= n;
		return out;
	}

	uint8_t u8() {
		return static_cast<uint8_t>(*take(1));
	}

	bool boolean() {
		return u8() != 0;
	}

	uint16_t u16() {
		uint16_t out = 0;
		std::memcpy(&out, take(2), 2);
		return out;
	}

	uint32_t u32() {
		uint32_t out = 0;
		std::memcpy(&out, take(4), 4);
		return out;
	}

	int32_t i32() {
		int32_t out = 0;
		std::memcpy(&out, take(4), 4);
		return out;
	}

	int64_t i64() {
		int64_t out = 0;
		std::memcpy(&out, take(8), 8);
		return out;
	}

	double f64() {
		double out = 0.0;
		std::memcpy(&out, take(8), 8);
		return out;
	}

	std::string constant_size_string(const std::size_t capacity) {
		const auto length = u32();

		if (length > capacity) {
			throw wire_error("string longer than its constant capacity");
		}

		const auto* chars = take(length);
		return std::string(chars, length);
	}

	address netcode_address() {
		const auto* raw = take(netcode_address_size);
		address out;
		std::memcpy(&out.ip, raw, 4);
		std::memcpy(&out.port, raw + 16, 2);

		if (static_cast<uint8_t>(raw[18]) != netcode_address_ipv4) {
			throw wire_error("only IPv4 addresses are supported");
		}

		return out;
	}

private:
	const char* begin;
	std::size_t left;
};

struct player_info {
	std::string nickname;
	uint8_t score = 0;
	uint8_t deaths = 0;
};

struct heartbeat {
	std::string server_name;
	std::string current_arena;
	std::string game_mode;
	uint8_t num_online_humans = 0;
	uint8_t num_online = 0;
	uint8_t server_slots = 0;
	std::optional<address> internal_network_address;
	uint8_t nat_type = 0;
	int32_t nat_port_delta = 0;
	uint16_t predicted_next_port = 0;
	bool suppress_new_community_server_webhook = false;
	bool show_on_server_list = true;
	std::string server_version;
	bool is_editor_playtesting_server = false;
	uint8_t score_resistance = 0;
	uint8_t score_metropolis = 0;
	std::vector<player_info> players_resistance;
	std::vector<player_info> players_metropolis;
	std::vector<player_info> players_spectating;
	bool require_authentication = false;
	uint8_t ranked_state = 0;
	bool require_password = false;

	/* server_setup.cpp, together with is_nickname_valid_characters */
	bool is_valid() const {
		const auto spaces = std::count(server_name.begin(), server_name.end(), ' ');

		if (spaces == static_cast<long>(server_name.size())) {
			return false;
		}

		for (const auto c : server_name) {
			if (c == '\0') {
				return false;
			}

			if (std::isspace(static_cast<unsigned char>(c)) && c != ' ') {
				return false;
			}
		}

		return !server_name.empty() && !current_arena.empty() && !game_mode.empty();
	}

	bool is_ranked_server() const {
		return ranked_state != 0;
	}

	/* num_online == server_slots + (num_online - num_online_humans) */
	bool is_full() const {
		return num_online == server_slots + (num_online - num_online_humans);
	}

	std::string get_location_id() const {
		static const std::vector<std::pair<std::string, std::string>> table = {
			{ "[AU]", "au" },
			{ "[NL]", "nl" },
			{ "[PL]", "pl" },
			{ "[US]", "us-central" },
			{ "[RU]", "ru" },
			{ "[DE]", "de" },
			{ "[CH]", "ch" },
			{ "[FI]", "fi" }
		};

		for (const auto& entry : table) {
			if (server_name.compare(0, entry.first.size(), entry.first) == 0) {
				return entry.second;
			}
		}

		return "";
	}
};

std::vector<player_info> read_players(byte_reader& reader) {
	const auto count = reader.u32();

	if (count > 32) {
		throw wire_error("more players than the constant capacity");
	}

	std::vector<player_info> out;

	for (uint32_t i = 0; i < count; ++i) {
		const auto* raw = reader.take(player_info_size);
		uint32_t length = 0;
		std::memcpy(&length, raw, 4);

		if (length > max_nickname_length) {
			throw wire_error("nickname longer than its constant capacity");
		}

		player_info player;
		player.nickname.assign(raw + 4, length);
		player.score = static_cast<uint8_t>(raw[48]);
		player.deaths = static_cast<uint8_t>(raw[49]);
		out.emplace_back(std::move(player));
	}

	return out;
}

enum class request_kind {
	heartbeat,
	tell_me_my_address,
	goodbye,
	dummy_int,
	dummy_float,
	webrtc_signalling
};

struct request {
	request_kind kind = request_kind::heartbeat;
	struct heartbeat beat;
};

request decode_request(const std::string& payload) {
	byte_reader reader(payload.data(), payload.size());
	request out;

	switch (reader.u8()) {
		case 0: {
			out.kind = request_kind::heartbeat;
			auto& beat = out.beat;
			beat.server_name = reader.constant_size_string(max_server_name_length);
			beat.current_arena = reader.constant_size_string(max_arena_name_length);
			beat.game_mode = reader.constant_size_string(max_game_mode_name_length);
			beat.num_online_humans = reader.u8();
			beat.num_online = reader.u8();
			beat.server_slots = reader.u8();

			if (reader.boolean()) {
				beat.internal_network_address = reader.netcode_address();
			}

			beat.nat_type = reader.u8();
			beat.nat_port_delta = reader.i32();
			beat.predicted_next_port = reader.u16();
			beat.suppress_new_community_server_webhook = reader.boolean();
			beat.show_on_server_list = reader.boolean();
			beat.server_version = reader.constant_size_string(max_version_length);
			beat.is_editor_playtesting_server = reader.boolean();
			beat.score_resistance = reader.u8();
			beat.score_metropolis = reader.u8();
			beat.players_resistance = read_players(reader);
			beat.players_metropolis = read_players(reader);
			beat.players_spectating = read_players(reader);
			beat.require_authentication = reader.boolean();
			beat.ranked_state = reader.u8();
			beat.require_password = reader.boolean();
			return out;
		}
		case 1:
			out.kind = request_kind::tell_me_my_address;
			reader.f64();
			return out;
		case 2:
			/* an empty struct is trivially copyable, so augs writes one byte */
			out.kind = request_kind::goodbye;
			reader.u8();
			return out;
		case 3:
			out.kind = request_kind::dummy_int;
			reader.i32();
			return out;
		case 4:
			out.kind = request_kind::dummy_float;
			reader.u32();
			return out;
		case 5:
			out.kind = request_kind::webrtc_signalling;
			reader.i64();
			reader.constant_size_string(max_signalling_message_length);
			return out;
		default:
			throw wire_error("unknown request kind");
	}
}

/* ---------------------------------------------------------------- journal */

struct record {
	double arrived_at = 0.0;
	address from;
	std::string payload;
};

struct journal {
	double window_start = 0.0;
	double window_end = 0.0;
	std::vector<record> records;
};

journal read_journal(const std::string& path) {
	const auto blob = read_file(path);

	if (blob.size() < 28 || blob.compare(0, 8, "HMSJRNL1") != 0) {
		throw input_error("bad journal magic");
	}

	journal out;
	uint32_t count = 0;
	std::memcpy(&count, blob.data() + 8, 4);
	std::memcpy(&out.window_start, blob.data() + 12, 8);
	std::memcpy(&out.window_end, blob.data() + 20, 8);

	if (out.window_end < out.window_start) {
		throw input_error("journal window ends before it starts");
	}

	std::size_t pos = 28;
	auto previous = out.window_start;

	for (uint32_t i = 0; i < count; ++i) {
		if (pos + 17 > blob.size()) {
			throw input_error("truncated journal record");
		}

		record next;
		std::memcpy(&next.arrived_at, blob.data() + pos, 8);

		if (static_cast<uint8_t>(blob[pos + 8]) != 4) {
			throw input_error("journal record is not IPv4");
		}

		std::memcpy(&next.from.ip, blob.data() + pos + 9, 4);
		std::memcpy(&next.from.port, blob.data() + pos + 13, 2);
		uint16_t length = 0;
		std::memcpy(&length, blob.data() + pos + 15, 2);
		pos += 17;

		if (pos + length > blob.size()) {
			throw input_error("truncated journal payload");
		}

		next.payload.assign(blob.data() + pos, length);
		pos += length;

		if (next.arrived_at < previous || next.arrived_at > out.window_end) {
			throw input_error("journal timestamps out of order");
		}

		previous = next.arrived_at;
		out.records.emplace_back(std::move(next));
	}

	if (pos != blob.size()) {
		throw input_error("trailing bytes in the journal");
	}

	return out;
}

/* --------------------------------------------------------- external facts */

std::string to_lowercase(std::string in) {
	for (auto& c : in) {
		c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
	}

	return in;
}

std::vector<std::pair<std::string, std::set<uint32_t>>> resolve_official_hosts(
	const std::vector<std::string>& hosts
) {
	std::vector<std::pair<std::string, std::set<uint32_t>>> out;

	for (const auto& host : hosts) {
		addrinfo hints;
		std::memset(&hints, 0, sizeof(hints));
		hints.ai_family = AF_INET;
		hints.ai_socktype = SOCK_STREAM;

		addrinfo* result = nullptr;

		if (::getaddrinfo(host.c_str(), nullptr, &hints, &result) != 0) {
			throw input_error("cannot resolve " + host);
		}

		std::set<uint32_t> addresses;

		for (auto* p = result; p != nullptr; p = p->ai_next) {
			if (p->ai_family == AF_INET) {
				const auto* v4 = reinterpret_cast<const sockaddr_in*>(p->ai_addr);
				addresses.insert(v4->sin_addr.s_addr);
			}
		}

		::freeaddrinfo(result);

		if (addresses.empty()) {
			throw input_error("no address for " + host);
		}

		out.emplace_back(host, std::move(addresses));
	}

	return out;
}

/*
	headless_map_catalogue.cpp asks the provider for its listing with
	"?format=json" appended, which is the only form that answers with the index
	rather than with the web page.
*/
std::map<std::string, std::string> fetch_catalogue(const std::string& provider) {
	const auto command = "curl -fsS --max-time 60 '" + provider + "?format=json'";
	auto* pipe = ::popen(command.c_str(), "r");

	if (pipe == nullptr) {
		throw input_error("cannot reach the arena catalogue");
	}

	std::string body;
	char buffer[8192];

	while (const auto got = std::fread(buffer, 1, sizeof(buffer), pipe)) {
		body.append(buffer, got);
	}

	if (::pclose(pipe) != 0 || body.empty()) {
		throw input_error("the arena catalogue could not be downloaded");
	}

	const auto parsed = json_parser(body).parse();

	if (parsed.type != json_value::kind::array) {
		throw input_error("unexpected arena catalogue shape");
	}

	std::map<std::string, std::string> out;

	for (const auto& entry : parsed.array) {
		const auto* name = entry.find("name");

		if (name == nullptr || name->type != json_value::kind::string) {
			continue;
		}

		const auto* author = entry.find("author");
		out[name->string] = author != nullptr && author->type == json_value::kind::string
			? author->string
			: std::string()
		;
	}

	return out;
}

/* ----------------------------------------------------------------- replay */

struct registration {
	double time_hosted = 0.0;
	double time_last_heartbeat = 0.0;
	uint32_t heartbeats = 0;
	heartbeat beat;
};

struct banlist {
	std::set<std::string> addresses;
	std::set<std::string> names;
};

/* masterserver.cpp splits every line on its first space */
banlist load_banlist(const std::string& path) {
	banlist out;
	std::string content;

	try {
		content = read_file(path);
	}
	catch (const input_error&) {
		return out;
	}

	std::size_t start = 0;

	while (start <= content.size()) {
		auto stop = content.find('\n', start);

		if (stop == std::string::npos) {
			stop = content.size();
		}

		const auto line = content.substr(start, stop - start);
		start = stop + 1;

		if (line.empty()) {
			continue;
		}

		const auto space = line.find(' ');
		out.addresses.insert(line.substr(0, space));

		if (space != std::string::npos) {
			out.names.insert(to_lowercase(line.substr(space + 1)));
		}
	}

	return out;
}

std::map<address, registration> replay(
	const journal& source,
	const double timeout,
	const banlist& banned
) {
	std::map<address, registration> registry;

	auto expire = [&](const double now) {
		for (auto it = registry.begin(); it != registry.end(); ) {
			if (now - it->second.time_last_heartbeat >= timeout) {
				it = registry.erase(it);
			}
			else {
				++it;
			}
		}
	};

	for (const auto& next : source.records) {
		expire(next.arrived_at);

		if (banned.addresses.count(next.from.ip_string()) > 0) {
			continue;
		}

		request parsed;

		try {
			parsed = decode_request(next.payload);
		}
		catch (const wire_error&) {
			registry.erase(next.from);
			continue;
		}

		if (parsed.kind == request_kind::goodbye) {
			registry.erase(next.from);
			continue;
		}

		if (parsed.kind != request_kind::heartbeat) {
			continue;
		}

		if (banned.names.count(to_lowercase(parsed.beat.server_name)) > 0) {
			continue;
		}

		if (!parsed.beat.is_valid()) {
			continue;
		}

		const auto existing = registry.find(next.from);

		if (existing == registry.end()) {
			registration fresh;
			fresh.time_hosted = next.arrived_at;
			fresh.time_last_heartbeat = next.arrived_at;
			fresh.heartbeats = 1;
			fresh.beat = parsed.beat;
			registry.emplace(next.from, std::move(fresh));
		}
		else {
			existing->second.time_last_heartbeat = next.arrived_at;
			existing->second.heartbeats += 1;
			existing->second.beat = parsed.beat;
		}
	}

	expire(source.window_end);
	return registry;
}

/* ----------------------------------------------------------------- output */

struct listed_entry {
	address from;
	registration entry;
	std::string official_url;
	std::string webrtc_id;
	bool arena_in_catalogue = false;
	std::string arena_author;
};

/* masterserver.cpp: to_webrtc_alias over get_location_id */
std::string webrtc_alias(const heartbeat& beat) {
	auto location = beat.get_location_id();

	if (location == "us-central") {
		location = "us";
	}

	if (beat.is_ranked_server()) {
		location = "ranked-" + location;
	}

	const auto hash_at = beat.server_name.find('#');

	if (hash_at != std::string::npos) {
		const auto tail = beat.server_name.substr(hash_at + 1);

		try {
			std::size_t used = 0;
			const auto index = std::stoi(tail, &used);

			if (used > 0) {
				location += ":" + std::to_string(index);
			}
		}
		catch (const std::exception&) {
			/* typesafe_sscanf fails the whole match, so no suffix is added */
		}
	}

	return location;
}

std::vector<listed_entry> build_rows(
	const std::map<address, registration>& registry,
	const std::vector<std::pair<std::string, std::set<uint32_t>>>& official,
	const std::map<std::string, std::string>& catalogue
) {
	std::vector<listed_entry> rows;

	for (const auto& pair : registry) {
		if (!pair.second.beat.show_on_server_list) {
			continue;
		}

		listed_entry row;
		row.from = pair.first;
		row.entry = pair.second;

		for (const auto& host : official) {
			if (host.second.count(pair.first.ip) > 0) {
				row.official_url = host.first + ":" + std::to_string(pair.first.port);
				break;
			}
		}

		if (!row.official_url.empty()) {
			row.webrtc_id = webrtc_alias(pair.second.beat);
		}

		const auto found = catalogue.find(pair.second.beat.current_arena);

		if (found != catalogue.end()) {
			row.arena_in_catalogue = true;
			row.arena_author = found->second;
		}

		rows.emplace_back(std::move(row));
	}

	std::sort(rows.begin(), rows.end(), [](const listed_entry& a, const listed_entry& b) {
		return a.from < b.from;
	});

	return rows;
}

const char* nat_type_name(const uint8_t type) {
	static const char* names[] = {
		"PUBLIC_INTERNET",
		"PORT_PRESERVING_CONE",
		"CONE",
		"ADDRESS_SENSITIVE",
		"PORT_SENSITIVE",
		"UNKNOWN"
	};

	return type < 6 ? names[type] : "UNKNOWN";
}

std::string format_double(const double value) {
	char buffer[64];
	std::snprintf(buffer, sizeof(buffer), "%.6f", value);
	return buffer;
}

std::string render_players(const std::vector<player_info>& players, const std::string& indent) {
	if (players.empty()) {
		return "[]";
	}

	std::string out = "[\n";

	for (std::size_t i = 0; i < players.size(); ++i) {
		out += indent + "  {\n";
		out += indent + "    \"nickname\": \"" + json_escape(players[i].nickname) + "\",\n";
		out += indent + "    \"score\": " + std::to_string(players[i].score) + ",\n";
		out += indent + "    \"deaths\": " + std::to_string(players[i].deaths) + "\n";
		out += indent + "  }";
		out += i + 1 < players.size() ? ",\n" : "\n";
	}

	out += indent + "]";
	return out;
}

std::string render_json(const std::vector<listed_entry>& rows) {
	if (rows.empty()) {
		return "[]\n";
	}

	std::string out = "[\n";

	for (std::size_t i = 0; i < rows.size(); ++i) {
		const auto& row = rows[i];
		const auto& beat = row.entry.beat;
		const auto ip_string = row.from.to_string();
		const auto is_official = !row.official_url.empty();
		const auto spectating = beat.players_spectating.size();

		auto field = [&out](const std::string& key, const std::string& value) {
			out += "    \"" + key + "\": " + value + ",\n";
		};

		auto text = [](const std::string& value) {
			return "\"" + json_escape(value) + "\"";
		};

		out += "  {\n";
		field("name", text(beat.server_name));
		field("ip", text(ip_string));
		field("official_url", text(row.official_url));
		field("webrtc_id", text(row.webrtc_id));
		field("browser_connect_string", text(row.webrtc_id.empty() ? ip_string : row.webrtc_id));
		field("site_displayed_address", text(is_official ? row.official_url : ip_string));
		field("server_version", text(beat.server_version));
		field("is_official", is_official ? "true" : "false");
		field("is_ranked", is_official && beat.is_ranked_server() ? "true" : "false");
		field("nat", text(nat_type_name(beat.nat_type)));
		field("arena", text(beat.current_arena));
		field("arena_in_catalogue", row.arena_in_catalogue ? "true" : "false");
		field("arena_author", text(row.arena_author));
		field("game_mode", text(beat.game_mode));
		field("time_hosted", format_double(row.entry.time_hosted));
		field("time_last_heartbeat", format_double(row.entry.time_last_heartbeat));
		field("heartbeats_accepted", std::to_string(row.entry.heartbeats));
		field("slots", std::to_string(beat.server_slots));
		field("num_online_humans", std::to_string(beat.num_online_humans));
		field("num_playing", std::to_string(beat.num_online - spectating));
		field("num_spectating", std::to_string(spectating));
		field("score_resistance", std::to_string(beat.score_resistance));
		field("score_metropolis", std::to_string(beat.score_metropolis));

		if (beat.internal_network_address.has_value()) {
			field("internal_network_address", text(beat.internal_network_address->to_string()));
		}

		if (beat.is_editor_playtesting_server) {
			field("is_editor_playtesting_server", "true");
		}

		field("players_resistance", render_players(beat.players_resistance, "    "));
		field("players_metropolis", render_players(beat.players_metropolis, "    "));
		out += "    \"players_spectating\": " + render_players(beat.players_spectating, "    ") + "\n";
		out += i + 1 < rows.size() ? "  },\n" : "  }\n";
	}

	out += "]\n";
	return out;
}

void put_uvarint(std::string& out, uint64_t value) {
	while (true) {
		const auto byte = static_cast<uint8_t>(value & 0x7F);
		value >>= 7;

		if (value != 0) {
			out += static_cast<char>(byte | 0x80);
		}
		else {
			out += static_cast<char>(byte);
			return;
		}
	}
}

void put_svarint(std::string& out, const int32_t value) {
	const auto folded = (static_cast<uint32_t>(value) << 1) ^ static_cast<uint32_t>(value >> 31);
	put_uvarint(out, folded);
}

void put_u16(std::string& out, const uint16_t value) {
	out += static_cast<char>((value >> 8) & 0xFF);
	out += static_cast<char>(value & 0xFF);
}

void put_u32(std::string& out, const uint32_t value) {
	out += static_cast<char>((value >> 24) & 0xFF);
	out += static_cast<char>((value >> 16) & 0xFF);
	out += static_cast<char>((value >> 8) & 0xFF);
	out += static_cast<char>(value & 0xFF);
}

void put_f64(std::string& out, const double value) {
	uint64_t raw = 0;
	std::memcpy(&raw, &value, 8);

	for (int shift = 56; shift >= 0; shift -= 8) {
		out += static_cast<char>((raw >> shift) & 0xFF);
	}
}

void put_octets(std::string& out, const uint32_t ip) {
	const auto* bytes = reinterpret_cast<const unsigned char*>(std::addressof(ip));
	out.append(reinterpret_cast<const char*>(bytes), 4);
}

uint32_t crc32(const char* const data, const std::size_t size) {
	static uint32_t table[256];
	static bool ready = false;

	if (!ready) {
		for (uint32_t i = 0; i < 256; ++i) {
			auto acc = i;

			for (int bit = 0; bit < 8; ++bit) {
				acc = (acc >> 1) ^ ((acc & 1) ? 0xEDB88320u : 0u);
			}

			table[i] = acc;
		}

		ready = true;
	}

	uint32_t acc = 0xFFFFFFFFu;

	for (std::size_t i = 0; i < size; ++i) {
		acc = table[(acc ^ static_cast<unsigned char>(data[i])) & 0xFF] ^ (acc >> 8);
	}

	return acc ^ 0xFFFFFFFFu;
}

int64_t round_half_away(const double value) {
	return value < 0.0
		? -static_cast<int64_t>(-value + 0.5)
		: static_cast<int64_t>(value + 0.5)
	;
}

std::string render_snapshot(
	const std::vector<listed_entry>& rows,
	const double window_start,
	const double window_end
) {
	std::vector<std::string> table;
	std::map<std::string, uint32_t> index_of;

	auto intern = [&](const std::string& value) {
		const auto found = index_of.find(value);

		if (found != index_of.end()) {
			return found->second;
		}

		const auto index = static_cast<uint32_t>(table.size());
		index_of.emplace(value, index);
		table.emplace_back(value);
		return index;
	};

	std::string body;

	for (const auto& row : rows) {
		const auto& beat = row.entry.beat;
		const auto is_official = !row.official_url.empty();

		const auto name_index = intern(beat.server_name);
		const auto arena_index = intern(beat.current_arena);
		const auto mode_index = intern(beat.game_mode);
		const auto version_index = intern(beat.server_version);
		uint32_t official_index = 0;
		uint32_t webrtc_index = 0;

		if (is_official) {
			official_index = intern(row.official_url);
			webrtc_index = intern(row.webrtc_id);
		}

		std::vector<std::vector<uint32_t>> nicknames;

		for (const auto* team : {
			std::addressof(beat.players_resistance),
			std::addressof(beat.players_metropolis),
			std::addressof(beat.players_spectating)
		}) {
			std::vector<uint32_t> indices;

			for (const auto& player : *team) {
				indices.emplace_back(intern(player.nickname));
			}

			nicknames.emplace_back(std::move(indices));
		}

		uint8_t flags = 0;

		if (is_official) {
			flags |= 0x01;
		}

		if (is_official && beat.is_ranked_server()) {
			flags |= 0x02;
		}

		if (beat.internal_network_address.has_value()) {
			flags |= 0x04;
		}

		if (beat.is_editor_playtesting_server) {
			flags |= 0x08;
		}

		if (row.arena_in_catalogue) {
			flags |= 0x10;
		}

		if (beat.is_full()) {
			flags |= 0x20;
		}

		put_octets(body, row.from.ip);
		put_u16(body, row.from.port);
		body += static_cast<char>(flags);
		body += static_cast<char>(beat.nat_type);
		put_svarint(body, beat.nat_port_delta);
		put_u16(body, beat.predicted_next_port);
		put_uvarint(body, name_index);
		put_uvarint(body, arena_index);
		put_uvarint(body, mode_index);
		put_uvarint(body, version_index);

		if (is_official) {
			put_uvarint(body, official_index);
			put_uvarint(body, webrtc_index);
		}

		if (beat.internal_network_address.has_value()) {
			put_octets(body, beat.internal_network_address->ip);
			put_u16(body, beat.internal_network_address->port);
		}

		put_uvarint(body, static_cast<uint64_t>(
			round_half_away((window_end - row.entry.time_hosted) * 1000.0)));
		put_uvarint(body, static_cast<uint64_t>(
			round_half_away((window_end - row.entry.time_last_heartbeat) * 1000.0)));
		put_uvarint(body, row.entry.heartbeats);

		body += static_cast<char>(beat.server_slots);
		body += static_cast<char>(beat.num_online_humans);
		body += static_cast<char>(beat.num_online - beat.players_spectating.size());
		body += static_cast<char>(beat.players_spectating.size());
		body += static_cast<char>(beat.score_resistance);
		body += static_cast<char>(beat.score_metropolis);

		const std::vector<const std::vector<player_info>*> teams = {
			std::addressof(beat.players_resistance),
			std::addressof(beat.players_metropolis),
			std::addressof(beat.players_spectating)
		};

		for (std::size_t team = 0; team < teams.size(); ++team) {
			put_uvarint(body, teams[team]->size());

			for (std::size_t i = 0; i < teams[team]->size(); ++i) {
				put_uvarint(body, nicknames[team][i]);
				body += static_cast<char>((*teams[team])[i].score);
				body += static_cast<char>((*teams[team])[i].deaths);
			}
		}
	}

	std::string head = "HYPRSNAP";
	head += static_cast<char>(1);
	put_u16(head, static_cast<uint16_t>(rows.size()));
	put_f64(head, window_start);
	put_f64(head, window_end);
	put_u16(head, static_cast<uint16_t>(table.size()));

	for (const auto& value : table) {
		put_uvarint(head, value.size());
		head += value;
	}

	auto out = head + body;
	const auto digest = crc32(out.data() + 8, out.size() - 8);
	put_u32(out, digest);
	return out;
}

} // namespace

int main(const int argc, const char* const* const argv) try {
	if (argc != 4) {
		std::fprintf(stderr, "usage: mslist <journal> <config> <out-dir>\n");
		return 2;
	}

	const auto journal_path = std::string(argv[1]);
	const auto config_path = std::string(argv[2]);
	const auto out_dir = std::string(argv[3]);

	const auto config = json_parser(read_file(config_path)).parse();

	auto require = [&config](const char* key) {
		const auto* found = config.find(key);

		if (found == nullptr) {
			throw input_error(std::string("missing config key ") + key);
		}

		return found;
	};

	const auto timeout = require("server_entry_timeout_secs")->number;
	const auto provider = require("external_arena_files_provider")->string;
	const auto banlist_path = require("banlist_servers_path")->string;

	std::vector<std::string> hosts;

	for (const auto& host : require("official_hosts")->array) {
		hosts.emplace_back(host.string);
	}

	const auto source = read_journal(journal_path);
	const auto official = resolve_official_hosts(hosts);
	const auto catalogue = fetch_catalogue(provider);
	const auto banned = load_banlist(banlist_path);

	const auto registry = replay(source, timeout, banned);
	const auto rows = build_rows(registry, official, catalogue);

	const auto listing = render_json(rows);
	const auto snapshot = render_snapshot(rows, source.window_start, source.window_end);

	make_directories(out_dir);
	write_file(out_dir + "/server_list.json", listing);
	write_file(out_dir + "/snapshot.bin", snapshot);
	return 0;
}
catch (const std::exception& err) {
	std::fprintf(stderr, "mslist: %s\n", err.what());
	return 2;
}
