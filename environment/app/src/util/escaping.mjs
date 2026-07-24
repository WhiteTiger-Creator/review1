/** Escape a string for use as a single Make target name segment. */
export function escapeMakeTarget(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/ /g, '\\ ')
    .replace(/:/g, '\\:')
    .replace(/#/g, '\\#');
}

/** Escape for Make recipe lines (dollar signs doubled). */
export function escapeMakeRecipe(value) {
  return String(value).replace(/\$/g, '$$$$');
}

/** Escape a shell argument for embedding in a Make recipe. */
export function escapeShellArg(value) {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
  return "'" + String(value).replace(/'/g, "'\''") + "'";
}
