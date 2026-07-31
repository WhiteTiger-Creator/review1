type FloorSpec = {
  map: string[];
  start: { x: number; y: number };
  shards: Record<string, string>;
  foes: Record<string, { name: string; hp: number; atk: number; def: number }>;
};

function parseMaps(floors: FloorSpec[]): {
  grids: string[][][];
  starts: { x: number; y: number }[];
  shard_at: Record<string, string>;
  foes: Record<string, { name: string; hp: number; atk: number; def: number }>;
  floor_loot: Record<number, string>;
} {
  const grids: string[][][] = [];
  const starts: { x: number; y: number }[] = [];
  const shard_at: Record<string, string> = {};
  const foes: Record<string, { name: string; hp: number; atk: number; def: number }> = {};
  const floor_loot: Record<number, string> = {};
  floors.forEach((f, fi) => {
    grids.push(f.map.map((row) => row.split("")));
    starts.push(f.start);
    for (const [k, id] of Object.entries(f.shards)) {
      shard_at[`${fi}:${k}`] = id;
      if (fi <= 2) floor_loot[fi] = id;
    }
    for (const [k, foe] of Object.entries(f.foes)) {
      foes[`${fi}:${k}`] = { ...foe };
    }
  });
  return { grids, starts, shard_at, foes, floor_loot };
}

const NOMINAL: FloorSpec[] = [
  {
    map: [
      "#######",
      "#S.1..#",
      "#.###.#",
      "#...E.#",
      "#.##..#",
      "#...>.#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "3,1": "ember_core" },
    foes: { "4,3": { name: "ward", hp: 6, atk: 2, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#.##2.#",
      "#E..#.#",
      "#.###.#",
      "#...>.#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "4,2": "veil_latch" },
    foes: { "1,3": { name: "ward", hp: 8, atk: 3, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S.#..#",
      "#..#3.#",
      "#.##E.#",
      "#.....#",
      "#>....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "4,2": "crest_key" },
    foes: { "4,3": { name: "ward", hp: 10, atk: 3, def: 2 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#.###.#",
      "#...E.#",
      "#.###.#",
      "#...>.#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: {},
    foes: { "4,3": { name: "ward", hp: 8, atk: 2, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#.###.#",
      "#..X..#",
      "#.###.#",
      "#.....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: {},
    foes: {},
  },
];

/** Holdout: geometry change plus shard-to-floor permutation (not floor-index order). */
const HOLDOUT: FloorSpec[] = [
  {
    map: [
      "#######",
      "#S..E.#",
      "#.##..#",
      "#..2..#",
      "#.###.#",
      "#...>.#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "3,3": "veil_latch" },
    foes: { "4,1": { name: "ward", hp: 6, atk: 2, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S.#..#",
      "#..#E.#",
      "#.##3.#",
      "#.....#",
      "#>....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "4,3": "crest_key" },
    foes: { "4,2": { name: "ward", hp: 8, atk: 3, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#E###.#",
      "#..1..#",
      "#.###.#",
      "#...>.#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "3,3": "ember_core" },
    foes: { "1,2": { name: "ward", hp: 10, atk: 3, def: 2 } },
  },
  {
    map: [
      "#######",
      "#S.E..#",
      "#.###.#",
      "#.....#",
      "#.###.#",
      "#>....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: {},
    foes: { "3,1": { name: "ward", hp: 7, atk: 2, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#.....#",
      "#..X..#",
      "#.....#",
      "#.....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: {},
    foes: {},
  },
];

/** Mirror: third geometry; shard floors match nominal assignment. */
const MIRROR: FloorSpec[] = [
  {
    map: [
      "#######",
      "#S....#",
      "#.#E#.#",
      "#1..#.#",
      "#.###.#",
      "#..>..#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "1,3": "ember_core" },
    foes: { "3,2": { name: "ward", hp: 6, atk: 2, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S..#.#",
      "#..2..#",
      "#E###.#",
      "#.....#",
      "#>....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "3,2": "veil_latch" },
    foes: { "1,3": { name: "ward", hp: 8, atk: 3, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S.#..#",
      "#..#..#",
      "#.##3E#",
      "#.....#",
      "#>....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: { "4,3": "crest_key" },
    foes: { "5,3": { name: "ward", hp: 10, atk: 3, def: 2 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#.##E.#",
      "#.....#",
      "#.###.#",
      "#...>.#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: {},
    foes: { "4,2": { name: "ward", hp: 8, atk: 2, def: 1 } },
  },
  {
    map: [
      "#######",
      "#S....#",
      "#.###.#",
      "#..X..#",
      "#.###.#",
      "#.....#",
      "#######",
    ],
    start: { x: 1, y: 1 },
    shards: {},
    foes: {},
  },
];

export function loadSeed(seed: string): {
  grids: string[][][];
  starts: { x: number; y: number }[];
  shard_at: Record<string, string>;
  foes: Record<string, { name: string; hp: number; atk: number; def: number }>;
  floor_loot: Record<number, string>;
} {
  if (seed === "holdout") return parseMaps(HOLDOUT);
  if (seed === "mirror") return parseMaps(MIRROR);
  return parseMaps(NOMINAL);
}
