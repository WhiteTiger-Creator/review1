#!/usr/bin/env node

const fs = require("fs");
const path = require("path");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 2) args[argv[i]] = argv[i + 1];
  return args;
}

function hasAll(emblems, required) {
  const needed = new Map();
  for (const item of required || []) needed.set(item, (needed.get(item) || 0) + 1);
  for (const [item, count] of needed) {
    if ((emblems.get(item) || 0) < count) return false;
  }
  return true;
}

function addEmblem(emblems, item) {
  const next = new Map(emblems);
  next.set(item, (next.get(item) || 0) + 1);
  return next;
}

function consumeEmblems(emblems, consumed) {
  const next = new Map(emblems);
  for (const item of consumed || []) {
    const remaining = (next.get(item) || 0) - 1;
    if (remaining > 0) next.set(item, remaining);
    else next.delete(item);
  }
  return next;
}

function routeSatisfied(pathIds, route) {
  const needed = route || [];
  if (needed.length === 0) return true;
  let pos = 0;
  for (const siteId of pathIds) {
    if (siteId === needed[pos]) {
      pos += 1;
      if (pos === needed.length) return true;
    }
  }
  return false;
}

function contractIds(match, emblems, pathIds, claimed, finalEnergy, finalHeat) {
  const eligible = match.contracts.filter((contract) => {
    const forbidsAbsent = (contract.forbids || []).every((item) => (emblems.get(item) || 0) === 0);
    const heatOk = !Object.prototype.hasOwnProperty.call(contract, "final_heat_at_most") || finalHeat <= contract.final_heat_at_most;
    const energyOk = !Object.prototype.hasOwnProperty.call(contract, "final_energy_at_least") || finalEnergy >= contract.final_energy_at_least;
    return (
      hasAll(emblems, contract.requires || []) &&
      forbidsAbsent &&
      heatOk &&
      energyOk &&
      routeSatisfied(pathIds, contract.route || []) &&
      routeSatisfied(claimed, contract.claimed_order || [])
    );
  });
  let bestIds = [];
  let bestPoints = -1;

  function conflicts(left, right) {
    return (left.exclusive_with || []).includes(right.id) || (right.exclusive_with || []).includes(left.id);
  }

  for (let mask = 0; mask < 1 << eligible.length; mask += 1) {
    const chosen = eligible.filter((_, idx) => mask & (1 << idx));
    let ok = true;
    for (let i = 0; i < chosen.length; i += 1) {
      for (let j = i + 1; j < chosen.length; j += 1) {
        if (conflicts(chosen[i], chosen[j])) ok = false;
      }
    }
    if (!ok) continue;
    const ids = chosen.map((contract) => contract.id).sort();
    const points = chosen.reduce((sum, contract) => sum + contract.points, 0);
    if (points > bestPoints || (points === bestPoints && ids.join(",") < bestIds.join(","))) {
      bestPoints = points;
      bestIds = ids;
    }
  }
  return bestIds;
}

function echoPoints(match, pathIds, claimed) {
  const sites = new Map(match.sites.map((site) => [site.id, site]));
  const visits = new Map();
  for (const siteId of pathIds) visits.set(siteId, (visits.get(siteId) || 0) + 1);
  return claimed.reduce((sum, siteId) => {
    if ((visits.get(siteId) || 0) >= 2) return sum + (sites.get(siteId).echo_points || 0);
    return sum;
  }, 0);
}

function resultKey(result) {
  return [
    -result.score,
    result.final_heat,
    -result.final_energy,
    result.path.length,
    result.path.join(">"),
    result.contracts.join(","),
  ];
}

function compareKey(left, right) {
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] < right[i]) return -1;
    if (left[i] > right[i]) return 1;
  }
  return 0;
}

