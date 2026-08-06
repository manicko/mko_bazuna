const fs = require("fs");
const css = fs.readFileSync("src/theme/static/theme/css/output.css", "utf8");
const targets = [
  "text-blue-600",
  "bg-blue-600",
  "rounded-lg",
  "shadow-sm",
  "bg-gray-50",
  "border-gray-300",
  "object-cover",
  "line-clamp-2",
  "container",
  "divide-y",
];
const results = [];
for (const c of targets) {
  const re = new RegExp("\\." + c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\{");
  const matches = css.match(re);
  results.push({ class: c, found: !!matches, count: matches ? matches.length : 0 });
}
console.log("Total output.css chars:", css.length);
console.log("Total classes (approx, count of '.XXX{'):", (css.match(/\.[a-zA-Z][\w-]*\{/g) || []).length);
console.log("---");
for (const r of results) {
  console.log(`${r.class}: ${r.found ? "FOUND" : "NOT FOUND"} count=${r.count}`);
}
