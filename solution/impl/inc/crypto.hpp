#pragma once

#include <cstdint>
#include <string>
#include <vector>

std::string sha256_hex(const std::vector<uint8_t>& data);
std::string sha256_hex(const std::string& data);

bool hex_decode(const std::string& hex, std::vector<uint8_t>& out);
bool verify_ed25519(const std::string& pub_hex,
                    const std::vector<uint8_t>& message,
                    const std::string& sig_hex);
