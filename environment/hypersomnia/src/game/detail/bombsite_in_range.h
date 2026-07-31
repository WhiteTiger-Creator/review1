#pragma once
#include <optional>
#include "game/detail/visible_entities.hpp"
#include "game/detail/physics/shape_overlapping.hpp"
#include "game/detail/entity_handle_mixins/get_owning_transfer_capability.hpp"
#include "game/components/marker_component.h"

template <class E>
std::optional<marker_letter_type> bombsite_in_range_of_entity(const E& queried_entity) {
	const auto capability = queried_entity.get_owning_transfer_capability();
	const auto matched_faction = capability.alive() ? capability.get_official_faction() : faction_type::SPECTATOR;

	const auto& cosm = queried_entity.get_cosmos();

	auto& entities = thread_local_visible_entities();

	entities.reacquire_all({
		cosm,
		camera_cone::from_aabb(queried_entity),
		accuracy_type::PROXIMATE,
		render_layer_filter::whitelist(render_layer::AREA_MARKERS),
		{ { tree_of_npo_type::RENDERABLES } }
	});

	std::optional<marker_letter_type> found_letter;

	entities.for_each<render_layer::AREA_MARKERS>(cosm, [&](const auto& area) {
		return area.template dispatch_on_having_all_ret<invariants::area_marker>([&](const auto& typed_area) {
			if constexpr(is_nullopt_v<decltype(typed_area)>) {
				return callback_result::CONTINUE;
			}
			else {
				const auto& marker = typed_area.template get<invariants::area_marker>();

				if (::is_bombsite(marker.type)) {
					if (matched_faction == typed_area.get_official_faction()) {
						if (entity_overlaps_entity(typed_area, queried_entity)) {
							found_letter = typed_area.template get<components::marker>().letter;
							return callback_result::ABORT;
						}
					}
				}

				return callback_result::CONTINUE;
			}
		});
	});

	return found_letter;
}

template <class E>
std::optional<marker_letter_type> bombsite_in_range(const E& fused_entity) {
	if (fused_entity.template get<components::hand_fuse>().defused()) {
		return std::nullopt;
	}

	const auto& fuse_def = fused_entity.template get<invariants::hand_fuse>();

	if (fuse_def.can_only_arm_at_bombsites) {
		return bombsite_in_range_of_entity(fused_entity);
	}

	/*
		Item can be armed anywhere (e.g. a grenade) — not bombsite-restricted.
		Return COUNT as a sentinel: "can arm, but at no specific site".
	*/
	return marker_letter_type::COUNT;
}

