#include "crypto.hpp"

#include <iomanip>
#include <openssl/evp.h>
#include <sstream>

namespace {

std::string bytes_to_hex(const unsigned char* data, size_t len) {
    std::ostringstream oss;
    oss << std::hex << std::setfill('0');
    for (size_t i = 0; i < len; ++i) {
        oss << std::setw(2) << static_cast<int>(data[i]);
    }
    return oss.str();
}

}  // namespace

std::string sha256_hex(const std::vector<uint8_t>& data) {
    unsigned char hash[EVP_MAX_MD_SIZE];
    unsigned int hash_len = 0;
    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) return "";
    if (EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) != 1 ||
        EVP_DigestUpdate(ctx, data.data(), data.size()) != 1 ||
        EVP_DigestFinal_ex(ctx, hash, &hash_len) != 1) {
        EVP_MD_CTX_free(ctx);
        return "";
    }
    EVP_MD_CTX_free(ctx);
    return bytes_to_hex(hash, hash_len);
}

std::string sha256_hex(const std::string& data) {
    return sha256_hex(std::vector<uint8_t>(data.begin(), data.end()));
}

bool hex_decode(const std::string& hex, std::vector<uint8_t>& out) {
    if (hex.size() % 2 != 0) return false;
    out.clear();
    out.reserve(hex.size() / 2);
    auto nybble = [](char c) -> int {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t i = 0; i < hex.size(); i += 2) {
        int hi = nybble(hex[i]);
        int lo = nybble(hex[i + 1]);
        if (hi < 0 || lo < 0) return false;
        out.push_back(static_cast<uint8_t>((hi << 4) | lo));
    }
    return true;
}

bool verify_ed25519(const std::string& pub_hex,
                    const std::vector<uint8_t>& message,
                    const std::string& sig_hex) {
    std::vector<uint8_t> pub_bytes;
    std::vector<uint8_t> sig_bytes;
    if (!hex_decode(pub_hex, pub_bytes) || pub_bytes.size() != 32) {
        return false;
    }
    if (!hex_decode(sig_hex, sig_bytes) || sig_bytes.size() != 64) {
        return false;
    }

    EVP_PKEY* pkey = EVP_PKEY_new_raw_public_key(
        EVP_PKEY_ED25519, nullptr, pub_bytes.data(), pub_bytes.size());
    if (!pkey) return false;

    EVP_MD_CTX* ctx = EVP_MD_CTX_new();
    if (!ctx) {
        EVP_PKEY_free(pkey);
        return false;
    }

    bool ok = false;
    if (EVP_DigestVerifyInit(ctx, nullptr, nullptr, nullptr, pkey) == 1 &&
        EVP_DigestVerify(ctx, sig_bytes.data(), sig_bytes.size(),
                         message.data(), message.size()) == 1) {
        ok = true;
    }

    EVP_MD_CTX_free(ctx);
    EVP_PKEY_free(pkey);
    return ok;
}
