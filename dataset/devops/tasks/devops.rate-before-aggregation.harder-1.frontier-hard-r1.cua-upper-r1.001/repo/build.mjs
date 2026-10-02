import {cp, mkdir, rm} from "node:fs/promises";
import {existsSync} from "node:fs";

await rm("dist", {recursive: true, force: true});
await mkdir("dist/src", {recursive: true});
await cp("index.html", "dist/index.html");
await cp("src", "dist/src", {recursive: true});
for (const path of ["dist/index.html", "dist/src/main.js", "dist/src/styles.css"]) {
  if (!existsSync(path)) throw new Error(`missing build output ${path}`);
}
console.log("counter order console build ok");
