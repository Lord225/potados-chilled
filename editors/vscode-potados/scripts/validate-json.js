"use strict";

const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
for (const relative of [
  "package.json",
  "language-configuration.json",
  "syntaxes/potados-asm.tmLanguage.json"
]) {
  JSON.parse(fs.readFileSync(path.join(root, relative), "utf8"));
}
