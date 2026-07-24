/** Escape path characters for Make target/prerequisite syntax (not variable refs). */
export function escapeMakePath(value) {
  return String(value)
    .replace(/\\/g, '\\\\')
    .replace(/\$/g, '$$$$') // JS replace: $$$$ -> $$
    .replace(/ /g, '\\ ')
    .replace(/:/g, '\\:')
    .replace(/#/g, '\\#');
}

/** Escape a string for use as a Make target (includes Make variable refs as-is). */
export function escapeMakeTarget(value) {
  // Preserve intentional Make variables like $(ASSET_ROOT), escape other dollars.
  return String(value)
    .replace(/\$\(([^)]+)\)/g, '\u0000($1)\u0000')
    .replace(/\$/g, '$$$$')
    .replace(/\u0000\(([^)]+)\)\u0000/g, '$$($1)')
    .replace(/ /g, '\\ ')
    .replace(/:/g, '\\:')
    .replace(/#/g, '\\#');
}

/** Escape for Make recipe lines (dollar signs doubled so Make yields a single $). */
export function escapeMakeRecipe(value) {
  return String(value).replace(/\$/g, '$$$$');
}

/** Escape a shell argument for embedding in a Make recipe. */
export function escapeShellArg(value) {
  if (/^[A-Za-z0-9_@%+=:,./-]+$/.test(value)) return value;
  return "'" + String(value).replace(/'/g, "'\\''") + "'";
}
