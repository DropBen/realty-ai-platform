// A direct esbuild build also works in restricted Windows environments where
// long-lived child processes with IPC pipes cannot start. No shell is used.
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  copyFileSync,
  rmSync,
} from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const require = createRequire(import.meta.url);
const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
process.chdir(root);
const types = spawnSync(
  process.execPath,
  [require.resolve("typescript/bin/tsc"), "-b"],
  { stdio: "inherit" },
);
if (types.status !== 0) process.exit(types.status || 1);
const esbuild =
  process.platform === "win32"
    ? require.resolve("@esbuild/win32-x64/esbuild.exe")
    : resolve("node_modules/esbuild/bin/esbuild");
const dist = resolve("dist");
if (dist !== resolve(root, "dist"))
  throw new Error("Invalid build output path");
rmSync(dist, { recursive: true, force: true });
mkdirSync(resolve(dist, "assets"), { recursive: true });
const result = spawnSync(
  esbuild,
  [
    "frontend/main.tsx",
    "--bundle",
    "--format=esm",
    "--splitting",
    "--target=es2022",
    "--minify",
    "--outdir=dist/assets",
    "--entry-names=[name]-[hash]",
    "--chunk-names=chunk-[hash]",
    "--metafile=dist/meta.json",
    '--define:process.env.NODE_ENV="production"',
  ],
  { stdio: "inherit" },
);
if (result.status !== 0) process.exit(result.status || 1);
const meta = JSON.parse(readFileSync("dist/meta.json", "utf8"));
const [entry, info] = Object.entries(meta.outputs).find(
  ([, value]) => value.entryPoint === "frontend/main.tsx",
);
const html = readFileSync("index.html", "utf8").replace(
  '<script type="module" src="/frontend/main.tsx"></script>',
  `<link rel="stylesheet" href="/${info.cssBundle.replace("dist/", "")}"><script type="module" src="/${entry.replace("dist/", "")}"></script>`,
);
writeFileSync("dist/index.html", html);
copyFileSync("public/favicon.svg", "dist/favicon.svg");
rmSync("dist/meta.json");
console.log("RealtyAI production assets built in dist/.");
