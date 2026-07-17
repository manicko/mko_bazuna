import { createHash } from "crypto";
import fs from "fs";
import yaml from "js-yaml";
import path from "path";
import { Project, SyntaxKind } from "ts-morph";
import { fileURLToPath } from "url";



// ======================================================
// CONFIG
// ======================================================

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const tsconfigPath = path.resolve(
  __dirname,
  "..",
  "..",
  "..",
    "frontend",
    "tsconfig.app.json"
);

const project = new Project({
  tsConfigFilePath: tsconfigPath,
});

console.log("TSConfig path:", tsconfigPath);
const IGNORE = [
  "node_modules",
  ".next",
  "dist",
  "build",
];


// ======================================================
// HELPERS
// ======================================================

function shouldIgnore(filePath: string): boolean {
  return IGNORE.some(part =>
    filePath.includes(part)
  );
}

function hash(input: string): string {
  return createHash("md5")
    .update(input)
    .digest("hex")
    .slice(0, 8);
}


// ======================================================
// MAIN GRAPH
// ======================================================

const semanticGraph: any = {
  files: [],
  anchors: [],
};


// ======================================================
// SCAN FILES
// ======================================================

for (const file of project.getSourceFiles()) {

  const filePath = file.getFilePath();

  if (shouldIgnore(filePath)) {
    continue;
  }

  // ====================================================
  // IMPORTS
  // ====================================================

  const imports = file
    .getImportDeclarations()
    .map(imp =>
      imp.getModuleSpecifierValue()
    );

  // ====================================================
  // COMPONENTS
  // ====================================================

  const components: string[] = [];

  // function Component()
  for (const fn of file.getFunctions()) {

    const name = fn.getName();

    if (
      name &&
      /^[A-Z]/.test(name)
    ) {
      components.push(name);
    }
  }

  // const Component = () => {}
  for (const variable of file.getVariableDeclarations()) {

    const name = variable.getName();

    const initializer =
      variable.getInitializer();

    if (
      name &&
      /^[A-Z]/.test(name) &&
      initializer &&
      (
        initializer.getKind() ===
        SyntaxKind.ArrowFunction
      )
    ) {
      components.push(name);
    }
  }

  // ====================================================
  // HOOKS
  // ====================================================

  const hooks: string[] = [];

  for (const fn of file.getFunctions()) {

    const name = fn.getName();

    if (
      name &&
      name.startsWith("use")
    ) {
      hooks.push(name);
    }
  }

  // ====================================================
  // JSX TAGS
  // ====================================================

  const jsxTags: string[] = [];

  file.forEachDescendant(node => {

    if (
      node.getKind() ===
      SyntaxKind.JsxOpeningElement
    ) {

      jsxTags.push(
        node.getText()
      );
    }
  });

  // ====================================================
  // FILE ENTRY
  // ====================================================

  semanticGraph.files.push({

    path: filePath,

    module: filePath
      .replace(/\\/g, ".")
      .replace(/\//g, ".")
      .replace(/\.(ts|tsx)$/, ""),

    layer:
      filePath.includes("/pages/")
        ? "page"
        : filePath.includes("/components/")
        ? "component"
        : filePath.includes("/hooks/")
        ? "hook"
        : filePath.includes("/api/")
        ? "api"
        : "unknown",

    imports,

    components,

    hooks,

    jsx_tags: jsxTags,
  });

  // ====================================================
  // SEMANTIC ANCHORS
  // ====================================================

  for (const component of components) {

    semanticGraph.anchors.push({

      id: hash(
        `${filePath}:${component}`
      ),

      file: filePath,

      symbol_path: [
        component
      ],

      type: "component",

      value: component,

      stable_hash: hash(
        `${filePath}:${component}`
      ),
    });
  }

  for (const hook of hooks) {

    semanticGraph.anchors.push({

      id: hash(
        `${filePath}:${hook}`
      ),

      file: filePath,

      symbol_path: [
        hook
      ],

      type: "hook",

      value: hook,

      stable_hash: hash(
        `${filePath}:${hook}`
      ),
    });
  }
}


// ======================================================
// SAVE
// ======================================================
const outputDir = "C:/py_dev/mkobi.ai/structure/front"


fs.mkdirSync(
  outputDir,
  { recursive: true }
);

fs.writeFileSync(
  `${outputDir}/ts_anchors.yaml`,
  yaml.dump(
    semanticGraph.anchors,
    {
      noRefs: true,
    }
  )
);
fs.writeFileSync(
  `${outputDir}/ts_map.yaml`,
  yaml.dump(
    semanticGraph.files,
    {
      noRefs: true,
    }
  )
);
console.log(
  "Generated ts_anchors.yaml", "Generated ts_map.yaml"
);
