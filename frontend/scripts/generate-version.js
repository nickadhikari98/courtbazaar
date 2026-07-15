#!/usr/bin/env node
/* Runs as the "prebuild" step (see package.json) before every `yarn build`.
   Writes the current git commit into public/version.json so it gets copied
   into build/ verbatim by CRA's static public-folder copy — giving every
   deployment a one-line way to verify what's actually live:
     curl https://courtbazaar.in/version.json
   versus:
     git rev-parse HEAD
   This exists because there was previously no way to confirm a deployed
   build matched the commit it was supposed to be built from short of
   manually inspecting compiled output. */

const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function git(cmd) {
  try {
    return execSync(`git ${cmd}`, { cwd: path.join(__dirname, ".."), encoding: "utf8" }).trim();
  } catch {
    return null;
  }
}

const commit = git("rev-parse HEAD") || "unknown";
const commitShort = git("rev-parse --short HEAD") || "unknown";
const branch = git("rev-parse --abbrev-ref HEAD") || "unknown";
const commitDate = git("log -1 --format=%cI") || null;

const version = {
  commit,
  commitShort,
  branch,
  commitDate,
  builtAt: new Date().toISOString(),
};

const outPath = path.join(__dirname, "..", "public", "version.json");
fs.writeFileSync(outPath, JSON.stringify(version, null, 2) + "\n");
console.log(`[generate-version] wrote ${outPath} — commit ${commitShort} on ${branch}`);
