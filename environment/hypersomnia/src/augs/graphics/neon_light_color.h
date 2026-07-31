#pragma once
#include "augs/graphics/rgba.h"

struct neon_light_color {
	// GEN INTROSPECTOR struct neon_light_color
	rgba color;
	float alpha_multiplier = 1.0f;
	// END GEN INTROSPECTOR

	neon_light_color() = default;
	neon_light_color(const rgba& c) : color(c), alpha_multiplier(1.0f) {}

	bool operator==(const neon_light_color&) const = default;
};
