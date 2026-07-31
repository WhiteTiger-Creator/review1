#pragma once
#include "game/components/cascade_explosion_component.h"
#include "game/components/explosive_component.h"
#include "game/components/hand_fuse_component.h"
#include "game/components/movement_component.h"
#include "game/cosmos/for_each_entity.h"
#include "game/detail/explosive/like_explosive.h"
#include "game/detail/path_navigation/navigate_path.hpp"
#include "game/detail/pathfinding/pathfinding.h"
#include "game/enums/filters.h"
#include "game/modes/ai/ai_character_context.h"
#include "game/modes/ai/intents/calc_navigation_request.hpp"
#include "game/modes/ai/tasks/line_of_sight.hpp"

/*
	Emergency avoidance layer — danger (grenade) avoidance component.

	Called from the emergency avoidance layer (PHASE 8) alongside
	update_bot_avoidance. should_run_avoidance_update must be computed
	by the caller and shared between both avoidance functions.

	When active, danger avoidance has HIGHER priority than bot avoidance:
	it is applied last (after bot_avoidance) so its direction wins.

	State fields in arena_mode_ai_state:
	  danger_navigation_request  — target cover cell; nullopt = in cover or inactive
	  danger_navigation_time_left — seconds remaining; -1.0f = inactive

	Behaviour:
	  - Each scan tick (throttled by should_run_avoidance_update) the closest
	    visible thrown explosive is found and cover is recalculated.  This runs
	    even while a danger navigation is already active so the target stays
	    up-to-date as the grenade moves.
	  - When the bot reaches cover (path_completed on the danger path) the
	    request is cleared and the bot stands still until the timer expires or
	    a new visible threat is detected on the next scan tick.
	  - Reload-based cover-seeking is handled separately by take_cover.hpp.
*/

/*
	Extra time added to the grenade fuse time so the bot keeps avoiding
	even during the explosion itself.
*/
constexpr float EXPLOSION_BUFFER_SECS = 0.2f;

/*
	Returns the worst-case duration in seconds for one cascade_explosion_input:
	  max_num_explosions * max_interval_ms / 1000
	where the max values account for the random variation ranges.
	Returns 0 if the flavour_id is not set.
*/
inline float estimate_explosion_duration(
	const cosmos& cosm,
	const cascade_explosion_input& ci
) {
	if (!ci.flavour_id.is_set()) {
		return 0.0f;
	}

	float result = 0.0f;

	ci.flavour_id.dispatch([&](const auto typed_id) {
		const auto& cascade_def = cosm.get_flavour(typed_id).template get<invariants::cascade_explosion>();

		/*
			mult_variated is sampled as base ± (base * variation / 2),
			so the maximum is base * (1 + variation / 2).
		*/
		const auto max_interval_ms =
			cascade_def.explosion_interval_ms.value
			* (1.f + cascade_def.explosion_interval_ms.variation * 0.5f)
		;

		const auto max_num = static_cast<float>(ci.num_explosions.value + ci.num_explosions.variation);

		result = max_num * max_interval_ms / 1000.0f;
	});

	return result;
}

