#pragma once
#include <optional>
#include "augs/math/vec2.h"

/*
	Combat behavior.
	Bot is engaged in combat with an enemy target.
	
	The combat_target tracking (who we're fighting, timeouts, last known positions)
	is handled by ai_target_tracking in arena_mode_ai_state, NOT here.
	
	This struct only tracks internal combat behavior state like:
	- Whether we've dashed at the last seen target position
	- Whether we've dashed at the last known target position
*/

struct ai_behavior_combat {
	// GEN INTROSPECTOR struct ai_behavior_combat
	std::optional<vec2> dashed_to_visual_pos;
	std::optional<vec2> dashed_to_known_pos;
	/*
		Once the bot has navigated to last_known_pos with no visual contact,
		find_closest_cover picks a hiding spot.  The result is cached here so
		the navigation request stays stable while moving toward it; on each
		arrival a new cover is picked using the previous one as a secondary
		danger so the bot keeps relocating until combat times out.

		last_known_time_at_cover_calc is combat_target.last_known_time_secs
		captured at the moment cover was computed.  When the tracker's
		last_known_time_secs advances past it (a new sight or sound came in,
		even if the position happens to coincide) the cover is stale and
		should be abandoned in favor of investigating the new info.
	*/
	std::optional<vec2> searching_cover_pos;
	real32 last_known_time_at_cover_calc = 0.0f;
	// END GEN INTROSPECTOR

	bool has_dashed_to_visual_pos(const vec2 pos) const {
		if (!dashed_to_visual_pos.has_value()) {
			return false;
		}

		constexpr float EPSILON = 10.0f;
		return (*dashed_to_visual_pos - pos).length() < EPSILON;
	}

	bool has_dashed_to_known_pos(const vec2 pos) const {
		if (!dashed_to_known_pos.has_value()) {
			return false;
		}

		constexpr float EPSILON = 10.0f;
		return (*dashed_to_known_pos - pos).length() < EPSILON;
	}

	void mark_dashed_to_visual_pos(const vec2 pos) {
		dashed_to_visual_pos = pos;
	}

	void mark_dashed_to_known_pos(const vec2 pos) {
		dashed_to_known_pos = pos;
	}

	bool operator==(const ai_behavior_combat&) const = default;

	void process(ai_behavior_process_ctx&) {}
};