function solve(match) {
  const sites = new Map(match.sites.map((site) => [site.id, site]));
  const linksByFrom = new Map();
  for (const link of match.links) {
    if (!linksByFrom.has(link.from)) linksByFrom.set(link.from, []);
    linksByFrom.get(link.from).push(link);
  }

  let anyMove = false;
  let best = null;

  function finish(pathIds, claimed, emblems, score, energy, heat) {
    const contracts = contractIds(match, emblems, pathIds, claimed, energy, heat);
    const contractPoints = match.contracts
      .filter((contract) => contracts.includes(contract.id))
      .reduce((sum, contract) => sum + contract.points, 0);
    const candidate = {
      score: score + echoPoints(match, pathIds, claimed) + contractPoints,
      path: [...pathIds],
      claimed: [...claimed],
      contracts,
      final_energy: energy,
      final_heat: heat,
    };
    if (best === null || compareKey(resultKey(candidate), resultKey(best)) < 0) {
      best = candidate;
    }
  }

  function walk(roundNo, current, pathIds, claimed, emblems, linkCounts, score, energy, heat) {
    finish(pathIds, claimed, emblems, score, energy, heat);
    if (roundNo > match.round_limit) return;

    for (const link of linksByFrom.get(current) || []) {
      if (!hasAll(emblems, link.requires || [])) continue;
      if (!hasAll(emblems, link.consumes || [])) continue;
      if (Object.prototype.hasOwnProperty.call(link, "quiet_max_heat") && heat > link.quiet_max_heat) continue;
      if (Object.prototype.hasOwnProperty.call(link, "open_rounds") && !link.open_rounds.includes(roundNo)) continue;
      const effectiveCost = link.cost + (linkCounts.get(link.id) || 0);
      if (energy < effectiveCost) continue;
      const revisitHeat = pathIds.includes(link.to) && link.safe_revisit !== true ? 1 : 0;
      const nextHeat = heat + link.heat + revisitHeat;
      if (nextHeat > match.heat_limit) continue;

      anyMove = true;
      let nextEnergy = energy - effectiveCost;
      let nextScore = score;
      let nextEmblems = consumeEmblems(emblems, link.consumes || []);
      const nextLinkCounts = new Map(linkCounts);
      nextLinkCounts.set(link.id, (nextLinkCounts.get(link.id) || 0) + 1);
      const nextClaimed = [...claimed];
      const dest = sites.get(link.to);
      const blocked = (dest.block_rounds || []).includes(roundNo);
      const alreadyClaimed = nextClaimed.includes(link.to);
      const sealed = !hasAll(nextEmblems, dest.seal || []);

      if (link.to !== match.start && !alreadyClaimed && !blocked && !sealed) {
        nextClaimed.push(link.to);
        nextEmblems = addEmblem(nextEmblems, dest.emblem);
        let sitePoints = dest.points;
        if (dest.late_penalty && roundNo > dest.late_penalty.after) {
          sitePoints = Math.max(0, sitePoints - dest.late_penalty.points);
        }
        if (dest.chain_points && claimed.includes(dest.chain_points.after)) {
          sitePoints += dest.chain_points.points;
        }
        nextScore += sitePoints;
        nextEnergy = Math.min(match.energy_cap, nextEnergy + dest.rest);
      }

      if (link.bonus) {
        if (Object.prototype.hasOwnProperty.call(link.bonus, "energy")) {
          nextEnergy = Math.min(match.energy_cap, nextEnergy + link.bonus.energy);
        }
        if (Object.prototype.hasOwnProperty.call(link.bonus, "emblem")) {
          nextEmblems = addEmblem(nextEmblems, link.bonus.emblem);
        }
      }

      walk(roundNo + 1, link.to, [...pathIds, link.to], nextClaimed, nextEmblems, nextLinkCounts, nextScore, nextEnergy, nextHeat);
    }
  }

  walk(1, match.start, [match.start], [], new Map(), new Map(), 0, match.energy, match.heat);
  if (!anyMove && best.score === 0 && best.contracts.length === 0) {
    return {
      score: null,
      path: [match.start],
      claimed: [],
      contracts: [],
      final_energy: match.energy,
      final_heat: match.heat,
    };
  }
  return best;
}

const args = parseArgs(process.argv);
const match = JSON.parse(fs.readFileSync(args["--input"], "utf8"));
const output = solve(match);
fs.mkdirSync(path.dirname(args["--output"]), { recursive: true });
fs.writeFileSync(args["--output"], `${JSON.stringify(output, null, 2)}\n`);
