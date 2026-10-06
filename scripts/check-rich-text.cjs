"use strict";

// Exercise the real TSX renderer using the web project's existing dependencies.
// Run under `timeout 10s` in CI: a parser that stops consuming input must fail.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { createRequire } = require("node:module");
const { performance } = require("node:perf_hooks");

const webRoot = path.resolve(__dirname, "../apps/web");
const webRequire = createRequire(path.join(webRoot, "package.json"));
const ts = webRequire("typescript");
const { createElement } = webRequire("react");
const { renderToStaticMarkup } = webRequire("react-dom/server");
const sourcePath = path.join(webRoot, "app/learning/rich-text.tsx");
const compiled = ts.transpileModule(fs.readFileSync(sourcePath, "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX,
  },
  fileName: sourcePath,
}).outputText;
const moduleUnderTest = { exports: {} };
vm.runInNewContext(compiled, {
  module: moduleUnderTest,
  exports: moduleUnderTest.exports,
  require: webRequire,
}, { filename: sourcePath, timeout: 1000 });
const RichText = moduleUnderTest.exports.default;
const render = (text) => renderToStaticMarkup(createElement(RichText, { text }));

const start = performance.now();
const heading = render("  ## Заголовок\nПосле заголовка текст.");
assert.match(heading, /<h4>Заголовок<\/h4><p>После заголовка текст\.<\/p>/);
assert.ok(performance.now() - start < 1000, "indented headings must consume input promptly");

const lists = render("  - Первый **пункт**\n  - Второй пункт\n\n  1. Первый шаг\n  2. Второй `шаг`\n\nТекст после списков.");
assert.match(lists, /<ul><li>Первый <strong>пункт<\/strong><\/li><li>Второй пункт<\/li><\/ul>/);
assert.match(lists, /<ol><li>Первый шаг<\/li><li>Второй <code>шаг<\/code><\/li><\/ol>/);
assert.match(lists, /<p>Текст после списков\.<\/p>/);

const fence = render("  ```python\nprint('<script>bad()</script>')\n  ```\nТекст после кода.");
assert.match(fence, /<pre><code>print\(&#x27;&lt;script&gt;bad\(\)&lt;\/script&gt;&#x27;\)<\/code><\/pre>/);
assert.match(fence, /<p>Текст после кода\.<\/p>/);

const html = render('<img src="x" onerror="bad()">\n\n  ## После HTML\nСодержимое сохранено.');
assert.ok(html.includes("&lt;img"), "HTML input must remain escaped text");
assert.ok(!html.includes("<img"), "untrusted input must not create HTML elements");
assert.match(html, /<h4>После HTML<\/h4><p>Содержимое сохранено\.<\/p>/);

const unmatchedFence = render("```\nНезакрытый блок <b>текст</b>");
assert.match(unmatchedFence, /<pre><code>Незакрытый блок &lt;b&gt;текст&lt;\/b&gt;<\/code><\/pre>/);
console.log("Rich-text renderer: indented heading, paragraphs, lists, code and escaped HTML passed.");
