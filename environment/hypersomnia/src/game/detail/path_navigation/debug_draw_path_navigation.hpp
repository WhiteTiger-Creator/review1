#pragma once
#include "game/detail/pathfinding/pathfinding.h"
#include "game/modes/ai/arena_mode_ai_structs.h"
#include "game/detail/path_navigation/path_helpers.hpp"
#include "game/debug_drawing_settings.h"

/*
	Debug draw the current path navigation state.
*/

inline void debug_draw_path_navigation(
	const std::optional<ai_path_navigation_state>& navigation_opt,
	const vec2 bot_pos,
	const cosmos_navmesh& navmesh
) {
	if (!DEBUG_DRAWING.draw_ai_info || !navigation_opt.has_value()) {
		return;
	}

	const auto& navigation = *navigation_opt;

	auto draw_path = [&](const path_navigation_progress& progress, bool rerouting) {
		const auto& path = progress.path;

		if (path.island_index >= navmesh.islands.size()) {
			return;
		}

		const auto& island = navmesh.islands[path.island_index];
		const auto cell_size = static_cast<float>(island.cell_size);

		for (std::size_t i = 0; i < path.nodes.size(); ++i) {
			const auto& node = path.nodes[i];
			const auto cell_center = ::cell_to_world(island, node.cell_xy);

			/*
				Draw cell AABB with smaller alpha.
			*/
			rgba cell_color;
			if (rerouting) {
				cell_color = i < progress.node_index ? rgba(255, 0, 0, 40) : rgba(255, 255, 0, 40);
			}
			else {
				cell_color = i < progress.node_index ? rgba(255, 0, 0, 40) : rgba(0, 255, 0, 40);
			}

			const auto cell_size_vec = vec2(cell_size, cell_size);
			DEBUG_LOGIC_STEP_RECTS.emplace_back(cell_color, cell_center, cell_size_vec, 0.0f);

			/*
				Draw line to next cell.
			*/
			if (i + 1 < path.nodes.size()) {
				const auto to = ::cell_to_world(island, path.nodes[i + 1].cell_xy);

				if (rerouting) {
					DEBUG_LOGIC_STEP_LINES.emplace_back(i < progress.node_index ? red : yellow, cell_center, to);
				}
				else {
					DEBUG_LOGIC_STEP_LINES.emplace_back(i < progress.node_index ? red : green, cell_center, to);
				}
			}
		}
	};

	draw_path(navigation.main, false);

	if (navigation.rerouting.has_value()) {
		draw_path(*navigation.rerouting, true);
	}

	if (const auto target = ::get_current_path_target(navigation, navmesh)) {
		DEBUG_LOGIC_STEP_LINES.emplace_back(cyan, bot_pos, *target);
	}

	if (navigation.exact_destination) {
		DEBUG_LOGIC_STEP_LINES.emplace_back(cyan, bot_pos, navigation.target_position());
	}
}
