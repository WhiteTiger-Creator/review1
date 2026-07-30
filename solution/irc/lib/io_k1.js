import fs from "fs";
import path from "path";

export function readJson(p) {
  return JSON.parse(fs.readFileSync(p, "utf8"));
}

export function saveJson(p, obj) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  fs.writeFileSync(p, JSON.stringify(obj, null, 2) + "\n");
}

export function readJournal(p) {
  if (!fs.existsSync(p)) return [];
  const text = fs.readFileSync(p, "utf8").trim();
  if (!text) return [];
  return text.split("\n").map((line) => JSON.parse(line));
}

export function writeJournal(p, events) {
  const body = events.map((e) => JSON.stringify(e)).join("\n") + (events.length ? "\n" : "");
  fs.writeFileSync(p, body);
}

export function loadState(root) {
  const state = path.join(root, "state");
  return {
    root,
    state,
    registry: readJson(path.join(state, "registry.json")),
    profile: readJson(path.join(state, "serving_profile.json")),
    journal: readJournal(path.join(state, "journal.ndjson")),
    router: readJson(path.join(state, "router.json")),
    feature: readJson(path.join(state, "feature_bind.json")),
    materialization: readJson(path.join(state, "materialized.json")),
    policy: readJson(path.join(state, "eval_policy.json")),
    staging: path.join(state, "staging"),
  };
}

export function findCkpt(registry, id) {
  return registry.checkpoints.find((c) => c.id === id) || null;
}

export function parentSeenInJournal(journal, parentId) {
  if (!parentId) return true;
  return journal.some((e) => e.complete && e.ckpt === parentId);
}
