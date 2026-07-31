#pragma once
#include "game/cosmos/entity_handle.h"
#include "game/components/item_component.h"
#include "game/components/gun_component.h"
#include "game/components/hand_fuse_component.h"
#include "game/components/melee_component.h"
#include "game/detail/entity_handle_mixins/for_each_slot_and_item.hpp"
#include "game/detail/weapon_like.h"

/*
	Find the most expensive gun in the bot's inventory.
	If no gun is available, fall back to the first melee weapon found
	so the bot can still charge the enemy with a knife.
	Returns the item id if found, otherwise returns dead entity_id.
*/

template <class E>
inline entity_id find_best_weapon(const E& character_handle) {
	entity_id best_gun;
	money_type best_price = 0;
	entity_id first_melee;

	character_handle.for_each_contained_item_recursive(
		[&](const auto& item) {
			if (item.template has<components::gun>()) {
				if (const auto item_def = item.template find<invariants::item>()) {
					const auto price = item_def->standard_price;

					if (price > best_price) {
						best_price = price;
						best_gun = item.get_id();
					}
				}

				return recursive_callback_result::CONTINUE_DONT_RECURSE;
			}

			if (!first_melee.is_set() && item.template has<components::melee>()) {
				first_melee = item.get_id();
				return recursive_callback_result::CONTINUE_DONT_RECURSE;
			}

			return recursive_callback_result::CONTINUE_AND_RECURSE;
		}
	);

	if (best_gun.is_set()) {
		return best_gun;
	}

	return first_melee;
}