/*
	Estimates the total danger duration in seconds for an entity that is either:
	  - A thrown explosive (hand_fuse + explosive invariant): fuse remaining time
	    plus the longest cascade chain across all three cascade slots.
	  - An already-running cascade explosion entity: remaining explosions *
	    max interval per explosion.
	Returns 0 if the entity matches neither type.
*/
template <class E>
inline float estimate_danger_duration(
	const cosmos& cosm,
	const augs::stepped_clock& clk,
	const E& entity
) {
	/* Thrown explosive */
	if (const auto* fuse = entity.template find<components::hand_fuse>()) {
		const auto fuse_remaining_secs =
			std::max(0.0f, clk.get_remaining_ms(fuse->fuse_delay_ms, fuse->when_armed) / 1000.0f)
		;

		float cascade_duration = 0.0f;

		if (const auto* explosive = entity.template find<invariants::explosive>()) {
			for (const auto& ci : explosive->cascade) {
				cascade_duration = std::max(cascade_duration, ::estimate_explosion_duration(cosm, ci));
			}
		}

		return fuse_remaining_secs + cascade_duration + EXPLOSION_BUFFER_SECS;
	}

	/* Already-running cascade explosion entity */
	if (const auto* cascade_comp = entity.template find<components::cascade_explosion>()) {
		if (const auto* cascade_def = entity.template find<invariants::cascade_explosion>()) {
			const auto max_interval_ms =
				cascade_def->explosion_interval_ms.value
				* (1.f + cascade_def->explosion_interval_ms.variation * 0.5f)
			;

			const auto remaining_secs =
				static_cast<float>(cascade_comp->explosions_left) * max_interval_ms / 1000.0f
			;

			return remaining_secs + EXPLOSION_BUFFER_SECS;
		}
	}

	return 0.0f;
}

/*
	Estimates the blast radius in pixels that a danger entity can affect.
	For a thrown explosive this is the maximum of the direct explosion radius
	and all cascade explosion radii.  For a running cascade explosion entity
	it is the cascade flavour's explosion radius.
	Returns 0 if no explosive data is found.
*/
template <class E>
inline float estimate_danger_radius(const cosmos& cosm, const E& entity) {
	float result = 0.0f;

	if (const auto* explosive = entity.template find<invariants::explosive>()) {
		result = std::max(result, explosive->explosion.effective_radius);

		for (const auto& ci : explosive->cascade) {
			if (!ci.flavour_id.is_set()) {
				continue;
			}

			ci.flavour_id.dispatch([&](const auto typed_id) {
				const auto& cascade_def = cosm.get_flavour(typed_id).template get<invariants::cascade_explosion>();
				result = std::max(result, cascade_def.explosion.effective_radius);
			});
		}
	}

	if (const auto* cascade_def = entity.template find<invariants::cascade_explosion>()) {
		result = std::max(result, cascade_def->explosion.effective_radius);
	}

	return result;
}


