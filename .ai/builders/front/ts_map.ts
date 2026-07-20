// Semantic map builder for TypeScript/React source trees.
//
// Pure, dependency-free extractor: only Node.js built-in modules (`fs`,
// `path`, `crypto`) are used. Anchors are detected with lightweight regex
// matching (no AST / type-checking), so no `tsconfig`, `ts-morph`, or
// `js-yaml` is required. Output is JSON via `JSON.stringify`.
//
// Portability:
//   * Copy this file to any project.
//   * Configure source/output via the env vars below (or edit the defaults).
//   * Run: `node --experimental-strip-types ts_map.ts` (Node 22+),
//     or rename to `.js` and run `node ts_map.js`.
//
// This builder is gated by ENABLE_TS. When false it exits without scanning,
// so it is safe to ship in projects (like Mko Bazuna) that have no frontend.

import { createHash } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

// ============================================================================
// Config (env-overridable)
// ============================================================================

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// ENABLE_TS gates execution. Default false (no frontend in this project).
const ENABLE_TS =
  (process.env.ENABLE_TS ?? "false").toLowerCase() === "true";

// Source root: directory containing the TS/TSX sources to scan.
const TS_SRC_ROOT = process.env.TS_SRC_ROOT
  ? path.resolve(process.env.TS_SRC_ROOT)
  : path.resolve(__dirname, "..", "..", "..", "frontend");

// Output directory for the generated JSON files.
const TS_OUTPUT = process.env.TS_OUTPUT
  ? path.resolve(process.env.TS_OUTPUT)
  : path.resolve(__dirname, "..", "..", "structure", "front");

const IGNORE_DIRS = [
  "node_modules",
  ".next",
  ".git",
  "dist",
  "build",
  "coverage",
];

const IGNORE_EXTENSIONS = [".json", ".md", ".map"];

// ============================================================================
// Helpers
// ============================================================================

function shouldIgnore(filePath: string): boolean {
  return IGNORE_DIRS.some((part) => filePath.includes(part));
}

function hash(input: string): string {
  return createHash("md5").update(input).digest("hex").slice(0, 8);
}

// Layer detection (first match wins).
function detectLayer(filePath: string): string {
  const posix = filePath.replace(/\\/g, "/");
  if (posix.includes("/pages/")) return "page";
  if (posix.includes("/components/")) return "component";
  if (posix.includes("/hooks/")) return "hook";
  if (posix.includes("/api/")) return "api";
  if (posix.includes("/services/")) return "service";
  if (posix.includes("/utils/")) return "util";
  return "other";
}

// ============================================================================
// Regex extractors
// ============================================================================

// function Component() / function useHook()
const FN_DECL = /^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/gm;
// const Component = () => {}  (uppercase start => component)
const ARROW_COMPONENT =
  /^(?:export\s+)?const\s+([A-Z][A-Za-z0-9]*)\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>/gm;
// uppercase-opening JSX tags
const JSX_TAG = /<([A-Z][A-Za-z0-9]*)[^>]*>/g;

function extractSymbols(source: string): {
  components: string[];
  hooks: string[];
  jsxTags: string[];
} {
  const components = new Set<string>();
  const hooks = new Set<string>();
  const jsxTags: string[] = [];

  let m: RegExpExecArray | null;

  FN_DECL.lastIndex = 0;
  while ((m = FN_DECL.exec(source)) !== null) {
    const name = m[1];
    if (/^use[A-Z]/.test(name)) {
      hooks.add(name);
    } else if (/^[A-Z]/.test(name)) {
      components.add(name);
    }
  }

  ARROW_COMPONENT.lastIndex = 0;
  while ((m = ARROW_COMPONENT.exec(source)) !== null) {
    components.add(m[1]);
  }

  JSX_TAG.lastIndex = 0;
  while ((m = JSX_TAG.exec(source)) !== null) {
    jsxTags.push(m[1]);
  }

  return {
    components: [...components],
    hooks: [...hooks],
    jsxTags,
  };
}

// ============================================================================
// Main
// ============================================================================

function walk(dir: string, acc: string[]): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (shouldIgnore(full)) continue;
    if (entry.isDirectory()) {
      walk(full, acc);
    } else if (
      (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) &&
      !IGNORE_EXTENSIONS.some((ext) => entry.name.endsWith(ext)) &&
      !entry.name.endsWith(".d.ts")
    ) {
      acc.push(full);
    }
  }
  return acc;
}

function build(): { files: unknown[]; anchors: unknown[] } {
  const semanticGraph = { files: [] as unknown[], anchors: [] as unknown[] };

  if (!fs.existsSync(TS_SRC_ROOT)) {
    console.error(`TS_SRC_ROOT does not exist: ${TS_SRC_ROOT}`);
    return semanticGraph;
  }

  const files = walk(TS_SRC_ROOT, []);

  for (const filePath of files) {
    const source = fs.readFileSync(filePath, "utf-8");
    const { components, hooks, jsxTags } = extractSymbols(source);

    const relPath = path.relative(TS_SRC_ROOT, filePath);

    semanticGraph.files.push({
      path: relPath,
      module: relPath
        .replace(/\\/g, ".")
        .replace(/\//g, ".")
        .replace(/\.(ts|tsx)$/, ""),
      layer: detectLayer(relPath),
      imports: [],
      components,
      hooks,
      jsx_tags: jsxTags,
    });

    for (const component of components) {
      const h = hash(`${filePath}:${component}`);
      semanticGraph.anchors.push({
        id: h,
        file: relPath,
        symbol_path: [component],
        type: "component",
        value: component,
        stable_hash: h,
      });
    }
    for (const hook of hooks) {
      const h = hash(`${filePath}:${hook}`);
      semanticGraph.anchors.push({
        id: h,
        file: relPath,
        symbol_path: [hook],
        type: "hook",
        value: hook,
        stable_hash: h,
      });
    }
  }

  return semanticGraph;
}

function main(): void {
  if (!ENABLE_TS) {
    console.log("ENABLE_TS is false; skipping TypeScript semantic map build.");
    return;
  }

  fs.mkdirSync(TS_OUTPUT, { recursive: true });

  const graph = build();

  fs.writeFileSync(
    path.join(TS_OUTPUT, "ts_map.json"),
    JSON.stringify(graph.files, null, 2),
  );
  fs.writeFileSync(
    path.join(TS_OUTPUT, "ts_anchors.json"),
    JSON.stringify(graph.anchors, null, 2),
  );

  console.log(
    `Generated ts_map.json (${graph.files.length} files), ` +
      `ts_anchors.json (${graph.anchors.length} anchors)`,
  );
}

main();