inline bool update_danger_avoidance(
	const ai_character_context& ctx,
	components::movement& movement,
	const cosmos_navmesh& navmesh,
	const navigate_path_result& move_result,
	const float dt_secs,
	const bool should_run_avoidance_update,
	const bool is_freeze_time
) {
	if (is_freeze_time) {
		return false;
	}

	auto& ai_state = ctx.ai_state;
	const auto& cosm = ctx.cosm;
	const auto& physics = ctx.physics;
	const auto character_pos = ctx.character_pos;
	const auto si = cosm.get_si();
	const auto& clk = cosm.get_clock();

	/* Tick the danger timer down every frame */
	if (ai_state.danger_navigation_time_left >= 0.0f) {
		ai_state.danger_navigation_time_left -= dt_secs;

		if (ai_state.danger_navigation_time_left < 0.0f) {
			ai_state.danger_navigation_time_left = -1.0f;
			ai_state.danger_navigation_request = std::nullopt;
		}
	}

	/*
		When cover is reached, clear the navigation request so the bot stands
		still.  The timer keeps running; the scan will issue a new request if
		the grenade is still visible from the new position.
	*/
	if (move_result.path_completed
		&& ai_state.current_navigation_request == ai_state.danger_navigation_request
		&& ai_state.danger_navigation_request.has_value()
	) {
		ai_state.danger_navigation_request = std::nullopt;
	}

	/*
		Scan for the closest visible thrown explosive and recalculate cover.
		Runs every throttled tick, even when a danger session is already active,
		so the target stays accurate as the grenade moves.
	*/
	if (should_run_avoidance_update) {
		const auto filter = predefined_queries::pathfinding();

		struct danger_candidate {
			vec2 pos;
			float remaining_secs;
			float dist_sq;
			float cover_radius;
		};

		std::optional<danger_candidate> closest;

		auto consider_candidate = [&](const vec2 pos, const float remaining_secs, const float raw_radius) {
			const auto cover_radius = std::clamp(raw_radius, 700.0f, 1100.0f);
			const auto dist_sq = (pos - character_pos).length_sq();

			if (dist_sq > cover_radius * cover_radius) {
				return;
			}

			/*
				Character is safe only when EVERY polygon vertex of its hitbox is
				shielded from the danger. Check all vertices and exit as soon as
				one is exposed (no wall between it and the danger).
			*/
			const bool any_vertex_exposed = ::los_to_any_vertices_of(ctx.character_handle, pos, physics, si, filter);

			if (!any_vertex_exposed) {
				/* Every vertex is shielded — character is already safe from this danger */
				return;
			}

			if (!closest.has_value() || dist_sq < closest->dist_sq) {
				closest = danger_candidate{ pos, remaining_secs, dist_sq, cover_radius };
			}
		};

		const bool is_defusing = ::is_behavior<ai_behavior_defuse>(ai_state.last_behavior);

		const auto should_avoid_explosion = [&](const standard_explosion_input& explosion) {
			if (!explosion.bother_avoiding) {
				return false;
			}

			if (explosion.damage.base < 0.f) {
				return false;
			}

			if (is_defusing && explosion.type != adverse_element_type::FORCE) {
				return false;
			}

			return true;
		};

		cosm.for_each_having<components::hand_fuse>(
			[&](const auto& grenade_handle) {
				if (!::is_like_thrown_explosive(grenade_handle)) {
					return;
				}

				if (const auto* explosive = grenade_handle.template find<invariants::explosive>()) {
					if (!should_avoid_explosion(explosive->explosion)) {
						return;
					}
				}

				consider_candidate(
					grenade_handle.get_logic_transform().pos,
					::estimate_danger_duration(cosm, clk, grenade_handle),
					::estimate_danger_radius(cosm, grenade_handle)
				);
			}
		);

		cosm.for_each_having<components::cascade_explosion>(
			[&](const auto& cascade_handle) {
				if (const auto* cascade_def = cascade_handle.template find<invariants::cascade_explosion>()) {
					if (!should_avoid_explosion(cascade_def->explosion)) {
						return;
					}
				}

				consider_candidate(
					cascade_handle.get_logic_transform().pos,
					::estimate_danger_duration(cosm, clk, cascade_handle),
					::estimate_danger_radius(cosm, cascade_handle)
				);
			}
		);

		/*
			Reload-based cover-seeking is handled separately by take_cover.hpp.
		*/

		if (closest.has_value()) {
			const auto cover_pos = ::find_closest_cover(navmesh, character_pos, closest->pos, std::nullopt, physics, si, closest->cover_radius);

			if (cover_pos.has_value()) {
				auto req = ai_navigation_request::to_position(*cover_pos);
				req.resolved_cell = ::resolve_cell_for_position(navmesh, *cover_pos);
				ai_state.danger_navigation_time_left = closest->remaining_secs;
				ai_state.danger_navigation_request = req;
			}
		}
	}

	const bool danger_active = ai_state.danger_navigation_time_left >= 0.0f;

	if (!danger_active) {
		return false;
	}

	if (ai_state.danger_navigation_request.has_value()) {
		if (move_result.movement_direction.has_value()
			&& ai_state.current_navigation_request == ai_state.danger_navigation_request
		) {
			/* Navigating to cover — sprint, dash, and follow the pathfinding direction */
			movement.flags.sprinting = move_result.can_sprint || move_result.nearing_end;

			const auto& character_handle = ctx.character_handle;
			const auto speed = character_handle.get_effective_velocity().length();

			movement.flags.dashing = move_result.can_sprint && speed > 500.0f;
			movement.flags.set_from_closest_direction(*move_result.movement_direction);
		}
	}
	else {
		/* In cover — stand completely still until the timer expires */
		movement.reset_movement_flags();
	}

	return danger_active;
}
