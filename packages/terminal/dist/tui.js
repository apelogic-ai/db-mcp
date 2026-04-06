#!/usr/bin/env node
// @bun
var __create = Object.create;
var __getProtoOf = Object.getPrototypeOf;
var __defProp = Object.defineProperty;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __toESM = (mod, isNodeMode, target) => {
  target = mod != null ? __create(__getProtoOf(mod)) : {};
  const to = isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target;
  for (let key of __getOwnPropNames(mod))
    if (!__hasOwnProp.call(to, key))
      __defProp(to, key, {
        get: () => mod[key],
        enumerable: true
      });
  return to;
};
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, {
      get: all[name],
      enumerable: true,
      configurable: true,
      set: (newValue) => all[name] = () => newValue
    });
};
var __esm = (fn, res) => () => (fn && (res = fn(fn = 0)), res);
var __require = import.meta.require;

// src/acp/terminal.ts
var exports_terminal = {};
__export(exports_terminal, {
  handleWaitForTerminalExit: () => handleWaitForTerminalExit,
  handleTerminalOutput: () => handleTerminalOutput,
  handleReleaseTerminal: () => handleReleaseTerminal,
  handleCreateTerminal: () => handleCreateTerminal
});
import { execFile } from "child_process";
function handleCreateTerminal(params) {
  const id = `term-${nextId++}`;
  const args = params.args ?? [];
  const env = params.env ? Object.fromEntries(params.env.map((e) => [e.name, e.value])) : undefined;
  const state2 = {
    command: params.command,
    args,
    stdout: "",
    stderr: "",
    exitCode: null,
    done: false,
    promise: Promise.resolve()
  };
  state2.promise = new Promise((resolve) => {
    const child = execFile(params.command, args, {
      cwd: params.cwd ?? undefined,
      env: env ? { ...process.env, ...env } : undefined,
      maxBuffer: params.outputByteLimit ?? 1024 * 1024,
      timeout: 60000
    }, (error, stdout, stderr) => {
      state2.stdout = stdout;
      state2.stderr = stderr;
      state2.exitCode = error?.code !== undefined ? typeof error.code === "number" ? error.code : 1 : 0;
      state2.done = true;
      resolve();
    });
    child.on("exit", (code) => {
      if (state2.exitCode === null) {
        state2.exitCode = code ?? 0;
      }
    });
  });
  terminals.set(id, state2);
  return { terminalId: id };
}
async function handleTerminalOutput(params) {
  const state2 = terminals.get(params.terminalId);
  if (!state2) {
    return { output: "Terminal not found", truncated: false, exitStatus: { exitCode: 1 } };
  }
  await state2.promise;
  const output = state2.stderr ? `${state2.stdout}
${state2.stderr}` : state2.stdout;
  return {
    output,
    truncated: false,
    exitStatus: state2.exitCode !== null ? { exitCode: state2.exitCode } : undefined
  };
}
async function handleWaitForTerminalExit(params) {
  const state2 = terminals.get(params.terminalId);
  if (!state2)
    return { exitCode: 1 };
  await state2.promise;
  return { exitCode: state2.exitCode ?? 0 };
}
function handleReleaseTerminal(params) {
  terminals.delete(params.terminalId);
  return {};
}
var terminals, nextId = 1;
var init_terminal = __esm(() => {
  terminals = new Map;
});

// src/preflight.ts
var exports_preflight = {};
__export(exports_preflight, {
  which: () => which
});
import { existsSync } from "fs";
import { join as join4 } from "path";
function which(name) {
  const pathDirs = (process.env.PATH ?? "").split(":");
  for (const dir of pathDirs) {
    const candidate = join4(dir, name);
    if (existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}
var init_preflight = () => {};

// src/index.ts
import { appendFileSync as appendFileSync3 } from "fs";

// node_modules/@mariozechner/pi-tui/dist/autocomplete.js
import { spawn } from "child_process";
import { readdirSync, statSync } from "fs";
import { homedir } from "os";
import { basename, dirname, join } from "path";

// node_modules/@mariozechner/pi-tui/dist/fuzzy.js
function fuzzyMatch(query, text) {
  const queryLower = query.toLowerCase();
  const textLower = text.toLowerCase();
  const matchQuery = (normalizedQuery) => {
    if (normalizedQuery.length === 0) {
      return { matches: true, score: 0 };
    }
    if (normalizedQuery.length > textLower.length) {
      return { matches: false, score: 0 };
    }
    let queryIndex = 0;
    let score = 0;
    let lastMatchIndex = -1;
    let consecutiveMatches = 0;
    for (let i = 0;i < textLower.length && queryIndex < normalizedQuery.length; i++) {
      if (textLower[i] === normalizedQuery[queryIndex]) {
        const isWordBoundary = i === 0 || /[\s\-_./:]/.test(textLower[i - 1]);
        if (lastMatchIndex === i - 1) {
          consecutiveMatches++;
          score -= consecutiveMatches * 5;
        } else {
          consecutiveMatches = 0;
          if (lastMatchIndex >= 0) {
            score += (i - lastMatchIndex - 1) * 2;
          }
        }
        if (isWordBoundary) {
          score -= 10;
        }
        score += i * 0.1;
        lastMatchIndex = i;
        queryIndex++;
      }
    }
    if (queryIndex < normalizedQuery.length) {
      return { matches: false, score: 0 };
    }
    return { matches: true, score };
  };
  const primaryMatch = matchQuery(queryLower);
  if (primaryMatch.matches) {
    return primaryMatch;
  }
  const alphaNumericMatch = queryLower.match(/^(?<letters>[a-z]+)(?<digits>[0-9]+)$/);
  const numericAlphaMatch = queryLower.match(/^(?<digits>[0-9]+)(?<letters>[a-z]+)$/);
  const swappedQuery = alphaNumericMatch ? `${alphaNumericMatch.groups?.digits ?? ""}${alphaNumericMatch.groups?.letters ?? ""}` : numericAlphaMatch ? `${numericAlphaMatch.groups?.letters ?? ""}${numericAlphaMatch.groups?.digits ?? ""}` : "";
  if (!swappedQuery) {
    return primaryMatch;
  }
  const swappedMatch = matchQuery(swappedQuery);
  if (!swappedMatch.matches) {
    return primaryMatch;
  }
  return { matches: true, score: swappedMatch.score + 5 };
}
function fuzzyFilter(items, query, getText) {
  if (!query.trim()) {
    return items;
  }
  const tokens = query.trim().split(/\s+/).filter((t) => t.length > 0);
  if (tokens.length === 0) {
    return items;
  }
  const results = [];
  for (const item of items) {
    const text = getText(item);
    let totalScore = 0;
    let allMatch = true;
    for (const token of tokens) {
      const match = fuzzyMatch(token, text);
      if (match.matches) {
        totalScore += match.score;
      } else {
        allMatch = false;
        break;
      }
    }
    if (allMatch) {
      results.push({ item, totalScore });
    }
  }
  results.sort((a, b) => a.totalScore - b.totalScore);
  return results.map((r) => r.item);
}

// node_modules/@mariozechner/pi-tui/dist/autocomplete.js
var PATH_DELIMITERS = new Set([" ", "\t", '"', "'", "="]);
function toDisplayPath(value) {
  return value.replace(/\\/g, "/");
}
function escapeRegex(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
function buildFdPathQuery(query) {
  const normalized = toDisplayPath(query);
  if (!normalized.includes("/")) {
    return normalized;
  }
  const hasTrailingSeparator = normalized.endsWith("/");
  const trimmed = normalized.replace(/^\/+|\/+$/g, "");
  if (!trimmed) {
    return normalized;
  }
  const separatorPattern = "[\\\\/]";
  const segments = trimmed.split("/").filter(Boolean).map((segment) => escapeRegex(segment));
  if (segments.length === 0) {
    return normalized;
  }
  let pattern = segments.join(separatorPattern);
  if (hasTrailingSeparator) {
    pattern += separatorPattern;
  }
  return pattern;
}
function findLastDelimiter(text) {
  for (let i = text.length - 1;i >= 0; i -= 1) {
    if (PATH_DELIMITERS.has(text[i] ?? "")) {
      return i;
    }
  }
  return -1;
}
function findUnclosedQuoteStart(text) {
  let inQuotes = false;
  let quoteStart = -1;
  for (let i = 0;i < text.length; i += 1) {
    if (text[i] === '"') {
      inQuotes = !inQuotes;
      if (inQuotes) {
        quoteStart = i;
      }
    }
  }
  return inQuotes ? quoteStart : null;
}
function isTokenStart(text, index) {
  return index === 0 || PATH_DELIMITERS.has(text[index - 1] ?? "");
}
function extractQuotedPrefix(text) {
  const quoteStart = findUnclosedQuoteStart(text);
  if (quoteStart === null) {
    return null;
  }
  if (quoteStart > 0 && text[quoteStart - 1] === "@") {
    if (!isTokenStart(text, quoteStart - 1)) {
      return null;
    }
    return text.slice(quoteStart - 1);
  }
  if (!isTokenStart(text, quoteStart)) {
    return null;
  }
  return text.slice(quoteStart);
}
function parsePathPrefix(prefix) {
  if (prefix.startsWith('@"')) {
    return { rawPrefix: prefix.slice(2), isAtPrefix: true, isQuotedPrefix: true };
  }
  if (prefix.startsWith('"')) {
    return { rawPrefix: prefix.slice(1), isAtPrefix: false, isQuotedPrefix: true };
  }
  if (prefix.startsWith("@")) {
    return { rawPrefix: prefix.slice(1), isAtPrefix: true, isQuotedPrefix: false };
  }
  return { rawPrefix: prefix, isAtPrefix: false, isQuotedPrefix: false };
}
function buildCompletionValue(path, options) {
  const needsQuotes = options.isQuotedPrefix || path.includes(" ");
  const prefix = options.isAtPrefix ? "@" : "";
  if (!needsQuotes) {
    return `${prefix}${path}`;
  }
  const openQuote = `${prefix}"`;
  const closeQuote = '"';
  return `${openQuote}${path}${closeQuote}`;
}
async function walkDirectoryWithFd(baseDir, fdPath, query, maxResults, signal) {
  const args = [
    "--base-directory",
    baseDir,
    "--max-results",
    String(maxResults),
    "--type",
    "f",
    "--type",
    "d",
    "--full-path",
    "--hidden",
    "--exclude",
    ".git",
    "--exclude",
    ".git/*",
    "--exclude",
    ".git/**"
  ];
  if (query) {
    args.push(buildFdPathQuery(query));
  }
  return await new Promise((resolve) => {
    if (signal.aborted) {
      resolve([]);
      return;
    }
    const child = spawn(fdPath, args, {
      stdio: ["ignore", "pipe", "pipe"]
    });
    let stdout = "";
    let resolved = false;
    const finish = (results) => {
      if (resolved)
        return;
      resolved = true;
      signal.removeEventListener("abort", onAbort);
      resolve(results);
    };
    const onAbort = () => {
      if (child.exitCode === null) {
        child.kill("SIGKILL");
      }
    };
    signal.addEventListener("abort", onAbort, { once: true });
    child.stdout.setEncoding("utf-8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.on("error", () => {
      finish([]);
    });
    child.on("close", (code) => {
      if (signal.aborted || code !== 0 || !stdout) {
        finish([]);
        return;
      }
      const lines = stdout.trim().split(`
`).filter(Boolean);
      const results = [];
      for (const line of lines) {
        const displayLine = toDisplayPath(line);
        const hasTrailingSeparator = displayLine.endsWith("/");
        const normalizedPath = hasTrailingSeparator ? displayLine.slice(0, -1) : displayLine;
        if (normalizedPath === ".git" || normalizedPath.startsWith(".git/") || normalizedPath.includes("/.git/")) {
          continue;
        }
        results.push({
          path: displayLine,
          isDirectory: hasTrailingSeparator
        });
      }
      finish(results);
    });
  });
}

class CombinedAutocompleteProvider {
  commands;
  basePath;
  fdPath;
  constructor(commands = [], basePath = process.cwd(), fdPath = null) {
    this.commands = commands;
    this.basePath = basePath;
    this.fdPath = fdPath;
  }
  async getSuggestions(lines, cursorLine, cursorCol, options) {
    const currentLine = lines[cursorLine] || "";
    const textBeforeCursor = currentLine.slice(0, cursorCol);
    const atPrefix = this.extractAtPrefix(textBeforeCursor);
    if (atPrefix) {
      const { rawPrefix, isQuotedPrefix } = parsePathPrefix(atPrefix);
      const suggestions2 = await this.getFuzzyFileSuggestions(rawPrefix, {
        isQuotedPrefix,
        signal: options.signal
      });
      if (suggestions2.length === 0)
        return null;
      return {
        items: suggestions2,
        prefix: atPrefix
      };
    }
    if (!options.force && textBeforeCursor.startsWith("/")) {
      const spaceIndex = textBeforeCursor.indexOf(" ");
      if (spaceIndex === -1) {
        const prefix = textBeforeCursor.slice(1);
        const commandItems = this.commands.map((cmd) => ({
          name: "name" in cmd ? cmd.name : cmd.value,
          label: "name" in cmd ? cmd.name : cmd.label,
          description: cmd.description
        }));
        const filtered = fuzzyFilter(commandItems, prefix, (item) => item.name).map((item) => ({
          value: item.name,
          label: item.label,
          ...item.description && { description: item.description }
        }));
        if (filtered.length === 0)
          return null;
        return {
          items: filtered,
          prefix: textBeforeCursor
        };
      }
      const commandName = textBeforeCursor.slice(1, spaceIndex);
      const argumentText = textBeforeCursor.slice(spaceIndex + 1);
      const command = this.commands.find((cmd) => {
        const name = "name" in cmd ? cmd.name : cmd.value;
        return name === commandName;
      });
      if (!command || !("getArgumentCompletions" in command) || !command.getArgumentCompletions) {
        return null;
      }
      const argumentSuggestions = await command.getArgumentCompletions(argumentText);
      if (!Array.isArray(argumentSuggestions) || argumentSuggestions.length === 0) {
        return null;
      }
      return {
        items: argumentSuggestions,
        prefix: argumentText
      };
    }
    const pathMatch = this.extractPathPrefix(textBeforeCursor, options.force ?? false);
    if (pathMatch === null) {
      return null;
    }
    const suggestions = this.getFileSuggestions(pathMatch);
    if (suggestions.length === 0)
      return null;
    return {
      items: suggestions,
      prefix: pathMatch
    };
  }
  applyCompletion(lines, cursorLine, cursorCol, item, prefix) {
    const currentLine = lines[cursorLine] || "";
    const beforePrefix = currentLine.slice(0, cursorCol - prefix.length);
    const afterCursor = currentLine.slice(cursorCol);
    const isQuotedPrefix = prefix.startsWith('"') || prefix.startsWith('@"');
    const hasLeadingQuoteAfterCursor = afterCursor.startsWith('"');
    const hasTrailingQuoteInItem = item.value.endsWith('"');
    const adjustedAfterCursor = isQuotedPrefix && hasTrailingQuoteInItem && hasLeadingQuoteAfterCursor ? afterCursor.slice(1) : afterCursor;
    const isSlashCommand = prefix.startsWith("/") && beforePrefix.trim() === "" && !prefix.slice(1).includes("/");
    if (isSlashCommand) {
      const newLine2 = `${beforePrefix}/${item.value} ${adjustedAfterCursor}`;
      const newLines2 = [...lines];
      newLines2[cursorLine] = newLine2;
      return {
        lines: newLines2,
        cursorLine,
        cursorCol: beforePrefix.length + item.value.length + 2
      };
    }
    if (prefix.startsWith("@")) {
      const isDirectory2 = item.label.endsWith("/");
      const suffix = isDirectory2 ? "" : " ";
      const newLine2 = `${beforePrefix + item.value}${suffix}${adjustedAfterCursor}`;
      const newLines2 = [...lines];
      newLines2[cursorLine] = newLine2;
      const hasTrailingQuote2 = item.value.endsWith('"');
      const cursorOffset2 = isDirectory2 && hasTrailingQuote2 ? item.value.length - 1 : item.value.length;
      return {
        lines: newLines2,
        cursorLine,
        cursorCol: beforePrefix.length + cursorOffset2 + suffix.length
      };
    }
    const textBeforeCursor = currentLine.slice(0, cursorCol);
    if (textBeforeCursor.includes("/") && textBeforeCursor.includes(" ")) {
      const newLine2 = beforePrefix + item.value + adjustedAfterCursor;
      const newLines2 = [...lines];
      newLines2[cursorLine] = newLine2;
      const isDirectory2 = item.label.endsWith("/");
      const hasTrailingQuote2 = item.value.endsWith('"');
      const cursorOffset2 = isDirectory2 && hasTrailingQuote2 ? item.value.length - 1 : item.value.length;
      return {
        lines: newLines2,
        cursorLine,
        cursorCol: beforePrefix.length + cursorOffset2
      };
    }
    const newLine = beforePrefix + item.value + adjustedAfterCursor;
    const newLines = [...lines];
    newLines[cursorLine] = newLine;
    const isDirectory = item.label.endsWith("/");
    const hasTrailingQuote = item.value.endsWith('"');
    const cursorOffset = isDirectory && hasTrailingQuote ? item.value.length - 1 : item.value.length;
    return {
      lines: newLines,
      cursorLine,
      cursorCol: beforePrefix.length + cursorOffset
    };
  }
  extractAtPrefix(text) {
    const quotedPrefix = extractQuotedPrefix(text);
    if (quotedPrefix?.startsWith('@"')) {
      return quotedPrefix;
    }
    const lastDelimiterIndex = findLastDelimiter(text);
    const tokenStart = lastDelimiterIndex === -1 ? 0 : lastDelimiterIndex + 1;
    if (text[tokenStart] === "@") {
      return text.slice(tokenStart);
    }
    return null;
  }
  extractPathPrefix(text, forceExtract = false) {
    const quotedPrefix = extractQuotedPrefix(text);
    if (quotedPrefix) {
      return quotedPrefix;
    }
    const lastDelimiterIndex = findLastDelimiter(text);
    const pathPrefix = lastDelimiterIndex === -1 ? text : text.slice(lastDelimiterIndex + 1);
    if (forceExtract) {
      return pathPrefix;
    }
    if (pathPrefix.includes("/") || pathPrefix.startsWith(".") || pathPrefix.startsWith("~/")) {
      return pathPrefix;
    }
    if (pathPrefix === "" && text.endsWith(" ")) {
      return pathPrefix;
    }
    return null;
  }
  expandHomePath(path) {
    if (path.startsWith("~/")) {
      const expandedPath = join(homedir(), path.slice(2));
      return path.endsWith("/") && !expandedPath.endsWith("/") ? `${expandedPath}/` : expandedPath;
    } else if (path === "~") {
      return homedir();
    }
    return path;
  }
  resolveScopedFuzzyQuery(rawQuery) {
    const normalizedQuery = toDisplayPath(rawQuery);
    const slashIndex = normalizedQuery.lastIndexOf("/");
    if (slashIndex === -1) {
      return null;
    }
    const displayBase = normalizedQuery.slice(0, slashIndex + 1);
    const query = normalizedQuery.slice(slashIndex + 1);
    let baseDir;
    if (displayBase.startsWith("~/")) {
      baseDir = this.expandHomePath(displayBase);
    } else if (displayBase.startsWith("/")) {
      baseDir = displayBase;
    } else {
      baseDir = join(this.basePath, displayBase);
    }
    try {
      if (!statSync(baseDir).isDirectory()) {
        return null;
      }
    } catch {
      return null;
    }
    return { baseDir, query, displayBase };
  }
  scopedPathForDisplay(displayBase, relativePath) {
    const normalizedRelativePath = toDisplayPath(relativePath);
    if (displayBase === "/") {
      return `/${normalizedRelativePath}`;
    }
    return `${toDisplayPath(displayBase)}${normalizedRelativePath}`;
  }
  getFileSuggestions(prefix) {
    try {
      let searchDir;
      let searchPrefix;
      const { rawPrefix, isAtPrefix, isQuotedPrefix } = parsePathPrefix(prefix);
      let expandedPrefix = rawPrefix;
      if (expandedPrefix.startsWith("~")) {
        expandedPrefix = this.expandHomePath(expandedPrefix);
      }
      const isRootPrefix = rawPrefix === "" || rawPrefix === "./" || rawPrefix === "../" || rawPrefix === "~" || rawPrefix === "~/" || rawPrefix === "/" || isAtPrefix && rawPrefix === "";
      if (isRootPrefix) {
        if (rawPrefix.startsWith("~") || expandedPrefix.startsWith("/")) {
          searchDir = expandedPrefix;
        } else {
          searchDir = join(this.basePath, expandedPrefix);
        }
        searchPrefix = "";
      } else if (rawPrefix.endsWith("/")) {
        if (rawPrefix.startsWith("~") || expandedPrefix.startsWith("/")) {
          searchDir = expandedPrefix;
        } else {
          searchDir = join(this.basePath, expandedPrefix);
        }
        searchPrefix = "";
      } else {
        const dir = dirname(expandedPrefix);
        const file = basename(expandedPrefix);
        if (rawPrefix.startsWith("~") || expandedPrefix.startsWith("/")) {
          searchDir = dir;
        } else {
          searchDir = join(this.basePath, dir);
        }
        searchPrefix = file;
      }
      const entries = readdirSync(searchDir, { withFileTypes: true });
      const suggestions = [];
      for (const entry of entries) {
        if (!entry.name.toLowerCase().startsWith(searchPrefix.toLowerCase())) {
          continue;
        }
        let isDirectory = entry.isDirectory();
        if (!isDirectory && entry.isSymbolicLink()) {
          try {
            const fullPath = join(searchDir, entry.name);
            isDirectory = statSync(fullPath).isDirectory();
          } catch {}
        }
        let relativePath;
        const name = entry.name;
        const displayPrefix = rawPrefix;
        if (displayPrefix.endsWith("/")) {
          relativePath = displayPrefix + name;
        } else if (displayPrefix.includes("/") || displayPrefix.includes("\\")) {
          if (displayPrefix.startsWith("~/")) {
            const homeRelativeDir = displayPrefix.slice(2);
            const dir = dirname(homeRelativeDir);
            relativePath = `~/${dir === "." ? name : join(dir, name)}`;
          } else if (displayPrefix.startsWith("/")) {
            const dir = dirname(displayPrefix);
            if (dir === "/") {
              relativePath = `/${name}`;
            } else {
              relativePath = `${dir}/${name}`;
            }
          } else {
            relativePath = join(dirname(displayPrefix), name);
            if (displayPrefix.startsWith("./") && !relativePath.startsWith("./")) {
              relativePath = `./${relativePath}`;
            }
          }
        } else {
          if (displayPrefix.startsWith("~")) {
            relativePath = `~/${name}`;
          } else {
            relativePath = name;
          }
        }
        relativePath = toDisplayPath(relativePath);
        const pathValue = isDirectory ? `${relativePath}/` : relativePath;
        const value = buildCompletionValue(pathValue, {
          isDirectory,
          isAtPrefix,
          isQuotedPrefix
        });
        suggestions.push({
          value,
          label: name + (isDirectory ? "/" : "")
        });
      }
      suggestions.sort((a, b) => {
        const aIsDir = a.value.endsWith("/");
        const bIsDir = b.value.endsWith("/");
        if (aIsDir && !bIsDir)
          return -1;
        if (!aIsDir && bIsDir)
          return 1;
        return a.label.localeCompare(b.label);
      });
      return suggestions;
    } catch (_e) {
      return [];
    }
  }
  scoreEntry(filePath, query, isDirectory) {
    const fileName = basename(filePath);
    const lowerFileName = fileName.toLowerCase();
    const lowerQuery = query.toLowerCase();
    let score = 0;
    if (lowerFileName === lowerQuery)
      score = 100;
    else if (lowerFileName.startsWith(lowerQuery))
      score = 80;
    else if (lowerFileName.includes(lowerQuery))
      score = 50;
    else if (filePath.toLowerCase().includes(lowerQuery))
      score = 30;
    if (isDirectory && score > 0)
      score += 10;
    return score;
  }
  async getFuzzyFileSuggestions(query, options) {
    if (!this.fdPath || options.signal.aborted) {
      return [];
    }
    try {
      const scopedQuery = this.resolveScopedFuzzyQuery(query);
      const fdBaseDir = scopedQuery?.baseDir ?? this.basePath;
      const fdQuery = scopedQuery?.query ?? query;
      const entries = await walkDirectoryWithFd(fdBaseDir, this.fdPath, fdQuery, 100, options.signal);
      if (options.signal.aborted) {
        return [];
      }
      const scoredEntries = entries.map((entry) => ({
        ...entry,
        score: fdQuery ? this.scoreEntry(entry.path, fdQuery, entry.isDirectory) : 1
      })).filter((entry) => entry.score > 0);
      scoredEntries.sort((a, b) => b.score - a.score);
      const topEntries = scoredEntries.slice(0, 20);
      const suggestions = [];
      for (const { path: entryPath, isDirectory } of topEntries) {
        const pathWithoutSlash = isDirectory ? entryPath.slice(0, -1) : entryPath;
        const displayPath = scopedQuery ? this.scopedPathForDisplay(scopedQuery.displayBase, pathWithoutSlash) : pathWithoutSlash;
        const entryName = basename(pathWithoutSlash);
        const completionPath = isDirectory ? `${displayPath}/` : displayPath;
        const value = buildCompletionValue(completionPath, {
          isDirectory,
          isAtPrefix: true,
          isQuotedPrefix: options.isQuotedPrefix
        });
        suggestions.push({
          value,
          label: entryName + (isDirectory ? "/" : ""),
          description: displayPath
        });
      }
      return suggestions;
    } catch {
      return [];
    }
  }
  shouldTriggerFileCompletion(lines, cursorLine, cursorCol) {
    const currentLine = lines[cursorLine] || "";
    const textBeforeCursor = currentLine.slice(0, cursorCol);
    if (textBeforeCursor.trim().startsWith("/") && !textBeforeCursor.trim().includes(" ")) {
      return false;
    }
    return true;
  }
}
// node_modules/get-east-asian-width/lookup-data.js
var ambiguousRanges = [161, 161, 164, 164, 167, 168, 170, 170, 173, 174, 176, 180, 182, 186, 188, 191, 198, 198, 208, 208, 215, 216, 222, 225, 230, 230, 232, 234, 236, 237, 240, 240, 242, 243, 247, 250, 252, 252, 254, 254, 257, 257, 273, 273, 275, 275, 283, 283, 294, 295, 299, 299, 305, 307, 312, 312, 319, 322, 324, 324, 328, 331, 333, 333, 338, 339, 358, 359, 363, 363, 462, 462, 464, 464, 466, 466, 468, 468, 470, 470, 472, 472, 474, 474, 476, 476, 593, 593, 609, 609, 708, 708, 711, 711, 713, 715, 717, 717, 720, 720, 728, 731, 733, 733, 735, 735, 768, 879, 913, 929, 931, 937, 945, 961, 963, 969, 1025, 1025, 1040, 1103, 1105, 1105, 8208, 8208, 8211, 8214, 8216, 8217, 8220, 8221, 8224, 8226, 8228, 8231, 8240, 8240, 8242, 8243, 8245, 8245, 8251, 8251, 8254, 8254, 8308, 8308, 8319, 8319, 8321, 8324, 8364, 8364, 8451, 8451, 8453, 8453, 8457, 8457, 8467, 8467, 8470, 8470, 8481, 8482, 8486, 8486, 8491, 8491, 8531, 8532, 8539, 8542, 8544, 8555, 8560, 8569, 8585, 8585, 8592, 8601, 8632, 8633, 8658, 8658, 8660, 8660, 8679, 8679, 8704, 8704, 8706, 8707, 8711, 8712, 8715, 8715, 8719, 8719, 8721, 8721, 8725, 8725, 8730, 8730, 8733, 8736, 8739, 8739, 8741, 8741, 8743, 8748, 8750, 8750, 8756, 8759, 8764, 8765, 8776, 8776, 8780, 8780, 8786, 8786, 8800, 8801, 8804, 8807, 8810, 8811, 8814, 8815, 8834, 8835, 8838, 8839, 8853, 8853, 8857, 8857, 8869, 8869, 8895, 8895, 8978, 8978, 9312, 9449, 9451, 9547, 9552, 9587, 9600, 9615, 9618, 9621, 9632, 9633, 9635, 9641, 9650, 9651, 9654, 9655, 9660, 9661, 9664, 9665, 9670, 9672, 9675, 9675, 9678, 9681, 9698, 9701, 9711, 9711, 9733, 9734, 9737, 9737, 9742, 9743, 9756, 9756, 9758, 9758, 9792, 9792, 9794, 9794, 9824, 9825, 9827, 9829, 9831, 9834, 9836, 9837, 9839, 9839, 9886, 9887, 9919, 9919, 9926, 9933, 9935, 9939, 9941, 9953, 9955, 9955, 9960, 9961, 9963, 9969, 9972, 9972, 9974, 9977, 9979, 9980, 9982, 9983, 10045, 10045, 10102, 10111, 11094, 11097, 12872, 12879, 57344, 63743, 65024, 65039, 65533, 65533, 127232, 127242, 127248, 127277, 127280, 127337, 127344, 127373, 127375, 127376, 127387, 127404, 917760, 917999, 983040, 1048573, 1048576, 1114109];
var fullwidthRanges = [12288, 12288, 65281, 65376, 65504, 65510];
var halfwidthRanges = [8361, 8361, 65377, 65470, 65474, 65479, 65482, 65487, 65490, 65495, 65498, 65500, 65512, 65518];
var narrowRanges = [32, 126, 162, 163, 165, 166, 172, 172, 175, 175, 10214, 10221, 10629, 10630];
var wideRanges = [4352, 4447, 8986, 8987, 9001, 9002, 9193, 9196, 9200, 9200, 9203, 9203, 9725, 9726, 9748, 9749, 9776, 9783, 9800, 9811, 9855, 9855, 9866, 9871, 9875, 9875, 9889, 9889, 9898, 9899, 9917, 9918, 9924, 9925, 9934, 9934, 9940, 9940, 9962, 9962, 9970, 9971, 9973, 9973, 9978, 9978, 9981, 9981, 9989, 9989, 9994, 9995, 10024, 10024, 10060, 10060, 10062, 10062, 10067, 10069, 10071, 10071, 10133, 10135, 10160, 10160, 10175, 10175, 11035, 11036, 11088, 11088, 11093, 11093, 11904, 11929, 11931, 12019, 12032, 12245, 12272, 12287, 12289, 12350, 12353, 12438, 12441, 12543, 12549, 12591, 12593, 12686, 12688, 12773, 12783, 12830, 12832, 12871, 12880, 42124, 42128, 42182, 43360, 43388, 44032, 55203, 63744, 64255, 65040, 65049, 65072, 65106, 65108, 65126, 65128, 65131, 94176, 94180, 94192, 94198, 94208, 101589, 101631, 101662, 101760, 101874, 110576, 110579, 110581, 110587, 110589, 110590, 110592, 110882, 110898, 110898, 110928, 110930, 110933, 110933, 110948, 110951, 110960, 111355, 119552, 119638, 119648, 119670, 126980, 126980, 127183, 127183, 127374, 127374, 127377, 127386, 127488, 127490, 127504, 127547, 127552, 127560, 127568, 127569, 127584, 127589, 127744, 127776, 127789, 127797, 127799, 127868, 127870, 127891, 127904, 127946, 127951, 127955, 127968, 127984, 127988, 127988, 127992, 128062, 128064, 128064, 128066, 128252, 128255, 128317, 128331, 128334, 128336, 128359, 128378, 128378, 128405, 128406, 128420, 128420, 128507, 128591, 128640, 128709, 128716, 128716, 128720, 128722, 128725, 128728, 128732, 128735, 128747, 128748, 128756, 128764, 128992, 129003, 129008, 129008, 129292, 129338, 129340, 129349, 129351, 129535, 129648, 129660, 129664, 129674, 129678, 129734, 129736, 129736, 129741, 129756, 129759, 129770, 129775, 129784, 131072, 196605, 196608, 262141];

// node_modules/get-east-asian-width/utilities.js
var isInRange = (ranges, codePoint) => {
  let low = 0;
  let high = Math.floor(ranges.length / 2) - 1;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const i = mid * 2;
    if (codePoint < ranges[i]) {
      high = mid - 1;
    } else if (codePoint > ranges[i + 1]) {
      low = mid + 1;
    } else {
      return true;
    }
  }
  return false;
};

// node_modules/get-east-asian-width/lookup.js
var minimumAmbiguousCodePoint = ambiguousRanges[0];
var maximumAmbiguousCodePoint = ambiguousRanges.at(-1);
var minimumFullWidthCodePoint = fullwidthRanges[0];
var maximumFullWidthCodePoint = fullwidthRanges.at(-1);
var minimumHalfWidthCodePoint = halfwidthRanges[0];
var maximumHalfWidthCodePoint = halfwidthRanges.at(-1);
var minimumNarrowCodePoint = narrowRanges[0];
var maximumNarrowCodePoint = narrowRanges.at(-1);
var minimumWideCodePoint = wideRanges[0];
var maximumWideCodePoint = wideRanges.at(-1);
var commonCjkCodePoint = 19968;
var [wideFastPathStart, wideFastPathEnd] = findWideFastPathRange(wideRanges);
function findWideFastPathRange(ranges) {
  let fastPathStart = ranges[0];
  let fastPathEnd = ranges[1];
  for (let index = 0;index < ranges.length; index += 2) {
    const start = ranges[index];
    const end = ranges[index + 1];
    if (commonCjkCodePoint >= start && commonCjkCodePoint <= end) {
      return [start, end];
    }
    if (end - start > fastPathEnd - fastPathStart) {
      fastPathStart = start;
      fastPathEnd = end;
    }
  }
  return [fastPathStart, fastPathEnd];
}
var isAmbiguous = (codePoint) => {
  if (codePoint < minimumAmbiguousCodePoint || codePoint > maximumAmbiguousCodePoint) {
    return false;
  }
  return isInRange(ambiguousRanges, codePoint);
};
var isFullWidth = (codePoint) => {
  if (codePoint < minimumFullWidthCodePoint || codePoint > maximumFullWidthCodePoint) {
    return false;
  }
  return isInRange(fullwidthRanges, codePoint);
};
var isWide = (codePoint) => {
  if (codePoint >= wideFastPathStart && codePoint <= wideFastPathEnd) {
    return true;
  }
  if (codePoint < minimumWideCodePoint || codePoint > maximumWideCodePoint) {
    return false;
  }
  return isInRange(wideRanges, codePoint);
};

// node_modules/get-east-asian-width/index.js
function validate(codePoint) {
  if (!Number.isSafeInteger(codePoint)) {
    throw new TypeError(`Expected a code point, got \`${typeof codePoint}\`.`);
  }
}
function eastAsianWidth(codePoint, { ambiguousAsWide = false } = {}) {
  validate(codePoint);
  if (isFullWidth(codePoint) || isWide(codePoint) || ambiguousAsWide && isAmbiguous(codePoint)) {
    return 2;
  }
  return 1;
}

// node_modules/@mariozechner/pi-tui/dist/utils.js
var segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
function getSegmenter() {
  return segmenter;
}
function couldBeEmoji(segment) {
  const cp = segment.codePointAt(0);
  return cp >= 126976 && cp <= 130047 || cp >= 8960 && cp <= 9215 || cp >= 9728 && cp <= 10175 || cp >= 11088 && cp <= 11093 || segment.includes("\uFE0F") || segment.length > 2;
}
var zeroWidthRegex = /^(?:\p{Default_Ignorable_Code_Point}|\p{Control}|\p{Mark}|\p{Surrogate})+$/v;
var leadingNonPrintingRegex = /^[\p{Default_Ignorable_Code_Point}\p{Control}\p{Format}\p{Mark}\p{Surrogate}]+/v;
var rgiEmojiRegex = /^\p{RGI_Emoji}$/v;
var WIDTH_CACHE_SIZE = 512;
var widthCache = new Map;
function isPrintableAscii(str) {
  for (let i = 0;i < str.length; i++) {
    const code = str.charCodeAt(i);
    if (code < 32 || code > 126) {
      return false;
    }
  }
  return true;
}
function truncateFragmentToWidth(text, maxWidth) {
  if (maxWidth <= 0 || text.length === 0) {
    return { text: "", width: 0 };
  }
  if (isPrintableAscii(text)) {
    const clipped = text.slice(0, maxWidth);
    return { text: clipped, width: clipped.length };
  }
  const hasAnsi = text.includes("\x1B");
  const hasTabs = text.includes("\t");
  if (!hasAnsi && !hasTabs) {
    let result2 = "";
    let width2 = 0;
    for (const { segment } of segmenter.segment(text)) {
      const w = graphemeWidth(segment);
      if (width2 + w > maxWidth) {
        break;
      }
      result2 += segment;
      width2 += w;
    }
    return { text: result2, width: width2 };
  }
  let result = "";
  let width = 0;
  let i = 0;
  let pendingAnsi = "";
  while (i < text.length) {
    const ansi = extractAnsiCode(text, i);
    if (ansi) {
      pendingAnsi += ansi.code;
      i += ansi.length;
      continue;
    }
    if (text[i] === "\t") {
      if (width + 3 > maxWidth) {
        break;
      }
      if (pendingAnsi) {
        result += pendingAnsi;
        pendingAnsi = "";
      }
      result += "\t";
      width += 3;
      i++;
      continue;
    }
    let end = i;
    while (end < text.length && text[end] !== "\t") {
      const nextAnsi = extractAnsiCode(text, end);
      if (nextAnsi) {
        break;
      }
      end++;
    }
    for (const { segment } of segmenter.segment(text.slice(i, end))) {
      const w = graphemeWidth(segment);
      if (width + w > maxWidth) {
        return { text: result, width };
      }
      if (pendingAnsi) {
        result += pendingAnsi;
        pendingAnsi = "";
      }
      result += segment;
      width += w;
    }
    i = end;
  }
  return { text: result, width };
}
function finalizeTruncatedResult(prefix, prefixWidth, ellipsis, ellipsisWidth, maxWidth, pad) {
  const reset = "\x1B[0m";
  const visibleWidth = prefixWidth + ellipsisWidth;
  let result;
  if (ellipsis.length > 0) {
    result = `${prefix}${reset}${ellipsis}${reset}`;
  } else {
    result = `${prefix}${reset}`;
  }
  return pad ? result + " ".repeat(Math.max(0, maxWidth - visibleWidth)) : result;
}
function graphemeWidth(segment) {
  if (zeroWidthRegex.test(segment)) {
    return 0;
  }
  if (couldBeEmoji(segment) && rgiEmojiRegex.test(segment)) {
    return 2;
  }
  const base = segment.replace(leadingNonPrintingRegex, "");
  const cp = base.codePointAt(0);
  if (cp === undefined) {
    return 0;
  }
  if (cp >= 127462 && cp <= 127487) {
    return 2;
  }
  let width = eastAsianWidth(cp);
  if (segment.length > 1) {
    for (const char of segment.slice(1)) {
      const c = char.codePointAt(0);
      if (c >= 65280 && c <= 65519) {
        width += eastAsianWidth(c);
      }
    }
  }
  return width;
}
function visibleWidth(str) {
  if (str.length === 0) {
    return 0;
  }
  if (isPrintableAscii(str)) {
    return str.length;
  }
  const cached = widthCache.get(str);
  if (cached !== undefined) {
    return cached;
  }
  let clean = str;
  if (str.includes("\t")) {
    clean = clean.replace(/\t/g, "   ");
  }
  if (clean.includes("\x1B")) {
    let stripped = "";
    let i = 0;
    while (i < clean.length) {
      const ansi = extractAnsiCode(clean, i);
      if (ansi) {
        i += ansi.length;
        continue;
      }
      stripped += clean[i];
      i++;
    }
    clean = stripped;
  }
  let width = 0;
  for (const { segment } of segmenter.segment(clean)) {
    width += graphemeWidth(segment);
  }
  if (widthCache.size >= WIDTH_CACHE_SIZE) {
    const firstKey = widthCache.keys().next().value;
    if (firstKey !== undefined) {
      widthCache.delete(firstKey);
    }
  }
  widthCache.set(str, width);
  return width;
}
function extractAnsiCode(str, pos) {
  if (pos >= str.length || str[pos] !== "\x1B")
    return null;
  const next = str[pos + 1];
  if (next === "[") {
    let j = pos + 2;
    while (j < str.length && !/[mGKHJ]/.test(str[j]))
      j++;
    if (j < str.length)
      return { code: str.substring(pos, j + 1), length: j + 1 - pos };
    return null;
  }
  if (next === "]") {
    let j = pos + 2;
    while (j < str.length) {
      if (str[j] === "\x07")
        return { code: str.substring(pos, j + 1), length: j + 1 - pos };
      if (str[j] === "\x1B" && str[j + 1] === "\\")
        return { code: str.substring(pos, j + 2), length: j + 2 - pos };
      j++;
    }
    return null;
  }
  if (next === "_") {
    let j = pos + 2;
    while (j < str.length) {
      if (str[j] === "\x07")
        return { code: str.substring(pos, j + 1), length: j + 1 - pos };
      if (str[j] === "\x1B" && str[j + 1] === "\\")
        return { code: str.substring(pos, j + 2), length: j + 2 - pos };
      j++;
    }
    return null;
  }
  return null;
}

class AnsiCodeTracker {
  bold = false;
  dim = false;
  italic = false;
  underline = false;
  blink = false;
  inverse = false;
  hidden = false;
  strikethrough = false;
  fgColor = null;
  bgColor = null;
  process(ansiCode) {
    if (!ansiCode.endsWith("m")) {
      return;
    }
    const match = ansiCode.match(/\x1b\[([\d;]*)m/);
    if (!match)
      return;
    const params = match[1];
    if (params === "" || params === "0") {
      this.reset();
      return;
    }
    const parts = params.split(";");
    let i = 0;
    while (i < parts.length) {
      const code = Number.parseInt(parts[i], 10);
      if (code === 38 || code === 48) {
        if (parts[i + 1] === "5" && parts[i + 2] !== undefined) {
          const colorCode = `${parts[i]};${parts[i + 1]};${parts[i + 2]}`;
          if (code === 38) {
            this.fgColor = colorCode;
          } else {
            this.bgColor = colorCode;
          }
          i += 3;
          continue;
        } else if (parts[i + 1] === "2" && parts[i + 4] !== undefined) {
          const colorCode = `${parts[i]};${parts[i + 1]};${parts[i + 2]};${parts[i + 3]};${parts[i + 4]}`;
          if (code === 38) {
            this.fgColor = colorCode;
          } else {
            this.bgColor = colorCode;
          }
          i += 5;
          continue;
        }
      }
      switch (code) {
        case 0:
          this.reset();
          break;
        case 1:
          this.bold = true;
          break;
        case 2:
          this.dim = true;
          break;
        case 3:
          this.italic = true;
          break;
        case 4:
          this.underline = true;
          break;
        case 5:
          this.blink = true;
          break;
        case 7:
          this.inverse = true;
          break;
        case 8:
          this.hidden = true;
          break;
        case 9:
          this.strikethrough = true;
          break;
        case 21:
          this.bold = false;
          break;
        case 22:
          this.bold = false;
          this.dim = false;
          break;
        case 23:
          this.italic = false;
          break;
        case 24:
          this.underline = false;
          break;
        case 25:
          this.blink = false;
          break;
        case 27:
          this.inverse = false;
          break;
        case 28:
          this.hidden = false;
          break;
        case 29:
          this.strikethrough = false;
          break;
        case 39:
          this.fgColor = null;
          break;
        case 49:
          this.bgColor = null;
          break;
        default:
          if (code >= 30 && code <= 37 || code >= 90 && code <= 97) {
            this.fgColor = String(code);
          } else if (code >= 40 && code <= 47 || code >= 100 && code <= 107) {
            this.bgColor = String(code);
          }
          break;
      }
      i++;
    }
  }
  reset() {
    this.bold = false;
    this.dim = false;
    this.italic = false;
    this.underline = false;
    this.blink = false;
    this.inverse = false;
    this.hidden = false;
    this.strikethrough = false;
    this.fgColor = null;
    this.bgColor = null;
  }
  clear() {
    this.reset();
  }
  getActiveCodes() {
    const codes = [];
    if (this.bold)
      codes.push("1");
    if (this.dim)
      codes.push("2");
    if (this.italic)
      codes.push("3");
    if (this.underline)
      codes.push("4");
    if (this.blink)
      codes.push("5");
    if (this.inverse)
      codes.push("7");
    if (this.hidden)
      codes.push("8");
    if (this.strikethrough)
      codes.push("9");
    if (this.fgColor)
      codes.push(this.fgColor);
    if (this.bgColor)
      codes.push(this.bgColor);
    if (codes.length === 0)
      return "";
    return `\x1B[${codes.join(";")}m`;
  }
  hasActiveCodes() {
    return this.bold || this.dim || this.italic || this.underline || this.blink || this.inverse || this.hidden || this.strikethrough || this.fgColor !== null || this.bgColor !== null;
  }
  getLineEndReset() {
    if (this.underline) {
      return "\x1B[24m";
    }
    return "";
  }
}
function updateTrackerFromText(text, tracker) {
  let i = 0;
  while (i < text.length) {
    const ansiResult = extractAnsiCode(text, i);
    if (ansiResult) {
      tracker.process(ansiResult.code);
      i += ansiResult.length;
    } else {
      i++;
    }
  }
}
function splitIntoTokensWithAnsi(text) {
  const tokens = [];
  let current = "";
  let pendingAnsi = "";
  let inWhitespace = false;
  let i = 0;
  while (i < text.length) {
    const ansiResult = extractAnsiCode(text, i);
    if (ansiResult) {
      pendingAnsi += ansiResult.code;
      i += ansiResult.length;
      continue;
    }
    const char = text[i];
    const charIsSpace = char === " ";
    if (charIsSpace !== inWhitespace && current) {
      tokens.push(current);
      current = "";
    }
    if (pendingAnsi) {
      current += pendingAnsi;
      pendingAnsi = "";
    }
    inWhitespace = charIsSpace;
    current += char;
    i++;
  }
  if (pendingAnsi) {
    current += pendingAnsi;
  }
  if (current) {
    tokens.push(current);
  }
  return tokens;
}
function wrapTextWithAnsi(text, width) {
  if (!text) {
    return [""];
  }
  const inputLines = text.split(`
`);
  const result = [];
  const tracker = new AnsiCodeTracker;
  for (const inputLine of inputLines) {
    const prefix = result.length > 0 ? tracker.getActiveCodes() : "";
    result.push(...wrapSingleLine(prefix + inputLine, width));
    updateTrackerFromText(inputLine, tracker);
  }
  return result.length > 0 ? result : [""];
}
function wrapSingleLine(line, width) {
  if (!line) {
    return [""];
  }
  const visibleLength = visibleWidth(line);
  if (visibleLength <= width) {
    return [line];
  }
  const wrapped = [];
  const tracker = new AnsiCodeTracker;
  const tokens = splitIntoTokensWithAnsi(line);
  let currentLine = "";
  let currentVisibleLength = 0;
  for (const token of tokens) {
    const tokenVisibleLength = visibleWidth(token);
    const isWhitespace = token.trim() === "";
    if (tokenVisibleLength > width && !isWhitespace) {
      if (currentLine) {
        const lineEndReset = tracker.getLineEndReset();
        if (lineEndReset) {
          currentLine += lineEndReset;
        }
        wrapped.push(currentLine);
        currentLine = "";
        currentVisibleLength = 0;
      }
      const broken = breakLongWord(token, width, tracker);
      wrapped.push(...broken.slice(0, -1));
      currentLine = broken[broken.length - 1];
      currentVisibleLength = visibleWidth(currentLine);
      continue;
    }
    const totalNeeded = currentVisibleLength + tokenVisibleLength;
    if (totalNeeded > width && currentVisibleLength > 0) {
      let lineToWrap = currentLine.trimEnd();
      const lineEndReset = tracker.getLineEndReset();
      if (lineEndReset) {
        lineToWrap += lineEndReset;
      }
      wrapped.push(lineToWrap);
      if (isWhitespace) {
        currentLine = tracker.getActiveCodes();
        currentVisibleLength = 0;
      } else {
        currentLine = tracker.getActiveCodes() + token;
        currentVisibleLength = tokenVisibleLength;
      }
    } else {
      currentLine += token;
      currentVisibleLength += tokenVisibleLength;
    }
    updateTrackerFromText(token, tracker);
  }
  if (currentLine) {
    wrapped.push(currentLine);
  }
  return wrapped.length > 0 ? wrapped.map((line2) => line2.trimEnd()) : [""];
}
var PUNCTUATION_REGEX = /[(){}[\]<>.,;:'"!?+\-=*/\\|&%^$#@~`]/;
function isWhitespaceChar(char) {
  return /\s/.test(char);
}
function isPunctuationChar(char) {
  return PUNCTUATION_REGEX.test(char);
}
function breakLongWord(word, width, tracker) {
  const lines = [];
  let currentLine = tracker.getActiveCodes();
  let currentWidth = 0;
  let i = 0;
  const segments = [];
  while (i < word.length) {
    const ansiResult = extractAnsiCode(word, i);
    if (ansiResult) {
      segments.push({ type: "ansi", value: ansiResult.code });
      i += ansiResult.length;
    } else {
      let end = i;
      while (end < word.length) {
        const nextAnsi = extractAnsiCode(word, end);
        if (nextAnsi)
          break;
        end++;
      }
      const textPortion = word.slice(i, end);
      for (const seg of segmenter.segment(textPortion)) {
        segments.push({ type: "grapheme", value: seg.segment });
      }
      i = end;
    }
  }
  for (const seg of segments) {
    if (seg.type === "ansi") {
      currentLine += seg.value;
      tracker.process(seg.value);
      continue;
    }
    const grapheme = seg.value;
    if (!grapheme)
      continue;
    const graphemeWidth2 = visibleWidth(grapheme);
    if (currentWidth + graphemeWidth2 > width) {
      const lineEndReset = tracker.getLineEndReset();
      if (lineEndReset) {
        currentLine += lineEndReset;
      }
      lines.push(currentLine);
      currentLine = tracker.getActiveCodes();
      currentWidth = 0;
    }
    currentLine += grapheme;
    currentWidth += graphemeWidth2;
  }
  if (currentLine) {
    lines.push(currentLine);
  }
  return lines.length > 0 ? lines : [""];
}
function applyBackgroundToLine(line, width, bgFn) {
  const visibleLen = visibleWidth(line);
  const paddingNeeded = Math.max(0, width - visibleLen);
  const padding = " ".repeat(paddingNeeded);
  const withPadding = line + padding;
  return bgFn(withPadding);
}
function truncateToWidth(text, maxWidth, ellipsis = "...", pad = false) {
  if (maxWidth <= 0) {
    return "";
  }
  if (text.length === 0) {
    return pad ? " ".repeat(maxWidth) : "";
  }
  const ellipsisWidth = visibleWidth(ellipsis);
  if (ellipsisWidth >= maxWidth) {
    const textWidth = visibleWidth(text);
    if (textWidth <= maxWidth) {
      return pad ? text + " ".repeat(maxWidth - textWidth) : text;
    }
    const clippedEllipsis = truncateFragmentToWidth(ellipsis, maxWidth);
    if (clippedEllipsis.width === 0) {
      return pad ? " ".repeat(maxWidth) : "";
    }
    return finalizeTruncatedResult("", 0, clippedEllipsis.text, clippedEllipsis.width, maxWidth, pad);
  }
  if (isPrintableAscii(text)) {
    if (text.length <= maxWidth) {
      return pad ? text + " ".repeat(maxWidth - text.length) : text;
    }
    const targetWidth2 = maxWidth - ellipsisWidth;
    return finalizeTruncatedResult(text.slice(0, targetWidth2), targetWidth2, ellipsis, ellipsisWidth, maxWidth, pad);
  }
  const targetWidth = maxWidth - ellipsisWidth;
  let result = "";
  let pendingAnsi = "";
  let visibleSoFar = 0;
  let keptWidth = 0;
  let keepContiguousPrefix = true;
  let overflowed = false;
  let exhaustedInput = false;
  const hasAnsi = text.includes("\x1B");
  const hasTabs = text.includes("\t");
  if (!hasAnsi && !hasTabs) {
    for (const { segment } of segmenter.segment(text)) {
      const width = graphemeWidth(segment);
      if (keepContiguousPrefix && keptWidth + width <= targetWidth) {
        result += segment;
        keptWidth += width;
      } else {
        keepContiguousPrefix = false;
      }
      visibleSoFar += width;
      if (visibleSoFar > maxWidth) {
        overflowed = true;
        break;
      }
    }
    exhaustedInput = !overflowed;
  } else {
    let i = 0;
    while (i < text.length) {
      const ansi = extractAnsiCode(text, i);
      if (ansi) {
        pendingAnsi += ansi.code;
        i += ansi.length;
        continue;
      }
      if (text[i] === "\t") {
        if (keepContiguousPrefix && keptWidth + 3 <= targetWidth) {
          if (pendingAnsi) {
            result += pendingAnsi;
            pendingAnsi = "";
          }
          result += "\t";
          keptWidth += 3;
        } else {
          keepContiguousPrefix = false;
          pendingAnsi = "";
        }
        visibleSoFar += 3;
        if (visibleSoFar > maxWidth) {
          overflowed = true;
          break;
        }
        i++;
        continue;
      }
      let end = i;
      while (end < text.length && text[end] !== "\t") {
        const nextAnsi = extractAnsiCode(text, end);
        if (nextAnsi) {
          break;
        }
        end++;
      }
      for (const { segment } of segmenter.segment(text.slice(i, end))) {
        const width = graphemeWidth(segment);
        if (keepContiguousPrefix && keptWidth + width <= targetWidth) {
          if (pendingAnsi) {
            result += pendingAnsi;
            pendingAnsi = "";
          }
          result += segment;
          keptWidth += width;
        } else {
          keepContiguousPrefix = false;
          pendingAnsi = "";
        }
        visibleSoFar += width;
        if (visibleSoFar > maxWidth) {
          overflowed = true;
          break;
        }
      }
      if (overflowed) {
        break;
      }
      i = end;
    }
    exhaustedInput = i >= text.length;
  }
  if (!overflowed && exhaustedInput) {
    return pad ? text + " ".repeat(Math.max(0, maxWidth - visibleSoFar)) : text;
  }
  return finalizeTruncatedResult(result, keptWidth, ellipsis, ellipsisWidth, maxWidth, pad);
}
function sliceByColumn(line, startCol, length, strict = false) {
  return sliceWithWidth(line, startCol, length, strict).text;
}
function sliceWithWidth(line, startCol, length, strict = false) {
  if (length <= 0)
    return { text: "", width: 0 };
  const endCol = startCol + length;
  let result = "", resultWidth = 0, currentCol = 0, i = 0, pendingAnsi = "";
  while (i < line.length) {
    const ansi = extractAnsiCode(line, i);
    if (ansi) {
      if (currentCol >= startCol && currentCol < endCol)
        result += ansi.code;
      else if (currentCol < startCol)
        pendingAnsi += ansi.code;
      i += ansi.length;
      continue;
    }
    let textEnd = i;
    while (textEnd < line.length && !extractAnsiCode(line, textEnd))
      textEnd++;
    for (const { segment } of segmenter.segment(line.slice(i, textEnd))) {
      const w = graphemeWidth(segment);
      const inRange = currentCol >= startCol && currentCol < endCol;
      const fits = !strict || currentCol + w <= endCol;
      if (inRange && fits) {
        if (pendingAnsi) {
          result += pendingAnsi;
          pendingAnsi = "";
        }
        result += segment;
        resultWidth += w;
      }
      currentCol += w;
      if (currentCol >= endCol)
        break;
    }
    i = textEnd;
    if (currentCol >= endCol)
      break;
  }
  return { text: result, width: resultWidth };
}
var pooledStyleTracker = new AnsiCodeTracker;
function extractSegments(line, beforeEnd, afterStart, afterLen, strictAfter = false) {
  let before = "", beforeWidth = 0, after = "", afterWidth = 0;
  let currentCol = 0, i = 0;
  let pendingAnsiBefore = "";
  let afterStarted = false;
  const afterEnd = afterStart + afterLen;
  pooledStyleTracker.clear();
  while (i < line.length) {
    const ansi = extractAnsiCode(line, i);
    if (ansi) {
      pooledStyleTracker.process(ansi.code);
      if (currentCol < beforeEnd) {
        pendingAnsiBefore += ansi.code;
      } else if (currentCol >= afterStart && currentCol < afterEnd && afterStarted) {
        after += ansi.code;
      }
      i += ansi.length;
      continue;
    }
    let textEnd = i;
    while (textEnd < line.length && !extractAnsiCode(line, textEnd))
      textEnd++;
    for (const { segment } of segmenter.segment(line.slice(i, textEnd))) {
      const w = graphemeWidth(segment);
      if (currentCol < beforeEnd) {
        if (pendingAnsiBefore) {
          before += pendingAnsiBefore;
          pendingAnsiBefore = "";
        }
        before += segment;
        beforeWidth += w;
      } else if (currentCol >= afterStart && currentCol < afterEnd) {
        const fits = !strictAfter || currentCol + w <= afterEnd;
        if (fits) {
          if (!afterStarted) {
            after += pooledStyleTracker.getActiveCodes();
            afterStarted = true;
          }
          after += segment;
          afterWidth += w;
        }
      }
      currentCol += w;
      if (afterLen <= 0 ? currentCol >= beforeEnd : currentCol >= afterEnd)
        break;
    }
    i = textEnd;
    if (afterLen <= 0 ? currentCol >= beforeEnd : currentCol >= afterEnd)
      break;
  }
  return { before, beforeWidth, after, afterWidth };
}
// node_modules/@mariozechner/pi-tui/dist/keys.js
var _kittyProtocolActive = false;
function setKittyProtocolActive(active) {
  _kittyProtocolActive = active;
}
var SYMBOL_KEYS = new Set([
  "`",
  "-",
  "=",
  "[",
  "]",
  "\\",
  ";",
  "'",
  ",",
  ".",
  "/",
  "!",
  "@",
  "#",
  "$",
  "%",
  "^",
  "&",
  "*",
  "(",
  ")",
  "_",
  "+",
  "|",
  "~",
  "{",
  "}",
  ":",
  "<",
  ">",
  "?"
]);
var MODIFIERS = {
  shift: 1,
  alt: 2,
  ctrl: 4
};
var LOCK_MASK = 64 + 128;
var CODEPOINTS = {
  escape: 27,
  tab: 9,
  enter: 13,
  space: 32,
  backspace: 127,
  kpEnter: 57414
};
var ARROW_CODEPOINTS = {
  up: -1,
  down: -2,
  right: -3,
  left: -4
};
var FUNCTIONAL_CODEPOINTS = {
  delete: -10,
  insert: -11,
  pageUp: -12,
  pageDown: -13,
  home: -14,
  end: -15
};
var KITTY_FUNCTIONAL_KEY_EQUIVALENTS = new Map([
  [57399, 48],
  [57400, 49],
  [57401, 50],
  [57402, 51],
  [57403, 52],
  [57404, 53],
  [57405, 54],
  [57406, 55],
  [57407, 56],
  [57408, 57],
  [57409, 46],
  [57410, 47],
  [57411, 42],
  [57412, 45],
  [57413, 43],
  [57415, 61],
  [57416, 44],
  [57417, ARROW_CODEPOINTS.left],
  [57418, ARROW_CODEPOINTS.right],
  [57419, ARROW_CODEPOINTS.up],
  [57420, ARROW_CODEPOINTS.down],
  [57421, FUNCTIONAL_CODEPOINTS.pageUp],
  [57422, FUNCTIONAL_CODEPOINTS.pageDown],
  [57423, FUNCTIONAL_CODEPOINTS.home],
  [57424, FUNCTIONAL_CODEPOINTS.end],
  [57425, FUNCTIONAL_CODEPOINTS.insert],
  [57426, FUNCTIONAL_CODEPOINTS.delete]
]);
function normalizeKittyFunctionalCodepoint(codepoint) {
  return KITTY_FUNCTIONAL_KEY_EQUIVALENTS.get(codepoint) ?? codepoint;
}
var LEGACY_KEY_SEQUENCES = {
  up: ["\x1B[A", "\x1BOA"],
  down: ["\x1B[B", "\x1BOB"],
  right: ["\x1B[C", "\x1BOC"],
  left: ["\x1B[D", "\x1BOD"],
  home: ["\x1B[H", "\x1BOH", "\x1B[1~", "\x1B[7~"],
  end: ["\x1B[F", "\x1BOF", "\x1B[4~", "\x1B[8~"],
  insert: ["\x1B[2~"],
  delete: ["\x1B[3~"],
  pageUp: ["\x1B[5~", "\x1B[[5~"],
  pageDown: ["\x1B[6~", "\x1B[[6~"],
  clear: ["\x1B[E", "\x1BOE"],
  f1: ["\x1BOP", "\x1B[11~", "\x1B[[A"],
  f2: ["\x1BOQ", "\x1B[12~", "\x1B[[B"],
  f3: ["\x1BOR", "\x1B[13~", "\x1B[[C"],
  f4: ["\x1BOS", "\x1B[14~", "\x1B[[D"],
  f5: ["\x1B[15~", "\x1B[[E"],
  f6: ["\x1B[17~"],
  f7: ["\x1B[18~"],
  f8: ["\x1B[19~"],
  f9: ["\x1B[20~"],
  f10: ["\x1B[21~"],
  f11: ["\x1B[23~"],
  f12: ["\x1B[24~"]
};
var LEGACY_SHIFT_SEQUENCES = {
  up: ["\x1B[a"],
  down: ["\x1B[b"],
  right: ["\x1B[c"],
  left: ["\x1B[d"],
  clear: ["\x1B[e"],
  insert: ["\x1B[2$"],
  delete: ["\x1B[3$"],
  pageUp: ["\x1B[5$"],
  pageDown: ["\x1B[6$"],
  home: ["\x1B[7$"],
  end: ["\x1B[8$"]
};
var LEGACY_CTRL_SEQUENCES = {
  up: ["\x1BOa"],
  down: ["\x1BOb"],
  right: ["\x1BOc"],
  left: ["\x1BOd"],
  clear: ["\x1BOe"],
  insert: ["\x1B[2^"],
  delete: ["\x1B[3^"],
  pageUp: ["\x1B[5^"],
  pageDown: ["\x1B[6^"],
  home: ["\x1B[7^"],
  end: ["\x1B[8^"]
};
var matchesLegacySequence = (data, sequences) => sequences.includes(data);
var matchesLegacyModifierSequence = (data, key, modifier) => {
  if (modifier === MODIFIERS.shift) {
    return matchesLegacySequence(data, LEGACY_SHIFT_SEQUENCES[key]);
  }
  if (modifier === MODIFIERS.ctrl) {
    return matchesLegacySequence(data, LEGACY_CTRL_SEQUENCES[key]);
  }
  return false;
};
var _lastEventType = "press";
function isKeyRelease(data) {
  if (data.includes("\x1B[200~")) {
    return false;
  }
  if (data.includes(":3u") || data.includes(":3~") || data.includes(":3A") || data.includes(":3B") || data.includes(":3C") || data.includes(":3D") || data.includes(":3H") || data.includes(":3F")) {
    return true;
  }
  return false;
}
function parseEventType(eventTypeStr) {
  if (!eventTypeStr)
    return "press";
  const eventType = parseInt(eventTypeStr, 10);
  if (eventType === 2)
    return "repeat";
  if (eventType === 3)
    return "release";
  return "press";
}
function parseKittySequence(data) {
  const csiUMatch = data.match(/^\x1b\[(\d+)(?::(\d*))?(?::(\d+))?(?:;(\d+))?(?::(\d+))?u$/);
  if (csiUMatch) {
    const codepoint = parseInt(csiUMatch[1], 10);
    const shiftedKey = csiUMatch[2] && csiUMatch[2].length > 0 ? parseInt(csiUMatch[2], 10) : undefined;
    const baseLayoutKey = csiUMatch[3] ? parseInt(csiUMatch[3], 10) : undefined;
    const modValue = csiUMatch[4] ? parseInt(csiUMatch[4], 10) : 1;
    const eventType = parseEventType(csiUMatch[5]);
    _lastEventType = eventType;
    return { codepoint, shiftedKey, baseLayoutKey, modifier: modValue - 1, eventType };
  }
  const arrowMatch = data.match(/^\x1b\[1;(\d+)(?::(\d+))?([ABCD])$/);
  if (arrowMatch) {
    const modValue = parseInt(arrowMatch[1], 10);
    const eventType = parseEventType(arrowMatch[2]);
    const arrowCodes = { A: -1, B: -2, C: -3, D: -4 };
    _lastEventType = eventType;
    return { codepoint: arrowCodes[arrowMatch[3]], modifier: modValue - 1, eventType };
  }
  const funcMatch = data.match(/^\x1b\[(\d+)(?:;(\d+))?(?::(\d+))?~$/);
  if (funcMatch) {
    const keyNum = parseInt(funcMatch[1], 10);
    const modValue = funcMatch[2] ? parseInt(funcMatch[2], 10) : 1;
    const eventType = parseEventType(funcMatch[3]);
    const funcCodes = {
      2: FUNCTIONAL_CODEPOINTS.insert,
      3: FUNCTIONAL_CODEPOINTS.delete,
      5: FUNCTIONAL_CODEPOINTS.pageUp,
      6: FUNCTIONAL_CODEPOINTS.pageDown,
      7: FUNCTIONAL_CODEPOINTS.home,
      8: FUNCTIONAL_CODEPOINTS.end
    };
    const codepoint = funcCodes[keyNum];
    if (codepoint !== undefined) {
      _lastEventType = eventType;
      return { codepoint, modifier: modValue - 1, eventType };
    }
  }
  const homeEndMatch = data.match(/^\x1b\[1;(\d+)(?::(\d+))?([HF])$/);
  if (homeEndMatch) {
    const modValue = parseInt(homeEndMatch[1], 10);
    const eventType = parseEventType(homeEndMatch[2]);
    const codepoint = homeEndMatch[3] === "H" ? FUNCTIONAL_CODEPOINTS.home : FUNCTIONAL_CODEPOINTS.end;
    _lastEventType = eventType;
    return { codepoint, modifier: modValue - 1, eventType };
  }
  return null;
}
function matchesKittySequence(data, expectedCodepoint, expectedModifier) {
  const parsed = parseKittySequence(data);
  if (!parsed)
    return false;
  const actualMod = parsed.modifier & ~LOCK_MASK;
  const expectedMod = expectedModifier & ~LOCK_MASK;
  if (actualMod !== expectedMod)
    return false;
  const normalizedCodepoint = normalizeKittyFunctionalCodepoint(parsed.codepoint);
  const normalizedExpectedCodepoint = normalizeKittyFunctionalCodepoint(expectedCodepoint);
  if (normalizedCodepoint === normalizedExpectedCodepoint)
    return true;
  if (parsed.baseLayoutKey !== undefined && parsed.baseLayoutKey === expectedCodepoint) {
    const cp = normalizedCodepoint;
    const isLatinLetter = cp >= 97 && cp <= 122;
    const isKnownSymbol = SYMBOL_KEYS.has(String.fromCharCode(cp));
    if (!isLatinLetter && !isKnownSymbol)
      return true;
  }
  return false;
}
function parseModifyOtherKeysSequence(data) {
  const match = data.match(/^\x1b\[27;(\d+);(\d+)~$/);
  if (!match)
    return null;
  const modValue = parseInt(match[1], 10);
  const codepoint = parseInt(match[2], 10);
  return { codepoint, modifier: modValue - 1 };
}
function matchesModifyOtherKeys(data, expectedKeycode, expectedModifier) {
  const parsed = parseModifyOtherKeysSequence(data);
  if (!parsed)
    return false;
  return parsed.codepoint === expectedKeycode && parsed.modifier === expectedModifier;
}
function isWindowsTerminalSession() {
  return Boolean(process.env.WT_SESSION) && !process.env.SSH_CONNECTION && !process.env.SSH_CLIENT && !process.env.SSH_TTY;
}
function matchesRawBackspace(data, expectedModifier) {
  if (data === "\x7F")
    return expectedModifier === 0;
  if (data !== "\b")
    return false;
  return isWindowsTerminalSession() ? expectedModifier === MODIFIERS.ctrl : expectedModifier === 0;
}
function rawCtrlChar(key) {
  const char = key.toLowerCase();
  const code = char.charCodeAt(0);
  if (code >= 97 && code <= 122 || char === "[" || char === "\\" || char === "]" || char === "_") {
    return String.fromCharCode(code & 31);
  }
  if (char === "-") {
    return String.fromCharCode(31);
  }
  return null;
}
function isDigitKey(key) {
  return key >= "0" && key <= "9";
}
function matchesPrintableModifyOtherKeys(data, expectedKeycode, expectedModifier) {
  if (expectedModifier === 0)
    return false;
  return matchesModifyOtherKeys(data, expectedKeycode, expectedModifier);
}
function parseKeyId(keyId) {
  const parts = keyId.toLowerCase().split("+");
  const key = parts[parts.length - 1];
  if (!key)
    return null;
  return {
    key,
    ctrl: parts.includes("ctrl"),
    shift: parts.includes("shift"),
    alt: parts.includes("alt")
  };
}
function matchesKey(data, keyId) {
  const parsed = parseKeyId(keyId);
  if (!parsed)
    return false;
  const { key, ctrl, shift, alt } = parsed;
  let modifier = 0;
  if (shift)
    modifier |= MODIFIERS.shift;
  if (alt)
    modifier |= MODIFIERS.alt;
  if (ctrl)
    modifier |= MODIFIERS.ctrl;
  switch (key) {
    case "escape":
    case "esc":
      if (modifier !== 0)
        return false;
      return data === "\x1B" || matchesKittySequence(data, CODEPOINTS.escape, 0) || matchesModifyOtherKeys(data, CODEPOINTS.escape, 0);
    case "space":
      if (!_kittyProtocolActive) {
        if (ctrl && !alt && !shift && data === "\x00") {
          return true;
        }
        if (alt && !ctrl && !shift && data === "\x1B ") {
          return true;
        }
      }
      if (modifier === 0) {
        return data === " " || matchesKittySequence(data, CODEPOINTS.space, 0) || matchesModifyOtherKeys(data, CODEPOINTS.space, 0);
      }
      return matchesKittySequence(data, CODEPOINTS.space, modifier) || matchesModifyOtherKeys(data, CODEPOINTS.space, modifier);
    case "tab":
      if (shift && !ctrl && !alt) {
        return data === "\x1B[Z" || matchesKittySequence(data, CODEPOINTS.tab, MODIFIERS.shift) || matchesModifyOtherKeys(data, CODEPOINTS.tab, MODIFIERS.shift);
      }
      if (modifier === 0) {
        return data === "\t" || matchesKittySequence(data, CODEPOINTS.tab, 0);
      }
      return matchesKittySequence(data, CODEPOINTS.tab, modifier) || matchesModifyOtherKeys(data, CODEPOINTS.tab, modifier);
    case "enter":
    case "return":
      if (shift && !ctrl && !alt) {
        if (matchesKittySequence(data, CODEPOINTS.enter, MODIFIERS.shift) || matchesKittySequence(data, CODEPOINTS.kpEnter, MODIFIERS.shift)) {
          return true;
        }
        if (matchesModifyOtherKeys(data, CODEPOINTS.enter, MODIFIERS.shift)) {
          return true;
        }
        if (_kittyProtocolActive) {
          return data === "\x1B\r" || data === `
`;
        }
        return false;
      }
      if (alt && !ctrl && !shift) {
        if (matchesKittySequence(data, CODEPOINTS.enter, MODIFIERS.alt) || matchesKittySequence(data, CODEPOINTS.kpEnter, MODIFIERS.alt)) {
          return true;
        }
        if (matchesModifyOtherKeys(data, CODEPOINTS.enter, MODIFIERS.alt)) {
          return true;
        }
        if (!_kittyProtocolActive) {
          return data === "\x1B\r";
        }
        return false;
      }
      if (modifier === 0) {
        return data === "\r" || !_kittyProtocolActive && data === `
` || data === "\x1BOM" || matchesKittySequence(data, CODEPOINTS.enter, 0) || matchesKittySequence(data, CODEPOINTS.kpEnter, 0);
      }
      return matchesKittySequence(data, CODEPOINTS.enter, modifier) || matchesKittySequence(data, CODEPOINTS.kpEnter, modifier) || matchesModifyOtherKeys(data, CODEPOINTS.enter, modifier);
    case "backspace":
      if (alt && !ctrl && !shift) {
        if (data === "\x1B\x7F" || data === "\x1B\b") {
          return true;
        }
        return matchesKittySequence(data, CODEPOINTS.backspace, MODIFIERS.alt) || matchesModifyOtherKeys(data, CODEPOINTS.backspace, MODIFIERS.alt);
      }
      if (ctrl && !alt && !shift) {
        if (matchesRawBackspace(data, MODIFIERS.ctrl))
          return true;
        return matchesKittySequence(data, CODEPOINTS.backspace, MODIFIERS.ctrl) || matchesModifyOtherKeys(data, CODEPOINTS.backspace, MODIFIERS.ctrl);
      }
      if (modifier === 0) {
        return matchesRawBackspace(data, 0) || matchesKittySequence(data, CODEPOINTS.backspace, 0) || matchesModifyOtherKeys(data, CODEPOINTS.backspace, 0);
      }
      return matchesKittySequence(data, CODEPOINTS.backspace, modifier) || matchesModifyOtherKeys(data, CODEPOINTS.backspace, modifier);
    case "insert":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.insert) || matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.insert, 0);
      }
      if (matchesLegacyModifierSequence(data, "insert", modifier)) {
        return true;
      }
      return matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.insert, modifier);
    case "delete":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.delete) || matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.delete, 0);
      }
      if (matchesLegacyModifierSequence(data, "delete", modifier)) {
        return true;
      }
      return matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.delete, modifier);
    case "clear":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.clear);
      }
      return matchesLegacyModifierSequence(data, "clear", modifier);
    case "home":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.home) || matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.home, 0);
      }
      if (matchesLegacyModifierSequence(data, "home", modifier)) {
        return true;
      }
      return matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.home, modifier);
    case "end":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.end) || matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.end, 0);
      }
      if (matchesLegacyModifierSequence(data, "end", modifier)) {
        return true;
      }
      return matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.end, modifier);
    case "pageup":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.pageUp) || matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.pageUp, 0);
      }
      if (matchesLegacyModifierSequence(data, "pageUp", modifier)) {
        return true;
      }
      return matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.pageUp, modifier);
    case "pagedown":
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.pageDown) || matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.pageDown, 0);
      }
      if (matchesLegacyModifierSequence(data, "pageDown", modifier)) {
        return true;
      }
      return matchesKittySequence(data, FUNCTIONAL_CODEPOINTS.pageDown, modifier);
    case "up":
      if (alt && !ctrl && !shift) {
        return data === "\x1Bp" || matchesKittySequence(data, ARROW_CODEPOINTS.up, MODIFIERS.alt);
      }
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.up) || matchesKittySequence(data, ARROW_CODEPOINTS.up, 0);
      }
      if (matchesLegacyModifierSequence(data, "up", modifier)) {
        return true;
      }
      return matchesKittySequence(data, ARROW_CODEPOINTS.up, modifier);
    case "down":
      if (alt && !ctrl && !shift) {
        return data === "\x1Bn" || matchesKittySequence(data, ARROW_CODEPOINTS.down, MODIFIERS.alt);
      }
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.down) || matchesKittySequence(data, ARROW_CODEPOINTS.down, 0);
      }
      if (matchesLegacyModifierSequence(data, "down", modifier)) {
        return true;
      }
      return matchesKittySequence(data, ARROW_CODEPOINTS.down, modifier);
    case "left":
      if (alt && !ctrl && !shift) {
        return data === "\x1B[1;3D" || !_kittyProtocolActive && data === "\x1BB" || data === "\x1Bb" || matchesKittySequence(data, ARROW_CODEPOINTS.left, MODIFIERS.alt);
      }
      if (ctrl && !alt && !shift) {
        return data === "\x1B[1;5D" || matchesLegacyModifierSequence(data, "left", MODIFIERS.ctrl) || matchesKittySequence(data, ARROW_CODEPOINTS.left, MODIFIERS.ctrl);
      }
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.left) || matchesKittySequence(data, ARROW_CODEPOINTS.left, 0);
      }
      if (matchesLegacyModifierSequence(data, "left", modifier)) {
        return true;
      }
      return matchesKittySequence(data, ARROW_CODEPOINTS.left, modifier);
    case "right":
      if (alt && !ctrl && !shift) {
        return data === "\x1B[1;3C" || !_kittyProtocolActive && data === "\x1BF" || data === "\x1Bf" || matchesKittySequence(data, ARROW_CODEPOINTS.right, MODIFIERS.alt);
      }
      if (ctrl && !alt && !shift) {
        return data === "\x1B[1;5C" || matchesLegacyModifierSequence(data, "right", MODIFIERS.ctrl) || matchesKittySequence(data, ARROW_CODEPOINTS.right, MODIFIERS.ctrl);
      }
      if (modifier === 0) {
        return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES.right) || matchesKittySequence(data, ARROW_CODEPOINTS.right, 0);
      }
      if (matchesLegacyModifierSequence(data, "right", modifier)) {
        return true;
      }
      return matchesKittySequence(data, ARROW_CODEPOINTS.right, modifier);
    case "f1":
    case "f2":
    case "f3":
    case "f4":
    case "f5":
    case "f6":
    case "f7":
    case "f8":
    case "f9":
    case "f10":
    case "f11":
    case "f12": {
      if (modifier !== 0) {
        return false;
      }
      const functionKey = key;
      return matchesLegacySequence(data, LEGACY_KEY_SEQUENCES[functionKey]);
    }
  }
  if (key.length === 1 && (key >= "a" && key <= "z" || isDigitKey(key) || SYMBOL_KEYS.has(key))) {
    const codepoint = key.charCodeAt(0);
    const rawCtrl = rawCtrlChar(key);
    const isLetter = key >= "a" && key <= "z";
    const isDigit = isDigitKey(key);
    if (ctrl && alt && !shift && !_kittyProtocolActive && rawCtrl) {
      return data === `\x1B${rawCtrl}`;
    }
    if (alt && !ctrl && !shift && !_kittyProtocolActive && (isLetter || isDigit)) {
      if (data === `\x1B${key}`)
        return true;
    }
    if (ctrl && !shift && !alt) {
      if (rawCtrl && data === rawCtrl)
        return true;
      return matchesKittySequence(data, codepoint, MODIFIERS.ctrl) || matchesPrintableModifyOtherKeys(data, codepoint, MODIFIERS.ctrl);
    }
    if (ctrl && shift && !alt) {
      return matchesKittySequence(data, codepoint, MODIFIERS.shift + MODIFIERS.ctrl) || matchesPrintableModifyOtherKeys(data, codepoint, MODIFIERS.shift + MODIFIERS.ctrl);
    }
    if (shift && !ctrl && !alt) {
      if (isLetter && data === key.toUpperCase())
        return true;
      return matchesKittySequence(data, codepoint, MODIFIERS.shift) || matchesPrintableModifyOtherKeys(data, codepoint, MODIFIERS.shift);
    }
    if (modifier !== 0) {
      return matchesKittySequence(data, codepoint, modifier) || matchesPrintableModifyOtherKeys(data, codepoint, modifier);
    }
    return data === key || matchesKittySequence(data, codepoint, 0);
  }
  return false;
}
var KITTY_CSI_U_REGEX = /^\x1b\[(\d+)(?::(\d*))?(?::(\d+))?(?:;(\d+))?(?::(\d+))?u$/;
var KITTY_PRINTABLE_ALLOWED_MODIFIERS = MODIFIERS.shift | LOCK_MASK;
function decodeKittyPrintable(data) {
  const match = data.match(KITTY_CSI_U_REGEX);
  if (!match)
    return;
  const codepoint = Number.parseInt(match[1] ?? "", 10);
  if (!Number.isFinite(codepoint))
    return;
  const shiftedKey = match[2] && match[2].length > 0 ? Number.parseInt(match[2], 10) : undefined;
  const modValue = match[4] ? Number.parseInt(match[4], 10) : 1;
  const modifier = Number.isFinite(modValue) ? modValue - 1 : 0;
  if ((modifier & ~KITTY_PRINTABLE_ALLOWED_MODIFIERS) !== 0)
    return;
  if (modifier & (MODIFIERS.alt | MODIFIERS.ctrl))
    return;
  let effectiveCodepoint = codepoint;
  if (modifier & MODIFIERS.shift && typeof shiftedKey === "number") {
    effectiveCodepoint = shiftedKey;
  }
  effectiveCodepoint = normalizeKittyFunctionalCodepoint(effectiveCodepoint);
  if (!Number.isFinite(effectiveCodepoint) || effectiveCodepoint < 32)
    return;
  try {
    return String.fromCodePoint(effectiveCodepoint);
  } catch {
    return;
  }
}

// node_modules/@mariozechner/pi-tui/dist/keybindings.js
var TUI_KEYBINDINGS = {
  "tui.editor.cursorUp": { defaultKeys: "up", description: "Move cursor up" },
  "tui.editor.cursorDown": { defaultKeys: "down", description: "Move cursor down" },
  "tui.editor.cursorLeft": {
    defaultKeys: ["left", "ctrl+b"],
    description: "Move cursor left"
  },
  "tui.editor.cursorRight": {
    defaultKeys: ["right", "ctrl+f"],
    description: "Move cursor right"
  },
  "tui.editor.cursorWordLeft": {
    defaultKeys: ["alt+left", "ctrl+left", "alt+b"],
    description: "Move cursor word left"
  },
  "tui.editor.cursorWordRight": {
    defaultKeys: ["alt+right", "ctrl+right", "alt+f"],
    description: "Move cursor word right"
  },
  "tui.editor.cursorLineStart": {
    defaultKeys: ["home", "ctrl+a"],
    description: "Move to line start"
  },
  "tui.editor.cursorLineEnd": {
    defaultKeys: ["end", "ctrl+e"],
    description: "Move to line end"
  },
  "tui.editor.jumpForward": {
    defaultKeys: "ctrl+]",
    description: "Jump forward to character"
  },
  "tui.editor.jumpBackward": {
    defaultKeys: "ctrl+alt+]",
    description: "Jump backward to character"
  },
  "tui.editor.pageUp": { defaultKeys: "pageUp", description: "Page up" },
  "tui.editor.pageDown": { defaultKeys: "pageDown", description: "Page down" },
  "tui.editor.deleteCharBackward": {
    defaultKeys: "backspace",
    description: "Delete character backward"
  },
  "tui.editor.deleteCharForward": {
    defaultKeys: ["delete", "ctrl+d"],
    description: "Delete character forward"
  },
  "tui.editor.deleteWordBackward": {
    defaultKeys: ["ctrl+w", "alt+backspace"],
    description: "Delete word backward"
  },
  "tui.editor.deleteWordForward": {
    defaultKeys: ["alt+d", "alt+delete"],
    description: "Delete word forward"
  },
  "tui.editor.deleteToLineStart": {
    defaultKeys: "ctrl+u",
    description: "Delete to line start"
  },
  "tui.editor.deleteToLineEnd": {
    defaultKeys: "ctrl+k",
    description: "Delete to line end"
  },
  "tui.editor.yank": { defaultKeys: "ctrl+y", description: "Yank" },
  "tui.editor.yankPop": { defaultKeys: "alt+y", description: "Yank pop" },
  "tui.editor.undo": { defaultKeys: "ctrl+-", description: "Undo" },
  "tui.input.newLine": { defaultKeys: "shift+enter", description: "Insert newline" },
  "tui.input.submit": { defaultKeys: "enter", description: "Submit input" },
  "tui.input.tab": { defaultKeys: "tab", description: "Tab / autocomplete" },
  "tui.input.copy": { defaultKeys: "ctrl+c", description: "Copy selection" },
  "tui.select.up": { defaultKeys: "up", description: "Move selection up" },
  "tui.select.down": { defaultKeys: "down", description: "Move selection down" },
  "tui.select.pageUp": { defaultKeys: "pageUp", description: "Selection page up" },
  "tui.select.pageDown": {
    defaultKeys: "pageDown",
    description: "Selection page down"
  },
  "tui.select.confirm": { defaultKeys: "enter", description: "Confirm selection" },
  "tui.select.cancel": {
    defaultKeys: ["escape", "ctrl+c"],
    description: "Cancel selection"
  }
};
function normalizeKeys(keys) {
  if (keys === undefined)
    return [];
  const keyList = Array.isArray(keys) ? keys : [keys];
  const seen = new Set;
  const result = [];
  for (const key of keyList) {
    if (!seen.has(key)) {
      seen.add(key);
      result.push(key);
    }
  }
  return result;
}

class KeybindingsManager {
  definitions;
  userBindings;
  keysById = new Map;
  conflicts = [];
  constructor(definitions, userBindings = {}) {
    this.definitions = definitions;
    this.userBindings = userBindings;
    this.rebuild();
  }
  rebuild() {
    this.keysById.clear();
    this.conflicts = [];
    const userClaims = new Map;
    for (const [keybinding, keys] of Object.entries(this.userBindings)) {
      if (!(keybinding in this.definitions))
        continue;
      for (const key of normalizeKeys(keys)) {
        const claimants = userClaims.get(key) ?? new Set;
        claimants.add(keybinding);
        userClaims.set(key, claimants);
      }
    }
    for (const [key, keybindings] of userClaims) {
      if (keybindings.size > 1) {
        this.conflicts.push({ key, keybindings: [...keybindings] });
      }
    }
    for (const [id, definition] of Object.entries(this.definitions)) {
      const userKeys = this.userBindings[id];
      const keys = userKeys === undefined ? normalizeKeys(definition.defaultKeys) : normalizeKeys(userKeys);
      this.keysById.set(id, keys);
    }
  }
  matches(data, keybinding) {
    const keys = this.keysById.get(keybinding) ?? [];
    for (const key of keys) {
      if (matchesKey(data, key))
        return true;
    }
    return false;
  }
  getKeys(keybinding) {
    return [...this.keysById.get(keybinding) ?? []];
  }
  getDefinition(keybinding) {
    return this.definitions[keybinding];
  }
  getConflicts() {
    return this.conflicts.map((conflict) => ({ ...conflict, keybindings: [...conflict.keybindings] }));
  }
  setUserBindings(userBindings) {
    this.userBindings = userBindings;
    this.rebuild();
  }
  getUserBindings() {
    return { ...this.userBindings };
  }
  getResolvedBindings() {
    const resolved = {};
    for (const id of Object.keys(this.definitions)) {
      const keys = this.keysById.get(id) ?? [];
      resolved[id] = keys.length === 1 ? keys[0] : [...keys];
    }
    return resolved;
  }
}
var globalKeybindings = null;
function getKeybindings() {
  if (!globalKeybindings) {
    globalKeybindings = new KeybindingsManager(TUI_KEYBINDINGS);
  }
  return globalKeybindings;
}

// node_modules/@mariozechner/pi-tui/dist/components/text.js
class Text {
  text;
  paddingX;
  paddingY;
  customBgFn;
  cachedText;
  cachedWidth;
  cachedLines;
  constructor(text = "", paddingX = 1, paddingY = 1, customBgFn) {
    this.text = text;
    this.paddingX = paddingX;
    this.paddingY = paddingY;
    this.customBgFn = customBgFn;
  }
  setText(text) {
    this.text = text;
    this.cachedText = undefined;
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }
  setCustomBgFn(customBgFn) {
    this.customBgFn = customBgFn;
    this.cachedText = undefined;
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }
  invalidate() {
    this.cachedText = undefined;
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }
  render(width) {
    if (this.cachedLines && this.cachedText === this.text && this.cachedWidth === width) {
      return this.cachedLines;
    }
    if (!this.text || this.text.trim() === "") {
      const result2 = [];
      this.cachedText = this.text;
      this.cachedWidth = width;
      this.cachedLines = result2;
      return result2;
    }
    const normalizedText = this.text.replace(/\t/g, "   ");
    const contentWidth = Math.max(1, width - this.paddingX * 2);
    const wrappedLines = wrapTextWithAnsi(normalizedText, contentWidth);
    const leftMargin = " ".repeat(this.paddingX);
    const rightMargin = " ".repeat(this.paddingX);
    const contentLines = [];
    for (const line of wrappedLines) {
      const lineWithMargins = leftMargin + line + rightMargin;
      if (this.customBgFn) {
        contentLines.push(applyBackgroundToLine(lineWithMargins, width, this.customBgFn));
      } else {
        const visibleLen = visibleWidth(lineWithMargins);
        const paddingNeeded = Math.max(0, width - visibleLen);
        contentLines.push(lineWithMargins + " ".repeat(paddingNeeded));
      }
    }
    const emptyLine = " ".repeat(width);
    const emptyLines = [];
    for (let i = 0;i < this.paddingY; i++) {
      const line = this.customBgFn ? applyBackgroundToLine(emptyLine, width, this.customBgFn) : emptyLine;
      emptyLines.push(line);
    }
    const result = [...emptyLines, ...contentLines, ...emptyLines];
    this.cachedText = this.text;
    this.cachedWidth = width;
    this.cachedLines = result;
    return result.length > 0 ? result : [""];
  }
}

// node_modules/@mariozechner/pi-tui/dist/components/loader.js
class Loader extends Text {
  spinnerColorFn;
  messageColorFn;
  message;
  frames = ["\u280B", "\u2819", "\u2839", "\u2838", "\u283C", "\u2834", "\u2826", "\u2827", "\u2807", "\u280F"];
  currentFrame = 0;
  intervalId = null;
  ui = null;
  constructor(ui, spinnerColorFn, messageColorFn, message = "Loading...") {
    super("", 1, 0);
    this.spinnerColorFn = spinnerColorFn;
    this.messageColorFn = messageColorFn;
    this.message = message;
    this.ui = ui;
    this.start();
  }
  render(width) {
    return ["", ...super.render(width)];
  }
  start() {
    this.updateDisplay();
    this.intervalId = setInterval(() => {
      this.currentFrame = (this.currentFrame + 1) % this.frames.length;
      this.updateDisplay();
    }, 80);
  }
  stop() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }
  setMessage(message) {
    this.message = message;
    this.updateDisplay();
  }
  updateDisplay() {
    const frame = this.frames[this.currentFrame];
    this.setText(`${this.spinnerColorFn(frame)} ${this.messageColorFn(this.message)}`);
    if (this.ui) {
      this.ui.requestRender();
    }
  }
}

// node_modules/@mariozechner/pi-tui/dist/components/cancellable-loader.js
class CancellableLoader extends Loader {
  abortController = new AbortController;
  onAbort;
  get signal() {
    return this.abortController.signal;
  }
  get aborted() {
    return this.abortController.signal.aborted;
  }
  handleInput(data) {
    const kb = getKeybindings();
    if (kb.matches(data, "tui.select.cancel")) {
      this.abortController.abort();
      this.onAbort?.();
    }
  }
  dispose() {
    this.stop();
  }
}
// node_modules/@mariozechner/pi-tui/dist/kill-ring.js
class KillRing {
  ring = [];
  push(text, opts) {
    if (!text)
      return;
    if (opts.accumulate && this.ring.length > 0) {
      const last = this.ring.pop();
      this.ring.push(opts.prepend ? text + last : last + text);
    } else {
      this.ring.push(text);
    }
  }
  peek() {
    return this.ring.length > 0 ? this.ring[this.ring.length - 1] : undefined;
  }
  rotate() {
    if (this.ring.length > 1) {
      const last = this.ring.pop();
      this.ring.unshift(last);
    }
  }
  get length() {
    return this.ring.length;
  }
}

// node_modules/@mariozechner/pi-tui/dist/tui.js
import * as fs from "fs";
import * as os from "os";
import * as path from "path";

// node_modules/@mariozechner/pi-tui/dist/terminal-image.js
var cachedCapabilities = null;
var cellDimensions = { widthPx: 9, heightPx: 18 };
function setCellDimensions(dims) {
  cellDimensions = dims;
}
function detectCapabilities() {
  const termProgram = process.env.TERM_PROGRAM?.toLowerCase() || "";
  const term = process.env.TERM?.toLowerCase() || "";
  const colorTerm = process.env.COLORTERM?.toLowerCase() || "";
  if (process.env.KITTY_WINDOW_ID || termProgram === "kitty") {
    return { images: "kitty", trueColor: true, hyperlinks: true };
  }
  if (termProgram === "ghostty" || term.includes("ghostty") || process.env.GHOSTTY_RESOURCES_DIR) {
    return { images: "kitty", trueColor: true, hyperlinks: true };
  }
  if (process.env.WEZTERM_PANE || termProgram === "wezterm") {
    return { images: "kitty", trueColor: true, hyperlinks: true };
  }
  if (process.env.ITERM_SESSION_ID || termProgram === "iterm.app") {
    return { images: "iterm2", trueColor: true, hyperlinks: true };
  }
  if (termProgram === "vscode") {
    return { images: null, trueColor: true, hyperlinks: true };
  }
  if (termProgram === "alacritty") {
    return { images: null, trueColor: true, hyperlinks: true };
  }
  const trueColor = colorTerm === "truecolor" || colorTerm === "24bit";
  return { images: null, trueColor, hyperlinks: true };
}
function getCapabilities() {
  if (!cachedCapabilities) {
    cachedCapabilities = detectCapabilities();
  }
  return cachedCapabilities;
}
var KITTY_PREFIX = "\x1B_G";
var ITERM2_PREFIX = "\x1B]1337;File=";
function isImageLine(line) {
  if (line.startsWith(KITTY_PREFIX) || line.startsWith(ITERM2_PREFIX)) {
    return true;
  }
  return line.includes(KITTY_PREFIX) || line.includes(ITERM2_PREFIX);
}

// node_modules/@mariozechner/pi-tui/dist/tui.js
function isFocusable(component) {
  return component !== null && "focused" in component;
}
var CURSOR_MARKER = "\x1B_pi:c\x07";
function parseSizeValue(value, referenceSize) {
  if (value === undefined)
    return;
  if (typeof value === "number")
    return value;
  const match = value.match(/^(\d+(?:\.\d+)?)%$/);
  if (match) {
    return Math.floor(referenceSize * parseFloat(match[1]) / 100);
  }
  return;
}
function isTermuxSession() {
  return Boolean(process.env.TERMUX_VERSION);
}

class Container {
  children = [];
  addChild(component) {
    this.children.push(component);
  }
  removeChild(component) {
    const index = this.children.indexOf(component);
    if (index !== -1) {
      this.children.splice(index, 1);
    }
  }
  clear() {
    this.children = [];
  }
  invalidate() {
    for (const child of this.children) {
      child.invalidate?.();
    }
  }
  render(width) {
    const lines = [];
    for (const child of this.children) {
      lines.push(...child.render(width));
    }
    return lines;
  }
}

class TUI extends Container {
  terminal;
  previousLines = [];
  previousWidth = 0;
  previousHeight = 0;
  focusedComponent = null;
  inputListeners = new Set;
  onDebug;
  renderRequested = false;
  cursorRow = 0;
  hardwareCursorRow = 0;
  showHardwareCursor = process.env.PI_HARDWARE_CURSOR === "1";
  clearOnShrink = process.env.PI_CLEAR_ON_SHRINK === "1";
  maxLinesRendered = 0;
  previousViewportTop = 0;
  fullRedrawCount = 0;
  stopped = false;
  focusOrderCounter = 0;
  overlayStack = [];
  constructor(terminal, showHardwareCursor) {
    super();
    this.terminal = terminal;
    if (showHardwareCursor !== undefined) {
      this.showHardwareCursor = showHardwareCursor;
    }
  }
  get fullRedraws() {
    return this.fullRedrawCount;
  }
  getShowHardwareCursor() {
    return this.showHardwareCursor;
  }
  setShowHardwareCursor(enabled) {
    if (this.showHardwareCursor === enabled)
      return;
    this.showHardwareCursor = enabled;
    if (!enabled) {
      this.terminal.hideCursor();
    }
    this.requestRender();
  }
  getClearOnShrink() {
    return this.clearOnShrink;
  }
  setClearOnShrink(enabled) {
    this.clearOnShrink = enabled;
  }
  setFocus(component) {
    if (isFocusable(this.focusedComponent)) {
      this.focusedComponent.focused = false;
    }
    this.focusedComponent = component;
    if (isFocusable(component)) {
      component.focused = true;
    }
  }
  showOverlay(component, options) {
    const entry = {
      component,
      options,
      preFocus: this.focusedComponent,
      hidden: false,
      focusOrder: ++this.focusOrderCounter
    };
    this.overlayStack.push(entry);
    if (!options?.nonCapturing && this.isOverlayVisible(entry)) {
      this.setFocus(component);
    }
    this.terminal.hideCursor();
    this.requestRender();
    return {
      hide: () => {
        const index = this.overlayStack.indexOf(entry);
        if (index !== -1) {
          this.overlayStack.splice(index, 1);
          if (this.focusedComponent === component) {
            const topVisible = this.getTopmostVisibleOverlay();
            this.setFocus(topVisible?.component ?? entry.preFocus);
          }
          if (this.overlayStack.length === 0)
            this.terminal.hideCursor();
          this.requestRender();
        }
      },
      setHidden: (hidden) => {
        if (entry.hidden === hidden)
          return;
        entry.hidden = hidden;
        if (hidden) {
          if (this.focusedComponent === component) {
            const topVisible = this.getTopmostVisibleOverlay();
            this.setFocus(topVisible?.component ?? entry.preFocus);
          }
        } else {
          if (!options?.nonCapturing && this.isOverlayVisible(entry)) {
            entry.focusOrder = ++this.focusOrderCounter;
            this.setFocus(component);
          }
        }
        this.requestRender();
      },
      isHidden: () => entry.hidden,
      focus: () => {
        if (!this.overlayStack.includes(entry) || !this.isOverlayVisible(entry))
          return;
        if (this.focusedComponent !== component) {
          this.setFocus(component);
        }
        entry.focusOrder = ++this.focusOrderCounter;
        this.requestRender();
      },
      unfocus: () => {
        if (this.focusedComponent !== component)
          return;
        const topVisible = this.getTopmostVisibleOverlay();
        this.setFocus(topVisible && topVisible !== entry ? topVisible.component : entry.preFocus);
        this.requestRender();
      },
      isFocused: () => this.focusedComponent === component
    };
  }
  hideOverlay() {
    const overlay = this.overlayStack.pop();
    if (!overlay)
      return;
    if (this.focusedComponent === overlay.component) {
      const topVisible = this.getTopmostVisibleOverlay();
      this.setFocus(topVisible?.component ?? overlay.preFocus);
    }
    if (this.overlayStack.length === 0)
      this.terminal.hideCursor();
    this.requestRender();
  }
  hasOverlay() {
    return this.overlayStack.some((o) => this.isOverlayVisible(o));
  }
  isOverlayVisible(entry) {
    if (entry.hidden)
      return false;
    if (entry.options?.visible) {
      return entry.options.visible(this.terminal.columns, this.terminal.rows);
    }
    return true;
  }
  getTopmostVisibleOverlay() {
    for (let i = this.overlayStack.length - 1;i >= 0; i--) {
      if (this.overlayStack[i].options?.nonCapturing)
        continue;
      if (this.isOverlayVisible(this.overlayStack[i])) {
        return this.overlayStack[i];
      }
    }
    return;
  }
  invalidate() {
    super.invalidate();
    for (const overlay of this.overlayStack)
      overlay.component.invalidate?.();
  }
  start() {
    this.stopped = false;
    this.terminal.start((data) => this.handleInput(data), () => this.requestRender());
    this.terminal.hideCursor();
    this.queryCellSize();
    this.requestRender();
  }
  addInputListener(listener) {
    this.inputListeners.add(listener);
    return () => {
      this.inputListeners.delete(listener);
    };
  }
  removeInputListener(listener) {
    this.inputListeners.delete(listener);
  }
  queryCellSize() {
    if (!getCapabilities().images) {
      return;
    }
    this.terminal.write("\x1B[16t");
  }
  stop() {
    this.stopped = true;
    if (this.previousLines.length > 0) {
      const targetRow = this.previousLines.length;
      const lineDiff = targetRow - this.hardwareCursorRow;
      if (lineDiff > 0) {
        this.terminal.write(`\x1B[${lineDiff}B`);
      } else if (lineDiff < 0) {
        this.terminal.write(`\x1B[${-lineDiff}A`);
      }
      this.terminal.write(`\r
`);
    }
    this.terminal.showCursor();
    this.terminal.stop();
  }
  requestRender(force = false) {
    if (force) {
      this.previousLines = [];
      this.previousWidth = -1;
      this.previousHeight = -1;
      this.cursorRow = 0;
      this.hardwareCursorRow = 0;
      this.maxLinesRendered = 0;
      this.previousViewportTop = 0;
    }
    if (this.renderRequested)
      return;
    this.renderRequested = true;
    process.nextTick(() => {
      this.renderRequested = false;
      this.doRender();
    });
  }
  handleInput(data) {
    if (this.inputListeners.size > 0) {
      let current = data;
      for (const listener of this.inputListeners) {
        const result = listener(current);
        if (result?.consume) {
          return;
        }
        if (result?.data !== undefined) {
          current = result.data;
        }
      }
      if (current.length === 0) {
        return;
      }
      data = current;
    }
    if (this.consumeCellSizeResponse(data)) {
      return;
    }
    if (matchesKey(data, "shift+ctrl+d") && this.onDebug) {
      this.onDebug();
      return;
    }
    const focusedOverlay = this.overlayStack.find((o) => o.component === this.focusedComponent);
    if (focusedOverlay && !this.isOverlayVisible(focusedOverlay)) {
      const topVisible = this.getTopmostVisibleOverlay();
      if (topVisible) {
        this.setFocus(topVisible.component);
      } else {
        this.setFocus(focusedOverlay.preFocus);
      }
    }
    if (this.focusedComponent?.handleInput) {
      if (isKeyRelease(data) && !this.focusedComponent.wantsKeyRelease) {
        return;
      }
      this.focusedComponent.handleInput(data);
      this.requestRender();
    }
  }
  consumeCellSizeResponse(data) {
    const match = data.match(/^\x1b\[6;(\d+);(\d+)t$/);
    if (!match) {
      return false;
    }
    const heightPx = parseInt(match[1], 10);
    const widthPx = parseInt(match[2], 10);
    if (heightPx <= 0 || widthPx <= 0) {
      return true;
    }
    setCellDimensions({ widthPx, heightPx });
    this.invalidate();
    this.requestRender();
    return true;
  }
  resolveOverlayLayout(options, overlayHeight, termWidth, termHeight) {
    const opt = options ?? {};
    const margin = typeof opt.margin === "number" ? { top: opt.margin, right: opt.margin, bottom: opt.margin, left: opt.margin } : opt.margin ?? {};
    const marginTop = Math.max(0, margin.top ?? 0);
    const marginRight = Math.max(0, margin.right ?? 0);
    const marginBottom = Math.max(0, margin.bottom ?? 0);
    const marginLeft = Math.max(0, margin.left ?? 0);
    const availWidth = Math.max(1, termWidth - marginLeft - marginRight);
    const availHeight = Math.max(1, termHeight - marginTop - marginBottom);
    let width = parseSizeValue(opt.width, termWidth) ?? Math.min(80, availWidth);
    if (opt.minWidth !== undefined) {
      width = Math.max(width, opt.minWidth);
    }
    width = Math.max(1, Math.min(width, availWidth));
    let maxHeight = parseSizeValue(opt.maxHeight, termHeight);
    if (maxHeight !== undefined) {
      maxHeight = Math.max(1, Math.min(maxHeight, availHeight));
    }
    const effectiveHeight = maxHeight !== undefined ? Math.min(overlayHeight, maxHeight) : overlayHeight;
    let row;
    let col;
    if (opt.row !== undefined) {
      if (typeof opt.row === "string") {
        const match = opt.row.match(/^(\d+(?:\.\d+)?)%$/);
        if (match) {
          const maxRow = Math.max(0, availHeight - effectiveHeight);
          const percent = parseFloat(match[1]) / 100;
          row = marginTop + Math.floor(maxRow * percent);
        } else {
          row = this.resolveAnchorRow("center", effectiveHeight, availHeight, marginTop);
        }
      } else {
        row = opt.row;
      }
    } else {
      const anchor = opt.anchor ?? "center";
      row = this.resolveAnchorRow(anchor, effectiveHeight, availHeight, marginTop);
    }
    if (opt.col !== undefined) {
      if (typeof opt.col === "string") {
        const match = opt.col.match(/^(\d+(?:\.\d+)?)%$/);
        if (match) {
          const maxCol = Math.max(0, availWidth - width);
          const percent = parseFloat(match[1]) / 100;
          col = marginLeft + Math.floor(maxCol * percent);
        } else {
          col = this.resolveAnchorCol("center", width, availWidth, marginLeft);
        }
      } else {
        col = opt.col;
      }
    } else {
      const anchor = opt.anchor ?? "center";
      col = this.resolveAnchorCol(anchor, width, availWidth, marginLeft);
    }
    if (opt.offsetY !== undefined)
      row += opt.offsetY;
    if (opt.offsetX !== undefined)
      col += opt.offsetX;
    row = Math.max(marginTop, Math.min(row, termHeight - marginBottom - effectiveHeight));
    col = Math.max(marginLeft, Math.min(col, termWidth - marginRight - width));
    return { width, row, col, maxHeight };
  }
  resolveAnchorRow(anchor, height, availHeight, marginTop) {
    switch (anchor) {
      case "top-left":
      case "top-center":
      case "top-right":
        return marginTop;
      case "bottom-left":
      case "bottom-center":
      case "bottom-right":
        return marginTop + availHeight - height;
      case "left-center":
      case "center":
      case "right-center":
        return marginTop + Math.floor((availHeight - height) / 2);
    }
  }
  resolveAnchorCol(anchor, width, availWidth, marginLeft) {
    switch (anchor) {
      case "top-left":
      case "left-center":
      case "bottom-left":
        return marginLeft;
      case "top-right":
      case "right-center":
      case "bottom-right":
        return marginLeft + availWidth - width;
      case "top-center":
      case "center":
      case "bottom-center":
        return marginLeft + Math.floor((availWidth - width) / 2);
    }
  }
  compositeOverlays(lines, termWidth, termHeight) {
    if (this.overlayStack.length === 0)
      return lines;
    const result = [...lines];
    const rendered = [];
    let minLinesNeeded = result.length;
    const visibleEntries = this.overlayStack.filter((e) => this.isOverlayVisible(e));
    visibleEntries.sort((a, b) => a.focusOrder - b.focusOrder);
    for (const entry of visibleEntries) {
      const { component, options } = entry;
      const { width, maxHeight } = this.resolveOverlayLayout(options, 0, termWidth, termHeight);
      let overlayLines = component.render(width);
      if (maxHeight !== undefined && overlayLines.length > maxHeight) {
        overlayLines = overlayLines.slice(0, maxHeight);
      }
      const { row, col } = this.resolveOverlayLayout(options, overlayLines.length, termWidth, termHeight);
      rendered.push({ overlayLines, row, col, w: width });
      minLinesNeeded = Math.max(minLinesNeeded, row + overlayLines.length);
    }
    const workingHeight = Math.max(result.length, termHeight, minLinesNeeded);
    while (result.length < workingHeight) {
      result.push("");
    }
    const viewportStart = Math.max(0, workingHeight - termHeight);
    for (const { overlayLines, row, col, w } of rendered) {
      for (let i = 0;i < overlayLines.length; i++) {
        const idx = viewportStart + row + i;
        if (idx >= 0 && idx < result.length) {
          const truncatedOverlayLine = visibleWidth(overlayLines[i]) > w ? sliceByColumn(overlayLines[i], 0, w, true) : overlayLines[i];
          result[idx] = this.compositeLineAt(result[idx], truncatedOverlayLine, col, w, termWidth);
        }
      }
    }
    return result;
  }
  static SEGMENT_RESET = "\x1B[0m\x1B]8;;\x07";
  applyLineResets(lines) {
    const reset = TUI.SEGMENT_RESET;
    for (let i = 0;i < lines.length; i++) {
      const line = lines[i];
      if (!isImageLine(line)) {
        lines[i] = line + reset;
      }
    }
    return lines;
  }
  compositeLineAt(baseLine, overlayLine, startCol, overlayWidth, totalWidth) {
    if (isImageLine(baseLine))
      return baseLine;
    const afterStart = startCol + overlayWidth;
    const base = extractSegments(baseLine, startCol, afterStart, totalWidth - afterStart, true);
    const overlay = sliceWithWidth(overlayLine, 0, overlayWidth, true);
    const beforePad = Math.max(0, startCol - base.beforeWidth);
    const overlayPad = Math.max(0, overlayWidth - overlay.width);
    const actualBeforeWidth = Math.max(startCol, base.beforeWidth);
    const actualOverlayWidth = Math.max(overlayWidth, overlay.width);
    const afterTarget = Math.max(0, totalWidth - actualBeforeWidth - actualOverlayWidth);
    const afterPad = Math.max(0, afterTarget - base.afterWidth);
    const r = TUI.SEGMENT_RESET;
    const result = base.before + " ".repeat(beforePad) + r + overlay.text + " ".repeat(overlayPad) + r + base.after + " ".repeat(afterPad);
    const resultWidth = visibleWidth(result);
    if (resultWidth <= totalWidth) {
      return result;
    }
    return sliceByColumn(result, 0, totalWidth, true);
  }
  extractCursorPosition(lines, height) {
    const viewportTop = Math.max(0, lines.length - height);
    for (let row = lines.length - 1;row >= viewportTop; row--) {
      const line = lines[row];
      const markerIndex = line.indexOf(CURSOR_MARKER);
      if (markerIndex !== -1) {
        const beforeMarker = line.slice(0, markerIndex);
        const col = visibleWidth(beforeMarker);
        lines[row] = line.slice(0, markerIndex) + line.slice(markerIndex + CURSOR_MARKER.length);
        return { row, col };
      }
    }
    return null;
  }
  doRender() {
    if (this.stopped)
      return;
    const width = this.terminal.columns;
    const height = this.terminal.rows;
    const widthChanged = this.previousWidth !== 0 && this.previousWidth !== width;
    const heightChanged = this.previousHeight !== 0 && this.previousHeight !== height;
    const previousBufferLength = this.previousHeight > 0 ? this.previousViewportTop + this.previousHeight : height;
    let prevViewportTop = heightChanged ? Math.max(0, previousBufferLength - height) : this.previousViewportTop;
    let viewportTop = prevViewportTop;
    let hardwareCursorRow = this.hardwareCursorRow;
    const computeLineDiff = (targetRow) => {
      const currentScreenRow = hardwareCursorRow - prevViewportTop;
      const targetScreenRow = targetRow - viewportTop;
      return targetScreenRow - currentScreenRow;
    };
    let newLines = this.render(width);
    if (this.overlayStack.length > 0) {
      newLines = this.compositeOverlays(newLines, width, height);
    }
    const cursorPos = this.extractCursorPosition(newLines, height);
    newLines = this.applyLineResets(newLines);
    const fullRender = (clear) => {
      this.fullRedrawCount += 1;
      let buffer2 = "\x1B[?2026h";
      if (clear)
        buffer2 += "\x1B[2J\x1B[H\x1B[3J";
      for (let i = 0;i < newLines.length; i++) {
        if (i > 0)
          buffer2 += `\r
`;
        buffer2 += newLines[i];
      }
      buffer2 += "\x1B[?2026l";
      this.terminal.write(buffer2);
      this.cursorRow = Math.max(0, newLines.length - 1);
      this.hardwareCursorRow = this.cursorRow;
      if (clear) {
        this.maxLinesRendered = newLines.length;
      } else {
        this.maxLinesRendered = Math.max(this.maxLinesRendered, newLines.length);
      }
      const bufferLength = Math.max(height, newLines.length);
      this.previousViewportTop = Math.max(0, bufferLength - height);
      this.positionHardwareCursor(cursorPos, newLines.length);
      this.previousLines = newLines;
      this.previousWidth = width;
      this.previousHeight = height;
    };
    const debugRedraw = process.env.PI_DEBUG_REDRAW === "1";
    const logRedraw = (reason) => {
      if (!debugRedraw)
        return;
      const logPath = path.join(os.homedir(), ".pi", "agent", "pi-debug.log");
      const msg = `[${new Date().toISOString()}] fullRender: ${reason} (prev=${this.previousLines.length}, new=${newLines.length}, height=${height})
`;
      fs.appendFileSync(logPath, msg);
    };
    if (this.previousLines.length === 0 && !widthChanged && !heightChanged) {
      logRedraw("first render");
      fullRender(false);
      return;
    }
    if (widthChanged) {
      logRedraw(`terminal width changed (${this.previousWidth} -> ${width})`);
      fullRender(true);
      return;
    }
    if (heightChanged && !isTermuxSession()) {
      logRedraw(`terminal height changed (${this.previousHeight} -> ${height})`);
      fullRender(true);
      return;
    }
    if (this.clearOnShrink && newLines.length < this.maxLinesRendered && this.overlayStack.length === 0) {
      logRedraw(`clearOnShrink (maxLinesRendered=${this.maxLinesRendered})`);
      fullRender(true);
      return;
    }
    let firstChanged = -1;
    let lastChanged = -1;
    const maxLines = Math.max(newLines.length, this.previousLines.length);
    for (let i = 0;i < maxLines; i++) {
      const oldLine = i < this.previousLines.length ? this.previousLines[i] : "";
      const newLine = i < newLines.length ? newLines[i] : "";
      if (oldLine !== newLine) {
        if (firstChanged === -1) {
          firstChanged = i;
        }
        lastChanged = i;
      }
    }
    const appendedLines = newLines.length > this.previousLines.length;
    if (appendedLines) {
      if (firstChanged === -1) {
        firstChanged = this.previousLines.length;
      }
      lastChanged = newLines.length - 1;
    }
    const appendStart = appendedLines && firstChanged === this.previousLines.length && firstChanged > 0;
    if (firstChanged === -1) {
      this.positionHardwareCursor(cursorPos, newLines.length);
      this.previousViewportTop = prevViewportTop;
      this.previousHeight = height;
      return;
    }
    if (firstChanged >= newLines.length) {
      if (this.previousLines.length > newLines.length) {
        let buffer2 = "\x1B[?2026h";
        const targetRow = Math.max(0, newLines.length - 1);
        if (targetRow < prevViewportTop) {
          logRedraw(`deleted lines moved viewport up (${targetRow} < ${prevViewportTop})`);
          fullRender(true);
          return;
        }
        const lineDiff2 = computeLineDiff(targetRow);
        if (lineDiff2 > 0)
          buffer2 += `\x1B[${lineDiff2}B`;
        else if (lineDiff2 < 0)
          buffer2 += `\x1B[${-lineDiff2}A`;
        buffer2 += "\r";
        const extraLines = this.previousLines.length - newLines.length;
        if (extraLines > height) {
          logRedraw(`extraLines > height (${extraLines} > ${height})`);
          fullRender(true);
          return;
        }
        if (extraLines > 0) {
          buffer2 += "\x1B[1B";
        }
        for (let i = 0;i < extraLines; i++) {
          buffer2 += "\r\x1B[2K";
          if (i < extraLines - 1)
            buffer2 += "\x1B[1B";
        }
        if (extraLines > 0) {
          buffer2 += `\x1B[${extraLines}A`;
        }
        buffer2 += "\x1B[?2026l";
        this.terminal.write(buffer2);
        this.cursorRow = targetRow;
        this.hardwareCursorRow = targetRow;
      }
      this.positionHardwareCursor(cursorPos, newLines.length);
      this.previousLines = newLines;
      this.previousWidth = width;
      this.previousHeight = height;
      this.previousViewportTop = prevViewportTop;
      return;
    }
    if (firstChanged < prevViewportTop) {
      logRedraw(`firstChanged < viewportTop (${firstChanged} < ${prevViewportTop})`);
      fullRender(true);
      return;
    }
    let buffer = "\x1B[?2026h";
    const prevViewportBottom = prevViewportTop + height - 1;
    const moveTargetRow = appendStart ? firstChanged - 1 : firstChanged;
    if (moveTargetRow > prevViewportBottom) {
      const currentScreenRow = Math.max(0, Math.min(height - 1, hardwareCursorRow - prevViewportTop));
      const moveToBottom = height - 1 - currentScreenRow;
      if (moveToBottom > 0) {
        buffer += `\x1B[${moveToBottom}B`;
      }
      const scroll = moveTargetRow - prevViewportBottom;
      buffer += `\r
`.repeat(scroll);
      prevViewportTop += scroll;
      viewportTop += scroll;
      hardwareCursorRow = moveTargetRow;
    }
    const lineDiff = computeLineDiff(moveTargetRow);
    if (lineDiff > 0) {
      buffer += `\x1B[${lineDiff}B`;
    } else if (lineDiff < 0) {
      buffer += `\x1B[${-lineDiff}A`;
    }
    buffer += appendStart ? `\r
` : "\r";
    const renderEnd = Math.min(lastChanged, newLines.length - 1);
    for (let i = firstChanged;i <= renderEnd; i++) {
      if (i > firstChanged)
        buffer += `\r
`;
      buffer += "\x1B[2K";
      const line = newLines[i];
      const isImage = isImageLine(line);
      if (!isImage && visibleWidth(line) > width) {
        const crashLogPath = path.join(os.homedir(), ".pi", "agent", "pi-crash.log");
        const crashData = [
          `Crash at ${new Date().toISOString()}`,
          `Terminal width: ${width}`,
          `Line ${i} visible width: ${visibleWidth(line)}`,
          "",
          "=== All rendered lines ===",
          ...newLines.map((l, idx) => `[${idx}] (w=${visibleWidth(l)}) ${l}`),
          ""
        ].join(`
`);
        fs.mkdirSync(path.dirname(crashLogPath), { recursive: true });
        fs.writeFileSync(crashLogPath, crashData);
        this.stop();
        const errorMsg = [
          `Rendered line ${i} exceeds terminal width (${visibleWidth(line)} > ${width}).`,
          "",
          "This is likely caused by a custom TUI component not truncating its output.",
          "Use visibleWidth() to measure and truncateToWidth() to truncate lines.",
          "",
          `Debug log written to: ${crashLogPath}`
        ].join(`
`);
        throw new Error(errorMsg);
      }
      buffer += line;
    }
    let finalCursorRow = renderEnd;
    if (this.previousLines.length > newLines.length) {
      if (renderEnd < newLines.length - 1) {
        const moveDown = newLines.length - 1 - renderEnd;
        buffer += `\x1B[${moveDown}B`;
        finalCursorRow = newLines.length - 1;
      }
      const extraLines = this.previousLines.length - newLines.length;
      for (let i = newLines.length;i < this.previousLines.length; i++) {
        buffer += `\r
\x1B[2K`;
      }
      buffer += `\x1B[${extraLines}A`;
    }
    buffer += "\x1B[?2026l";
    if (process.env.PI_TUI_DEBUG === "1") {
      const debugDir = "/tmp/tui";
      fs.mkdirSync(debugDir, { recursive: true });
      const debugPath = path.join(debugDir, `render-${Date.now()}-${Math.random().toString(36).slice(2)}.log`);
      const debugData = [
        `firstChanged: ${firstChanged}`,
        `viewportTop: ${viewportTop}`,
        `cursorRow: ${this.cursorRow}`,
        `height: ${height}`,
        `lineDiff: ${lineDiff}`,
        `hardwareCursorRow: ${hardwareCursorRow}`,
        `renderEnd: ${renderEnd}`,
        `finalCursorRow: ${finalCursorRow}`,
        `cursorPos: ${JSON.stringify(cursorPos)}`,
        `newLines.length: ${newLines.length}`,
        `previousLines.length: ${this.previousLines.length}`,
        "",
        "=== newLines ===",
        JSON.stringify(newLines, null, 2),
        "",
        "=== previousLines ===",
        JSON.stringify(this.previousLines, null, 2),
        "",
        "=== buffer ===",
        JSON.stringify(buffer)
      ].join(`
`);
      fs.writeFileSync(debugPath, debugData);
    }
    this.terminal.write(buffer);
    this.cursorRow = Math.max(0, newLines.length - 1);
    this.hardwareCursorRow = finalCursorRow;
    this.maxLinesRendered = Math.max(this.maxLinesRendered, newLines.length);
    this.previousViewportTop = Math.max(prevViewportTop, finalCursorRow - height + 1);
    this.positionHardwareCursor(cursorPos, newLines.length);
    this.previousLines = newLines;
    this.previousWidth = width;
    this.previousHeight = height;
  }
  positionHardwareCursor(cursorPos, totalLines) {
    if (!cursorPos || totalLines <= 0) {
      this.terminal.hideCursor();
      return;
    }
    const targetRow = Math.max(0, Math.min(cursorPos.row, totalLines - 1));
    const targetCol = Math.max(0, cursorPos.col);
    const rowDelta = targetRow - this.hardwareCursorRow;
    let buffer = "";
    if (rowDelta > 0) {
      buffer += `\x1B[${rowDelta}B`;
    } else if (rowDelta < 0) {
      buffer += `\x1B[${-rowDelta}A`;
    }
    buffer += `\x1B[${targetCol + 1}G`;
    if (buffer) {
      this.terminal.write(buffer);
    }
    this.hardwareCursorRow = targetRow;
    if (this.showHardwareCursor) {
      this.terminal.showCursor();
    } else {
      this.terminal.hideCursor();
    }
  }
}

// node_modules/@mariozechner/pi-tui/dist/undo-stack.js
class UndoStack {
  stack = [];
  push(state) {
    this.stack.push(structuredClone(state));
  }
  pop() {
    return this.stack.pop();
  }
  clear() {
    this.stack.length = 0;
  }
  get length() {
    return this.stack.length;
  }
}

// node_modules/@mariozechner/pi-tui/dist/components/select-list.js
var DEFAULT_PRIMARY_COLUMN_WIDTH = 32;
var PRIMARY_COLUMN_GAP = 2;
var MIN_DESCRIPTION_WIDTH = 10;
var normalizeToSingleLine = (text) => text.replace(/[\r\n]+/g, " ").trim();
var clamp = (value, min, max) => Math.max(min, Math.min(value, max));

class SelectList {
  items = [];
  filteredItems = [];
  selectedIndex = 0;
  maxVisible = 5;
  theme;
  layout;
  onSelect;
  onCancel;
  onSelectionChange;
  constructor(items, maxVisible, theme, layout = {}) {
    this.items = items;
    this.filteredItems = items;
    this.maxVisible = maxVisible;
    this.theme = theme;
    this.layout = layout;
  }
  setFilter(filter) {
    this.filteredItems = this.items.filter((item) => item.value.toLowerCase().startsWith(filter.toLowerCase()));
    this.selectedIndex = 0;
  }
  setSelectedIndex(index) {
    this.selectedIndex = Math.max(0, Math.min(index, this.filteredItems.length - 1));
  }
  invalidate() {}
  render(width) {
    const lines = [];
    if (this.filteredItems.length === 0) {
      lines.push(this.theme.noMatch("  No matching commands"));
      return lines;
    }
    const primaryColumnWidth = this.getPrimaryColumnWidth();
    const startIndex = Math.max(0, Math.min(this.selectedIndex - Math.floor(this.maxVisible / 2), this.filteredItems.length - this.maxVisible));
    const endIndex = Math.min(startIndex + this.maxVisible, this.filteredItems.length);
    for (let i = startIndex;i < endIndex; i++) {
      const item = this.filteredItems[i];
      if (!item)
        continue;
      const isSelected = i === this.selectedIndex;
      const descriptionSingleLine = item.description ? normalizeToSingleLine(item.description) : undefined;
      lines.push(this.renderItem(item, isSelected, width, descriptionSingleLine, primaryColumnWidth));
    }
    if (startIndex > 0 || endIndex < this.filteredItems.length) {
      const scrollText = `  (${this.selectedIndex + 1}/${this.filteredItems.length})`;
      lines.push(this.theme.scrollInfo(truncateToWidth(scrollText, width - 2, "")));
    }
    return lines;
  }
  handleInput(keyData) {
    const kb = getKeybindings();
    if (kb.matches(keyData, "tui.select.up")) {
      this.selectedIndex = this.selectedIndex === 0 ? this.filteredItems.length - 1 : this.selectedIndex - 1;
      this.notifySelectionChange();
    } else if (kb.matches(keyData, "tui.select.down")) {
      this.selectedIndex = this.selectedIndex === this.filteredItems.length - 1 ? 0 : this.selectedIndex + 1;
      this.notifySelectionChange();
    } else if (kb.matches(keyData, "tui.select.confirm")) {
      const selectedItem = this.filteredItems[this.selectedIndex];
      if (selectedItem && this.onSelect) {
        this.onSelect(selectedItem);
      }
    } else if (kb.matches(keyData, "tui.select.cancel")) {
      if (this.onCancel) {
        this.onCancel();
      }
    }
  }
  renderItem(item, isSelected, width, descriptionSingleLine, primaryColumnWidth) {
    const prefix = isSelected ? "\u2192 " : "  ";
    const prefixWidth = visibleWidth(prefix);
    if (descriptionSingleLine && width > 40) {
      const effectivePrimaryColumnWidth = Math.max(1, Math.min(primaryColumnWidth, width - prefixWidth - 4));
      const maxPrimaryWidth = Math.max(1, effectivePrimaryColumnWidth - PRIMARY_COLUMN_GAP);
      const truncatedValue2 = this.truncatePrimary(item, isSelected, maxPrimaryWidth, effectivePrimaryColumnWidth);
      const truncatedValueWidth = visibleWidth(truncatedValue2);
      const spacing = " ".repeat(Math.max(1, effectivePrimaryColumnWidth - truncatedValueWidth));
      const descriptionStart = prefixWidth + truncatedValueWidth + spacing.length;
      const remainingWidth = width - descriptionStart - 2;
      if (remainingWidth > MIN_DESCRIPTION_WIDTH) {
        const truncatedDesc = truncateToWidth(descriptionSingleLine, remainingWidth, "");
        if (isSelected) {
          return this.theme.selectedText(`${prefix}${truncatedValue2}${spacing}${truncatedDesc}`);
        }
        const descText = this.theme.description(spacing + truncatedDesc);
        return prefix + truncatedValue2 + descText;
      }
    }
    const maxWidth = width - prefixWidth - 2;
    const truncatedValue = this.truncatePrimary(item, isSelected, maxWidth, maxWidth);
    if (isSelected) {
      return this.theme.selectedText(`${prefix}${truncatedValue}`);
    }
    return prefix + truncatedValue;
  }
  getPrimaryColumnWidth() {
    const { min, max } = this.getPrimaryColumnBounds();
    const widestPrimary = this.filteredItems.reduce((widest, item) => {
      return Math.max(widest, visibleWidth(this.getDisplayValue(item)) + PRIMARY_COLUMN_GAP);
    }, 0);
    return clamp(widestPrimary, min, max);
  }
  getPrimaryColumnBounds() {
    const rawMin = this.layout.minPrimaryColumnWidth ?? this.layout.maxPrimaryColumnWidth ?? DEFAULT_PRIMARY_COLUMN_WIDTH;
    const rawMax = this.layout.maxPrimaryColumnWidth ?? this.layout.minPrimaryColumnWidth ?? DEFAULT_PRIMARY_COLUMN_WIDTH;
    return {
      min: Math.max(1, Math.min(rawMin, rawMax)),
      max: Math.max(1, Math.max(rawMin, rawMax))
    };
  }
  truncatePrimary(item, isSelected, maxWidth, columnWidth) {
    const displayValue = this.getDisplayValue(item);
    const truncatedValue = this.layout.truncatePrimary ? this.layout.truncatePrimary({
      text: displayValue,
      maxWidth,
      columnWidth,
      item,
      isSelected
    }) : truncateToWidth(displayValue, maxWidth, "");
    return truncateToWidth(truncatedValue, maxWidth, "");
  }
  getDisplayValue(item) {
    return item.label || item.value;
  }
  notifySelectionChange() {
    const selectedItem = this.filteredItems[this.selectedIndex];
    if (selectedItem && this.onSelectionChange) {
      this.onSelectionChange(selectedItem);
    }
  }
  getSelectedItem() {
    const item = this.filteredItems[this.selectedIndex];
    return item || null;
  }
}

// node_modules/@mariozechner/pi-tui/dist/components/editor.js
var baseSegmenter = getSegmenter();
var PASTE_MARKER_REGEX = /\[paste #(\d+)( (\+\d+ lines|\d+ chars))?\]/g;
var PASTE_MARKER_SINGLE = /^\[paste #(\d+)( (\+\d+ lines|\d+ chars))?\]$/;
function isPasteMarker(segment) {
  return segment.length >= 10 && PASTE_MARKER_SINGLE.test(segment);
}
function segmentWithMarkers(text, validIds) {
  if (validIds.size === 0 || !text.includes("[paste #")) {
    return baseSegmenter.segment(text);
  }
  const markers = [];
  for (const m of text.matchAll(PASTE_MARKER_REGEX)) {
    const id = Number.parseInt(m[1], 10);
    if (!validIds.has(id))
      continue;
    markers.push({ start: m.index, end: m.index + m[0].length });
  }
  if (markers.length === 0) {
    return baseSegmenter.segment(text);
  }
  const baseSegments = baseSegmenter.segment(text);
  const result = [];
  let markerIdx = 0;
  for (const seg of baseSegments) {
    while (markerIdx < markers.length && markers[markerIdx].end <= seg.index) {
      markerIdx++;
    }
    const marker = markerIdx < markers.length ? markers[markerIdx] : null;
    if (marker && seg.index >= marker.start && seg.index < marker.end) {
      if (seg.index === marker.start) {
        const markerText = text.slice(marker.start, marker.end);
        result.push({
          segment: markerText,
          index: marker.start,
          input: text
        });
      }
    } else {
      result.push(seg);
    }
  }
  return result;
}
function wordWrapLine(line, maxWidth, preSegmented) {
  if (!line || maxWidth <= 0) {
    return [{ text: "", startIndex: 0, endIndex: 0 }];
  }
  const lineWidth = visibleWidth(line);
  if (lineWidth <= maxWidth) {
    return [{ text: line, startIndex: 0, endIndex: line.length }];
  }
  const chunks = [];
  const segments = preSegmented ?? [...baseSegmenter.segment(line)];
  let currentWidth = 0;
  let chunkStart = 0;
  let wrapOppIndex = -1;
  let wrapOppWidth = 0;
  for (let i = 0;i < segments.length; i++) {
    const seg = segments[i];
    const grapheme = seg.segment;
    const gWidth = visibleWidth(grapheme);
    const charIndex = seg.index;
    const isWs = !isPasteMarker(grapheme) && isWhitespaceChar(grapheme);
    if (currentWidth + gWidth > maxWidth) {
      if (wrapOppIndex >= 0 && currentWidth - wrapOppWidth + gWidth <= maxWidth) {
        chunks.push({ text: line.slice(chunkStart, wrapOppIndex), startIndex: chunkStart, endIndex: wrapOppIndex });
        chunkStart = wrapOppIndex;
        currentWidth -= wrapOppWidth;
      } else if (chunkStart < charIndex) {
        chunks.push({ text: line.slice(chunkStart, charIndex), startIndex: chunkStart, endIndex: charIndex });
        chunkStart = charIndex;
        currentWidth = 0;
      }
      wrapOppIndex = -1;
    }
    if (gWidth > maxWidth) {
      const subChunks = wordWrapLine(grapheme, maxWidth);
      for (let j = 0;j < subChunks.length - 1; j++) {
        const sc = subChunks[j];
        chunks.push({ text: sc.text, startIndex: charIndex + sc.startIndex, endIndex: charIndex + sc.endIndex });
      }
      const last = subChunks[subChunks.length - 1];
      chunkStart = charIndex + last.startIndex;
      currentWidth = visibleWidth(last.text);
      wrapOppIndex = -1;
      continue;
    }
    currentWidth += gWidth;
    const next = segments[i + 1];
    if (isWs && next && (isPasteMarker(next.segment) || !isWhitespaceChar(next.segment))) {
      wrapOppIndex = next.index;
      wrapOppWidth = currentWidth;
    }
  }
  chunks.push({ text: line.slice(chunkStart), startIndex: chunkStart, endIndex: line.length });
  return chunks;
}
var SLASH_COMMAND_SELECT_LIST_LAYOUT = {
  minPrimaryColumnWidth: 12,
  maxPrimaryColumnWidth: 32
};
var ATTACHMENT_AUTOCOMPLETE_DEBOUNCE_MS = 20;

class Editor {
  state = {
    lines: [""],
    cursorLine: 0,
    cursorCol: 0
  };
  focused = false;
  tui;
  theme;
  paddingX = 0;
  lastWidth = 80;
  scrollOffset = 0;
  borderColor;
  autocompleteProvider;
  autocompleteList;
  autocompleteState = null;
  autocompletePrefix = "";
  autocompleteMaxVisible = 5;
  autocompleteAbort;
  autocompleteDebounceTimer;
  autocompleteRequestTask = Promise.resolve();
  autocompleteStartToken = 0;
  autocompleteRequestId = 0;
  pastes = new Map;
  pasteCounter = 0;
  pasteBuffer = "";
  isInPaste = false;
  history = [];
  historyIndex = -1;
  killRing = new KillRing;
  lastAction = null;
  jumpMode = null;
  preferredVisualCol = null;
  undoStack = new UndoStack;
  onSubmit;
  onChange;
  disableSubmit = false;
  constructor(tui, theme, options = {}) {
    this.tui = tui;
    this.theme = theme;
    this.borderColor = theme.borderColor;
    const paddingX = options.paddingX ?? 0;
    this.paddingX = Number.isFinite(paddingX) ? Math.max(0, Math.floor(paddingX)) : 0;
    const maxVisible = options.autocompleteMaxVisible ?? 5;
    this.autocompleteMaxVisible = Number.isFinite(maxVisible) ? Math.max(3, Math.min(20, Math.floor(maxVisible))) : 5;
  }
  validPasteIds() {
    return new Set(this.pastes.keys());
  }
  segment(text) {
    return segmentWithMarkers(text, this.validPasteIds());
  }
  getPaddingX() {
    return this.paddingX;
  }
  setPaddingX(padding) {
    const newPadding = Number.isFinite(padding) ? Math.max(0, Math.floor(padding)) : 0;
    if (this.paddingX !== newPadding) {
      this.paddingX = newPadding;
      this.tui.requestRender();
    }
  }
  getAutocompleteMaxVisible() {
    return this.autocompleteMaxVisible;
  }
  setAutocompleteMaxVisible(maxVisible) {
    const newMaxVisible = Number.isFinite(maxVisible) ? Math.max(3, Math.min(20, Math.floor(maxVisible))) : 5;
    if (this.autocompleteMaxVisible !== newMaxVisible) {
      this.autocompleteMaxVisible = newMaxVisible;
      this.tui.requestRender();
    }
  }
  setAutocompleteProvider(provider) {
    this.cancelAutocomplete();
    this.autocompleteProvider = provider;
  }
  addToHistory(text) {
    const trimmed = text.trim();
    if (!trimmed)
      return;
    if (this.history.length > 0 && this.history[0] === trimmed)
      return;
    this.history.unshift(trimmed);
    if (this.history.length > 100) {
      this.history.pop();
    }
  }
  isEditorEmpty() {
    return this.state.lines.length === 1 && this.state.lines[0] === "";
  }
  isOnFirstVisualLine() {
    const visualLines = this.buildVisualLineMap(this.lastWidth);
    const currentVisualLine = this.findCurrentVisualLine(visualLines);
    return currentVisualLine === 0;
  }
  isOnLastVisualLine() {
    const visualLines = this.buildVisualLineMap(this.lastWidth);
    const currentVisualLine = this.findCurrentVisualLine(visualLines);
    return currentVisualLine === visualLines.length - 1;
  }
  navigateHistory(direction) {
    this.lastAction = null;
    if (this.history.length === 0)
      return;
    const newIndex = this.historyIndex - direction;
    if (newIndex < -1 || newIndex >= this.history.length)
      return;
    if (this.historyIndex === -1 && newIndex >= 0) {
      this.pushUndoSnapshot();
    }
    this.historyIndex = newIndex;
    if (this.historyIndex === -1) {
      this.setTextInternal("");
    } else {
      this.setTextInternal(this.history[this.historyIndex] || "");
    }
  }
  setTextInternal(text) {
    const lines = text.split(`
`);
    this.state.lines = lines.length === 0 ? [""] : lines;
    this.state.cursorLine = this.state.lines.length - 1;
    this.setCursorCol(this.state.lines[this.state.cursorLine]?.length || 0);
    this.scrollOffset = 0;
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  invalidate() {}
  render(width) {
    const maxPadding = Math.max(0, Math.floor((width - 1) / 2));
    const paddingX = Math.min(this.paddingX, maxPadding);
    const contentWidth = Math.max(1, width - paddingX * 2);
    const layoutWidth = Math.max(1, contentWidth - (paddingX ? 0 : 1));
    this.lastWidth = layoutWidth;
    const horizontal = this.borderColor("\u2500");
    const layoutLines = this.layoutText(layoutWidth);
    const terminalRows = this.tui.terminal.rows;
    const maxVisibleLines = Math.max(5, Math.floor(terminalRows * 0.3));
    let cursorLineIndex = layoutLines.findIndex((line) => line.hasCursor);
    if (cursorLineIndex === -1)
      cursorLineIndex = 0;
    if (cursorLineIndex < this.scrollOffset) {
      this.scrollOffset = cursorLineIndex;
    } else if (cursorLineIndex >= this.scrollOffset + maxVisibleLines) {
      this.scrollOffset = cursorLineIndex - maxVisibleLines + 1;
    }
    const maxScrollOffset = Math.max(0, layoutLines.length - maxVisibleLines);
    this.scrollOffset = Math.max(0, Math.min(this.scrollOffset, maxScrollOffset));
    const visibleLines = layoutLines.slice(this.scrollOffset, this.scrollOffset + maxVisibleLines);
    const result = [];
    const leftPadding = " ".repeat(paddingX);
    const rightPadding = leftPadding;
    if (this.scrollOffset > 0) {
      const indicator = `\u2500\u2500\u2500 \u2191 ${this.scrollOffset} more `;
      const remaining = width - visibleWidth(indicator);
      if (remaining >= 0) {
        result.push(this.borderColor(indicator + "\u2500".repeat(remaining)));
      } else {
        result.push(this.borderColor(truncateToWidth(indicator, width)));
      }
    } else {
      result.push(horizontal.repeat(width));
    }
    const emitCursorMarker = this.focused && !this.autocompleteState;
    for (const layoutLine of visibleLines) {
      let displayText = layoutLine.text;
      let lineVisibleWidth = visibleWidth(layoutLine.text);
      let cursorInPadding = false;
      if (layoutLine.hasCursor && layoutLine.cursorPos !== undefined) {
        const before = displayText.slice(0, layoutLine.cursorPos);
        const after = displayText.slice(layoutLine.cursorPos);
        const marker = emitCursorMarker ? CURSOR_MARKER : "";
        if (after.length > 0) {
          const afterGraphemes = [...this.segment(after)];
          const firstGrapheme = afterGraphemes[0]?.segment || "";
          const restAfter = after.slice(firstGrapheme.length);
          const cursor = `\x1B[7m${firstGrapheme}\x1B[0m`;
          displayText = before + marker + cursor + restAfter;
        } else {
          const cursor = "\x1B[7m \x1B[0m";
          displayText = before + marker + cursor;
          lineVisibleWidth = lineVisibleWidth + 1;
          if (lineVisibleWidth > contentWidth && paddingX > 0) {
            cursorInPadding = true;
          }
        }
      }
      const padding = " ".repeat(Math.max(0, contentWidth - lineVisibleWidth));
      const lineRightPadding = cursorInPadding ? rightPadding.slice(1) : rightPadding;
      result.push(`${leftPadding}${displayText}${padding}${lineRightPadding}`);
    }
    const linesBelow = layoutLines.length - (this.scrollOffset + visibleLines.length);
    if (linesBelow > 0) {
      const indicator = `\u2500\u2500\u2500 \u2193 ${linesBelow} more `;
      const remaining = width - visibleWidth(indicator);
      result.push(this.borderColor(indicator + "\u2500".repeat(Math.max(0, remaining))));
    } else {
      result.push(horizontal.repeat(width));
    }
    if (this.autocompleteState && this.autocompleteList) {
      const autocompleteResult = this.autocompleteList.render(contentWidth);
      for (const line of autocompleteResult) {
        const lineWidth = visibleWidth(line);
        const linePadding = " ".repeat(Math.max(0, contentWidth - lineWidth));
        result.push(`${leftPadding}${line}${linePadding}${rightPadding}`);
      }
    }
    return result;
  }
  handleInput(data) {
    const kb = getKeybindings();
    if (this.jumpMode !== null) {
      if (kb.matches(data, "tui.editor.jumpForward") || kb.matches(data, "tui.editor.jumpBackward")) {
        this.jumpMode = null;
        return;
      }
      if (data.charCodeAt(0) >= 32) {
        const direction = this.jumpMode;
        this.jumpMode = null;
        this.jumpToChar(data, direction);
        return;
      }
      this.jumpMode = null;
    }
    if (data.includes("\x1B[200~")) {
      this.isInPaste = true;
      this.pasteBuffer = "";
      data = data.replace("\x1B[200~", "");
    }
    if (this.isInPaste) {
      this.pasteBuffer += data;
      const endIndex = this.pasteBuffer.indexOf("\x1B[201~");
      if (endIndex !== -1) {
        const pasteContent = this.pasteBuffer.substring(0, endIndex);
        if (pasteContent.length > 0) {
          this.handlePaste(pasteContent);
        }
        this.isInPaste = false;
        const remaining = this.pasteBuffer.substring(endIndex + 6);
        this.pasteBuffer = "";
        if (remaining.length > 0) {
          this.handleInput(remaining);
        }
        return;
      }
      return;
    }
    if (kb.matches(data, "tui.input.copy")) {
      return;
    }
    if (kb.matches(data, "tui.editor.undo")) {
      this.undo();
      return;
    }
    if (this.autocompleteState && this.autocompleteList) {
      if (kb.matches(data, "tui.select.cancel")) {
        this.cancelAutocomplete();
        return;
      }
      if (kb.matches(data, "tui.select.up") || kb.matches(data, "tui.select.down")) {
        this.autocompleteList.handleInput(data);
        return;
      }
      if (kb.matches(data, "tui.input.tab")) {
        const selected = this.autocompleteList.getSelectedItem();
        if (selected && this.autocompleteProvider) {
          this.pushUndoSnapshot();
          this.lastAction = null;
          const result = this.autocompleteProvider.applyCompletion(this.state.lines, this.state.cursorLine, this.state.cursorCol, selected, this.autocompletePrefix);
          this.state.lines = result.lines;
          this.state.cursorLine = result.cursorLine;
          this.setCursorCol(result.cursorCol);
          this.cancelAutocomplete();
          if (this.onChange)
            this.onChange(this.getText());
        }
        return;
      }
      if (kb.matches(data, "tui.select.confirm")) {
        const selected = this.autocompleteList.getSelectedItem();
        if (selected && this.autocompleteProvider) {
          this.pushUndoSnapshot();
          this.lastAction = null;
          const result = this.autocompleteProvider.applyCompletion(this.state.lines, this.state.cursorLine, this.state.cursorCol, selected, this.autocompletePrefix);
          this.state.lines = result.lines;
          this.state.cursorLine = result.cursorLine;
          this.setCursorCol(result.cursorCol);
          if (this.autocompletePrefix.startsWith("/")) {
            this.cancelAutocomplete();
          } else {
            this.cancelAutocomplete();
            if (this.onChange)
              this.onChange(this.getText());
            return;
          }
        }
      }
    }
    if (kb.matches(data, "tui.input.tab") && !this.autocompleteState) {
      this.handleTabCompletion();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteToLineEnd")) {
      this.deleteToEndOfLine();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteToLineStart")) {
      this.deleteToStartOfLine();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteWordBackward")) {
      this.deleteWordBackwards();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteWordForward")) {
      this.deleteWordForward();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteCharBackward") || matchesKey(data, "shift+backspace")) {
      this.handleBackspace();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteCharForward") || matchesKey(data, "shift+delete")) {
      this.handleForwardDelete();
      return;
    }
    if (kb.matches(data, "tui.editor.yank")) {
      this.yank();
      return;
    }
    if (kb.matches(data, "tui.editor.yankPop")) {
      this.yankPop();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorLineStart")) {
      this.moveToLineStart();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorLineEnd")) {
      this.moveToLineEnd();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorWordLeft")) {
      this.moveWordBackwards();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorWordRight")) {
      this.moveWordForwards();
      return;
    }
    if (kb.matches(data, "tui.input.newLine") || data.charCodeAt(0) === 10 && data.length > 1 || data === "\x1B\r" || data === "\x1B[13;2~" || data.length > 1 && data.includes("\x1B") && data.includes("\r") || data === `
` && data.length === 1) {
      if (this.shouldSubmitOnBackslashEnter(data, kb)) {
        this.handleBackspace();
        this.submitValue();
        return;
      }
      this.addNewLine();
      return;
    }
    if (kb.matches(data, "tui.input.submit")) {
      if (this.disableSubmit)
        return;
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      if (this.state.cursorCol > 0 && currentLine[this.state.cursorCol - 1] === "\\") {
        this.handleBackspace();
        this.addNewLine();
        return;
      }
      this.submitValue();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorUp")) {
      if (this.isEditorEmpty()) {
        this.navigateHistory(-1);
      } else if (this.historyIndex > -1 && this.isOnFirstVisualLine()) {
        this.navigateHistory(-1);
      } else if (this.isOnFirstVisualLine()) {
        this.moveToLineStart();
      } else {
        this.moveCursor(-1, 0);
      }
      return;
    }
    if (kb.matches(data, "tui.editor.cursorDown")) {
      if (this.historyIndex > -1 && this.isOnLastVisualLine()) {
        this.navigateHistory(1);
      } else if (this.isOnLastVisualLine()) {
        this.moveToLineEnd();
      } else {
        this.moveCursor(1, 0);
      }
      return;
    }
    if (kb.matches(data, "tui.editor.cursorRight")) {
      this.moveCursor(0, 1);
      return;
    }
    if (kb.matches(data, "tui.editor.cursorLeft")) {
      this.moveCursor(0, -1);
      return;
    }
    if (kb.matches(data, "tui.editor.pageUp")) {
      this.pageScroll(-1);
      return;
    }
    if (kb.matches(data, "tui.editor.pageDown")) {
      this.pageScroll(1);
      return;
    }
    if (kb.matches(data, "tui.editor.jumpForward")) {
      this.jumpMode = "forward";
      return;
    }
    if (kb.matches(data, "tui.editor.jumpBackward")) {
      this.jumpMode = "backward";
      return;
    }
    if (matchesKey(data, "shift+space")) {
      this.insertCharacter(" ");
      return;
    }
    const kittyPrintable = decodeKittyPrintable(data);
    if (kittyPrintable !== undefined) {
      this.insertCharacter(kittyPrintable);
      return;
    }
    if (data.charCodeAt(0) >= 32) {
      this.insertCharacter(data);
    }
  }
  layoutText(contentWidth) {
    const layoutLines = [];
    if (this.state.lines.length === 0 || this.state.lines.length === 1 && this.state.lines[0] === "") {
      layoutLines.push({
        text: "",
        hasCursor: true,
        cursorPos: 0
      });
      return layoutLines;
    }
    for (let i = 0;i < this.state.lines.length; i++) {
      const line = this.state.lines[i] || "";
      const isCurrentLine = i === this.state.cursorLine;
      const lineVisibleWidth = visibleWidth(line);
      if (lineVisibleWidth <= contentWidth) {
        if (isCurrentLine) {
          layoutLines.push({
            text: line,
            hasCursor: true,
            cursorPos: this.state.cursorCol
          });
        } else {
          layoutLines.push({
            text: line,
            hasCursor: false
          });
        }
      } else {
        const chunks = wordWrapLine(line, contentWidth, [...this.segment(line)]);
        for (let chunkIndex = 0;chunkIndex < chunks.length; chunkIndex++) {
          const chunk = chunks[chunkIndex];
          if (!chunk)
            continue;
          const cursorPos = this.state.cursorCol;
          const isLastChunk = chunkIndex === chunks.length - 1;
          let hasCursorInChunk = false;
          let adjustedCursorPos = 0;
          if (isCurrentLine) {
            if (isLastChunk) {
              hasCursorInChunk = cursorPos >= chunk.startIndex;
              adjustedCursorPos = cursorPos - chunk.startIndex;
            } else {
              hasCursorInChunk = cursorPos >= chunk.startIndex && cursorPos < chunk.endIndex;
              if (hasCursorInChunk) {
                adjustedCursorPos = cursorPos - chunk.startIndex;
                if (adjustedCursorPos > chunk.text.length) {
                  adjustedCursorPos = chunk.text.length;
                }
              }
            }
          }
          if (hasCursorInChunk) {
            layoutLines.push({
              text: chunk.text,
              hasCursor: true,
              cursorPos: adjustedCursorPos
            });
          } else {
            layoutLines.push({
              text: chunk.text,
              hasCursor: false
            });
          }
        }
      }
    }
    return layoutLines;
  }
  getText() {
    return this.state.lines.join(`
`);
  }
  expandPasteMarkers(text) {
    let result = text;
    for (const [pasteId, pasteContent] of this.pastes) {
      const markerRegex = new RegExp(`\\[paste #${pasteId}( (\\+\\d+ lines|\\d+ chars))?\\]`, "g");
      result = result.replace(markerRegex, () => pasteContent);
    }
    return result;
  }
  getExpandedText() {
    return this.expandPasteMarkers(this.state.lines.join(`
`));
  }
  getLines() {
    return [...this.state.lines];
  }
  getCursor() {
    return { line: this.state.cursorLine, col: this.state.cursorCol };
  }
  setText(text) {
    this.cancelAutocomplete();
    this.lastAction = null;
    this.historyIndex = -1;
    const normalized = this.normalizeText(text);
    if (this.getText() !== normalized) {
      this.pushUndoSnapshot();
    }
    this.setTextInternal(normalized);
  }
  insertTextAtCursor(text) {
    if (!text)
      return;
    this.cancelAutocomplete();
    this.pushUndoSnapshot();
    this.lastAction = null;
    this.historyIndex = -1;
    this.insertTextAtCursorInternal(text);
  }
  normalizeText(text) {
    return text.replace(/\r\n/g, `
`).replace(/\r/g, `
`).replace(/\t/g, "    ");
  }
  insertTextAtCursorInternal(text) {
    if (!text)
      return;
    const normalized = this.normalizeText(text);
    const insertedLines = normalized.split(`
`);
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    const beforeCursor = currentLine.slice(0, this.state.cursorCol);
    const afterCursor = currentLine.slice(this.state.cursorCol);
    if (insertedLines.length === 1) {
      this.state.lines[this.state.cursorLine] = beforeCursor + normalized + afterCursor;
      this.setCursorCol(this.state.cursorCol + normalized.length);
    } else {
      this.state.lines = [
        ...this.state.lines.slice(0, this.state.cursorLine),
        beforeCursor + insertedLines[0],
        ...insertedLines.slice(1, -1),
        insertedLines[insertedLines.length - 1] + afterCursor,
        ...this.state.lines.slice(this.state.cursorLine + 1)
      ];
      this.state.cursorLine += insertedLines.length - 1;
      this.setCursorCol((insertedLines[insertedLines.length - 1] || "").length);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  insertCharacter(char, skipUndoCoalescing) {
    this.historyIndex = -1;
    if (!skipUndoCoalescing) {
      if (isWhitespaceChar(char) || this.lastAction !== "type-word") {
        this.pushUndoSnapshot();
      }
      this.lastAction = "type-word";
    }
    const line = this.state.lines[this.state.cursorLine] || "";
    const before = line.slice(0, this.state.cursorCol);
    const after = line.slice(this.state.cursorCol);
    this.state.lines[this.state.cursorLine] = before + char + after;
    this.setCursorCol(this.state.cursorCol + char.length);
    if (this.onChange) {
      this.onChange(this.getText());
    }
    if (!this.autocompleteState) {
      if (char === "/" && this.isAtStartOfMessage()) {
        this.tryTriggerAutocomplete();
      } else if (char === "@") {
        const currentLine = this.state.lines[this.state.cursorLine] || "";
        const textBeforeCursor = currentLine.slice(0, this.state.cursorCol);
        const charBeforeAt = textBeforeCursor[textBeforeCursor.length - 2];
        if (textBeforeCursor.length === 1 || charBeforeAt === " " || charBeforeAt === "\t") {
          this.tryTriggerAutocomplete();
        }
      } else if (/[a-zA-Z0-9.\-_]/.test(char)) {
        const currentLine = this.state.lines[this.state.cursorLine] || "";
        const textBeforeCursor = currentLine.slice(0, this.state.cursorCol);
        if (this.isInSlashCommandContext(textBeforeCursor)) {
          this.tryTriggerAutocomplete();
        } else if (textBeforeCursor.match(/(?:^|[\s])@[^\s]*$/)) {
          this.tryTriggerAutocomplete();
        }
      }
    } else {
      this.updateAutocomplete();
    }
  }
  handlePaste(pastedText) {
    this.cancelAutocomplete();
    this.historyIndex = -1;
    this.lastAction = null;
    this.pushUndoSnapshot();
    const cleanText = this.normalizeText(pastedText);
    let filteredText = cleanText.split("").filter((char) => char === `
` || char.charCodeAt(0) >= 32).join("");
    if (/^[/~.]/.test(filteredText)) {
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      const charBeforeCursor = this.state.cursorCol > 0 ? currentLine[this.state.cursorCol - 1] : "";
      if (charBeforeCursor && /\w/.test(charBeforeCursor)) {
        filteredText = ` ${filteredText}`;
      }
    }
    const pastedLines = filteredText.split(`
`);
    const totalChars = filteredText.length;
    if (pastedLines.length > 10 || totalChars > 1000) {
      this.pasteCounter++;
      const pasteId = this.pasteCounter;
      this.pastes.set(pasteId, filteredText);
      const marker = pastedLines.length > 10 ? `[paste #${pasteId} +${pastedLines.length} lines]` : `[paste #${pasteId} ${totalChars} chars]`;
      this.insertTextAtCursorInternal(marker);
      return;
    }
    if (pastedLines.length === 1) {
      this.insertTextAtCursorInternal(filteredText);
      return;
    }
    this.insertTextAtCursorInternal(filteredText);
  }
  addNewLine() {
    this.cancelAutocomplete();
    this.historyIndex = -1;
    this.lastAction = null;
    this.pushUndoSnapshot();
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    const before = currentLine.slice(0, this.state.cursorCol);
    const after = currentLine.slice(this.state.cursorCol);
    this.state.lines[this.state.cursorLine] = before;
    this.state.lines.splice(this.state.cursorLine + 1, 0, after);
    this.state.cursorLine++;
    this.setCursorCol(0);
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  shouldSubmitOnBackslashEnter(data, kb) {
    if (this.disableSubmit)
      return false;
    if (!matchesKey(data, "enter"))
      return false;
    const submitKeys = kb.getKeys("tui.input.submit");
    const hasShiftEnter = submitKeys.includes("shift+enter") || submitKeys.includes("shift+return");
    if (!hasShiftEnter)
      return false;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    return this.state.cursorCol > 0 && currentLine[this.state.cursorCol - 1] === "\\";
  }
  submitValue() {
    this.cancelAutocomplete();
    const result = this.expandPasteMarkers(this.state.lines.join(`
`)).trim();
    this.state = { lines: [""], cursorLine: 0, cursorCol: 0 };
    this.pastes.clear();
    this.pasteCounter = 0;
    this.historyIndex = -1;
    this.scrollOffset = 0;
    this.undoStack.clear();
    this.lastAction = null;
    if (this.onChange)
      this.onChange("");
    if (this.onSubmit)
      this.onSubmit(result);
  }
  handleBackspace() {
    this.historyIndex = -1;
    this.lastAction = null;
    if (this.state.cursorCol > 0) {
      this.pushUndoSnapshot();
      const line = this.state.lines[this.state.cursorLine] || "";
      const beforeCursor = line.slice(0, this.state.cursorCol);
      const graphemes = [...this.segment(beforeCursor)];
      const lastGrapheme = graphemes[graphemes.length - 1];
      const graphemeLength = lastGrapheme ? lastGrapheme.segment.length : 1;
      const before = line.slice(0, this.state.cursorCol - graphemeLength);
      const after = line.slice(this.state.cursorCol);
      this.state.lines[this.state.cursorLine] = before + after;
      this.setCursorCol(this.state.cursorCol - graphemeLength);
    } else if (this.state.cursorLine > 0) {
      this.pushUndoSnapshot();
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      const previousLine = this.state.lines[this.state.cursorLine - 1] || "";
      this.state.lines[this.state.cursorLine - 1] = previousLine + currentLine;
      this.state.lines.splice(this.state.cursorLine, 1);
      this.state.cursorLine--;
      this.setCursorCol(previousLine.length);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
    if (this.autocompleteState) {
      this.updateAutocomplete();
    } else {
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      const textBeforeCursor = currentLine.slice(0, this.state.cursorCol);
      if (this.isInSlashCommandContext(textBeforeCursor)) {
        this.tryTriggerAutocomplete();
      } else if (textBeforeCursor.match(/(?:^|[\s])@[^\s]*$/)) {
        this.tryTriggerAutocomplete();
      }
    }
  }
  setCursorCol(col) {
    this.state.cursorCol = col;
    this.preferredVisualCol = null;
  }
  moveToVisualLine(visualLines, currentVisualLine, targetVisualLine) {
    const currentVL = visualLines[currentVisualLine];
    const targetVL = visualLines[targetVisualLine];
    if (currentVL && targetVL) {
      const currentVisualCol = this.state.cursorCol - currentVL.startCol;
      const isLastSourceSegment = currentVisualLine === visualLines.length - 1 || visualLines[currentVisualLine + 1]?.logicalLine !== currentVL.logicalLine;
      const sourceMaxVisualCol = isLastSourceSegment ? currentVL.length : Math.max(0, currentVL.length - 1);
      const isLastTargetSegment = targetVisualLine === visualLines.length - 1 || visualLines[targetVisualLine + 1]?.logicalLine !== targetVL.logicalLine;
      const targetMaxVisualCol = isLastTargetSegment ? targetVL.length : Math.max(0, targetVL.length - 1);
      const moveToVisualCol = this.computeVerticalMoveColumn(currentVisualCol, sourceMaxVisualCol, targetMaxVisualCol);
      this.state.cursorLine = targetVL.logicalLine;
      const targetCol = targetVL.startCol + moveToVisualCol;
      const logicalLine = this.state.lines[targetVL.logicalLine] || "";
      this.state.cursorCol = Math.min(targetCol, logicalLine.length);
      const segments = [...this.segment(logicalLine)];
      for (const seg of segments) {
        if (seg.index > this.state.cursorCol)
          break;
        if (seg.segment.length <= 1)
          continue;
        if (this.state.cursorCol < seg.index + seg.segment.length) {
          this.state.cursorCol = currentVisualLine > targetVisualLine ? seg.index : seg.index + seg.segment.length;
          break;
        }
      }
    }
  }
  computeVerticalMoveColumn(currentVisualCol, sourceMaxVisualCol, targetMaxVisualCol) {
    const hasPreferred = this.preferredVisualCol !== null;
    const cursorInMiddle = currentVisualCol < sourceMaxVisualCol;
    const targetTooShort = targetMaxVisualCol < currentVisualCol;
    if (!hasPreferred || cursorInMiddle) {
      if (targetTooShort) {
        this.preferredVisualCol = currentVisualCol;
        return targetMaxVisualCol;
      }
      this.preferredVisualCol = null;
      return currentVisualCol;
    }
    const targetCantFitPreferred = targetMaxVisualCol < this.preferredVisualCol;
    if (targetTooShort || targetCantFitPreferred) {
      return targetMaxVisualCol;
    }
    const result = this.preferredVisualCol;
    this.preferredVisualCol = null;
    return result;
  }
  moveToLineStart() {
    this.lastAction = null;
    this.setCursorCol(0);
  }
  moveToLineEnd() {
    this.lastAction = null;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    this.setCursorCol(currentLine.length);
  }
  deleteToStartOfLine() {
    this.historyIndex = -1;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol > 0) {
      this.pushUndoSnapshot();
      const deletedText = currentLine.slice(0, this.state.cursorCol);
      this.killRing.push(deletedText, { prepend: true, accumulate: this.lastAction === "kill" });
      this.lastAction = "kill";
      this.state.lines[this.state.cursorLine] = currentLine.slice(this.state.cursorCol);
      this.setCursorCol(0);
    } else if (this.state.cursorLine > 0) {
      this.pushUndoSnapshot();
      this.killRing.push(`
`, { prepend: true, accumulate: this.lastAction === "kill" });
      this.lastAction = "kill";
      const previousLine = this.state.lines[this.state.cursorLine - 1] || "";
      this.state.lines[this.state.cursorLine - 1] = previousLine + currentLine;
      this.state.lines.splice(this.state.cursorLine, 1);
      this.state.cursorLine--;
      this.setCursorCol(previousLine.length);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  deleteToEndOfLine() {
    this.historyIndex = -1;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol < currentLine.length) {
      this.pushUndoSnapshot();
      const deletedText = currentLine.slice(this.state.cursorCol);
      this.killRing.push(deletedText, { prepend: false, accumulate: this.lastAction === "kill" });
      this.lastAction = "kill";
      this.state.lines[this.state.cursorLine] = currentLine.slice(0, this.state.cursorCol);
    } else if (this.state.cursorLine < this.state.lines.length - 1) {
      this.pushUndoSnapshot();
      this.killRing.push(`
`, { prepend: false, accumulate: this.lastAction === "kill" });
      this.lastAction = "kill";
      const nextLine = this.state.lines[this.state.cursorLine + 1] || "";
      this.state.lines[this.state.cursorLine] = currentLine + nextLine;
      this.state.lines.splice(this.state.cursorLine + 1, 1);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  deleteWordBackwards() {
    this.historyIndex = -1;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol === 0) {
      if (this.state.cursorLine > 0) {
        this.pushUndoSnapshot();
        this.killRing.push(`
`, { prepend: true, accumulate: this.lastAction === "kill" });
        this.lastAction = "kill";
        const previousLine = this.state.lines[this.state.cursorLine - 1] || "";
        this.state.lines[this.state.cursorLine - 1] = previousLine + currentLine;
        this.state.lines.splice(this.state.cursorLine, 1);
        this.state.cursorLine--;
        this.setCursorCol(previousLine.length);
      }
    } else {
      this.pushUndoSnapshot();
      const wasKill = this.lastAction === "kill";
      const oldCursorCol = this.state.cursorCol;
      this.moveWordBackwards();
      const deleteFrom = this.state.cursorCol;
      this.setCursorCol(oldCursorCol);
      const deletedText = currentLine.slice(deleteFrom, this.state.cursorCol);
      this.killRing.push(deletedText, { prepend: true, accumulate: wasKill });
      this.lastAction = "kill";
      this.state.lines[this.state.cursorLine] = currentLine.slice(0, deleteFrom) + currentLine.slice(this.state.cursorCol);
      this.setCursorCol(deleteFrom);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  deleteWordForward() {
    this.historyIndex = -1;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol >= currentLine.length) {
      if (this.state.cursorLine < this.state.lines.length - 1) {
        this.pushUndoSnapshot();
        this.killRing.push(`
`, { prepend: false, accumulate: this.lastAction === "kill" });
        this.lastAction = "kill";
        const nextLine = this.state.lines[this.state.cursorLine + 1] || "";
        this.state.lines[this.state.cursorLine] = currentLine + nextLine;
        this.state.lines.splice(this.state.cursorLine + 1, 1);
      }
    } else {
      this.pushUndoSnapshot();
      const wasKill = this.lastAction === "kill";
      const oldCursorCol = this.state.cursorCol;
      this.moveWordForwards();
      const deleteTo = this.state.cursorCol;
      this.setCursorCol(oldCursorCol);
      const deletedText = currentLine.slice(this.state.cursorCol, deleteTo);
      this.killRing.push(deletedText, { prepend: false, accumulate: wasKill });
      this.lastAction = "kill";
      this.state.lines[this.state.cursorLine] = currentLine.slice(0, this.state.cursorCol) + currentLine.slice(deleteTo);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  handleForwardDelete() {
    this.historyIndex = -1;
    this.lastAction = null;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol < currentLine.length) {
      this.pushUndoSnapshot();
      const afterCursor = currentLine.slice(this.state.cursorCol);
      const graphemes = [...this.segment(afterCursor)];
      const firstGrapheme = graphemes[0];
      const graphemeLength = firstGrapheme ? firstGrapheme.segment.length : 1;
      const before = currentLine.slice(0, this.state.cursorCol);
      const after = currentLine.slice(this.state.cursorCol + graphemeLength);
      this.state.lines[this.state.cursorLine] = before + after;
    } else if (this.state.cursorLine < this.state.lines.length - 1) {
      this.pushUndoSnapshot();
      const nextLine = this.state.lines[this.state.cursorLine + 1] || "";
      this.state.lines[this.state.cursorLine] = currentLine + nextLine;
      this.state.lines.splice(this.state.cursorLine + 1, 1);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
    if (this.autocompleteState) {
      this.updateAutocomplete();
    } else {
      const currentLine2 = this.state.lines[this.state.cursorLine] || "";
      const textBeforeCursor = currentLine2.slice(0, this.state.cursorCol);
      if (this.isInSlashCommandContext(textBeforeCursor)) {
        this.tryTriggerAutocomplete();
      } else if (textBeforeCursor.match(/(?:^|[\s])@[^\s]*$/)) {
        this.tryTriggerAutocomplete();
      }
    }
  }
  buildVisualLineMap(width) {
    const visualLines = [];
    for (let i = 0;i < this.state.lines.length; i++) {
      const line = this.state.lines[i] || "";
      const lineVisWidth = visibleWidth(line);
      if (line.length === 0) {
        visualLines.push({ logicalLine: i, startCol: 0, length: 0 });
      } else if (lineVisWidth <= width) {
        visualLines.push({ logicalLine: i, startCol: 0, length: line.length });
      } else {
        const chunks = wordWrapLine(line, width, [...this.segment(line)]);
        for (const chunk of chunks) {
          visualLines.push({
            logicalLine: i,
            startCol: chunk.startIndex,
            length: chunk.endIndex - chunk.startIndex
          });
        }
      }
    }
    return visualLines;
  }
  findCurrentVisualLine(visualLines) {
    for (let i = 0;i < visualLines.length; i++) {
      const vl = visualLines[i];
      if (!vl)
        continue;
      if (vl.logicalLine === this.state.cursorLine) {
        const colInSegment = this.state.cursorCol - vl.startCol;
        const isLastSegmentOfLine = i === visualLines.length - 1 || visualLines[i + 1]?.logicalLine !== vl.logicalLine;
        if (colInSegment >= 0 && (colInSegment < vl.length || isLastSegmentOfLine && colInSegment <= vl.length)) {
          return i;
        }
      }
    }
    return visualLines.length - 1;
  }
  moveCursor(deltaLine, deltaCol) {
    this.lastAction = null;
    const visualLines = this.buildVisualLineMap(this.lastWidth);
    const currentVisualLine = this.findCurrentVisualLine(visualLines);
    if (deltaLine !== 0) {
      const targetVisualLine = currentVisualLine + deltaLine;
      if (targetVisualLine >= 0 && targetVisualLine < visualLines.length) {
        this.moveToVisualLine(visualLines, currentVisualLine, targetVisualLine);
      }
    }
    if (deltaCol !== 0) {
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      if (deltaCol > 0) {
        if (this.state.cursorCol < currentLine.length) {
          const afterCursor = currentLine.slice(this.state.cursorCol);
          const graphemes = [...this.segment(afterCursor)];
          const firstGrapheme = graphemes[0];
          this.setCursorCol(this.state.cursorCol + (firstGrapheme ? firstGrapheme.segment.length : 1));
        } else if (this.state.cursorLine < this.state.lines.length - 1) {
          this.state.cursorLine++;
          this.setCursorCol(0);
        } else {
          const currentVL = visualLines[currentVisualLine];
          if (currentVL) {
            this.preferredVisualCol = this.state.cursorCol - currentVL.startCol;
          }
        }
      } else {
        if (this.state.cursorCol > 0) {
          const beforeCursor = currentLine.slice(0, this.state.cursorCol);
          const graphemes = [...this.segment(beforeCursor)];
          const lastGrapheme = graphemes[graphemes.length - 1];
          this.setCursorCol(this.state.cursorCol - (lastGrapheme ? lastGrapheme.segment.length : 1));
        } else if (this.state.cursorLine > 0) {
          this.state.cursorLine--;
          const prevLine = this.state.lines[this.state.cursorLine] || "";
          this.setCursorCol(prevLine.length);
        }
      }
    }
  }
  pageScroll(direction) {
    this.lastAction = null;
    const terminalRows = this.tui.terminal.rows;
    const pageSize = Math.max(5, Math.floor(terminalRows * 0.3));
    const visualLines = this.buildVisualLineMap(this.lastWidth);
    const currentVisualLine = this.findCurrentVisualLine(visualLines);
    const targetVisualLine = Math.max(0, Math.min(visualLines.length - 1, currentVisualLine + direction * pageSize));
    this.moveToVisualLine(visualLines, currentVisualLine, targetVisualLine);
  }
  moveWordBackwards() {
    this.lastAction = null;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol === 0) {
      if (this.state.cursorLine > 0) {
        this.state.cursorLine--;
        const prevLine = this.state.lines[this.state.cursorLine] || "";
        this.setCursorCol(prevLine.length);
      }
      return;
    }
    const textBeforeCursor = currentLine.slice(0, this.state.cursorCol);
    const graphemes = [...this.segment(textBeforeCursor)];
    let newCol = this.state.cursorCol;
    while (graphemes.length > 0 && !isPasteMarker(graphemes[graphemes.length - 1]?.segment || "") && isWhitespaceChar(graphemes[graphemes.length - 1]?.segment || "")) {
      newCol -= graphemes.pop()?.segment.length || 0;
    }
    if (graphemes.length > 0) {
      const lastGrapheme = graphemes[graphemes.length - 1]?.segment || "";
      if (isPasteMarker(lastGrapheme)) {
        newCol -= graphemes.pop()?.segment.length || 0;
      } else if (isPunctuationChar(lastGrapheme)) {
        while (graphemes.length > 0 && isPunctuationChar(graphemes[graphemes.length - 1]?.segment || "") && !isPasteMarker(graphemes[graphemes.length - 1]?.segment || "")) {
          newCol -= graphemes.pop()?.segment.length || 0;
        }
      } else {
        while (graphemes.length > 0 && !isWhitespaceChar(graphemes[graphemes.length - 1]?.segment || "") && !isPunctuationChar(graphemes[graphemes.length - 1]?.segment || "") && !isPasteMarker(graphemes[graphemes.length - 1]?.segment || "")) {
          newCol -= graphemes.pop()?.segment.length || 0;
        }
      }
    }
    this.setCursorCol(newCol);
  }
  yank() {
    if (this.killRing.length === 0)
      return;
    this.pushUndoSnapshot();
    const text = this.killRing.peek();
    this.insertYankedText(text);
    this.lastAction = "yank";
  }
  yankPop() {
    if (this.lastAction !== "yank" || this.killRing.length <= 1)
      return;
    this.pushUndoSnapshot();
    this.deleteYankedText();
    this.killRing.rotate();
    const text = this.killRing.peek();
    this.insertYankedText(text);
    this.lastAction = "yank";
  }
  insertYankedText(text) {
    this.historyIndex = -1;
    const lines = text.split(`
`);
    if (lines.length === 1) {
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      const before = currentLine.slice(0, this.state.cursorCol);
      const after = currentLine.slice(this.state.cursorCol);
      this.state.lines[this.state.cursorLine] = before + text + after;
      this.setCursorCol(this.state.cursorCol + text.length);
    } else {
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      const before = currentLine.slice(0, this.state.cursorCol);
      const after = currentLine.slice(this.state.cursorCol);
      this.state.lines[this.state.cursorLine] = before + (lines[0] || "");
      for (let i = 1;i < lines.length - 1; i++) {
        this.state.lines.splice(this.state.cursorLine + i, 0, lines[i] || "");
      }
      const lastLineIndex = this.state.cursorLine + lines.length - 1;
      this.state.lines.splice(lastLineIndex, 0, (lines[lines.length - 1] || "") + after);
      this.state.cursorLine = lastLineIndex;
      this.setCursorCol((lines[lines.length - 1] || "").length);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  deleteYankedText() {
    const yankedText = this.killRing.peek();
    if (!yankedText)
      return;
    const yankLines = yankedText.split(`
`);
    if (yankLines.length === 1) {
      const currentLine = this.state.lines[this.state.cursorLine] || "";
      const deleteLen = yankedText.length;
      const before = currentLine.slice(0, this.state.cursorCol - deleteLen);
      const after = currentLine.slice(this.state.cursorCol);
      this.state.lines[this.state.cursorLine] = before + after;
      this.setCursorCol(this.state.cursorCol - deleteLen);
    } else {
      const startLine = this.state.cursorLine - (yankLines.length - 1);
      const startCol = (this.state.lines[startLine] || "").length - (yankLines[0] || "").length;
      const afterCursor = (this.state.lines[this.state.cursorLine] || "").slice(this.state.cursorCol);
      const beforeYank = (this.state.lines[startLine] || "").slice(0, startCol);
      this.state.lines.splice(startLine, yankLines.length, beforeYank + afterCursor);
      this.state.cursorLine = startLine;
      this.setCursorCol(startCol);
    }
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  pushUndoSnapshot() {
    this.undoStack.push(this.state);
  }
  undo() {
    this.historyIndex = -1;
    const snapshot = this.undoStack.pop();
    if (!snapshot)
      return;
    Object.assign(this.state, snapshot);
    this.lastAction = null;
    this.preferredVisualCol = null;
    if (this.onChange) {
      this.onChange(this.getText());
    }
  }
  jumpToChar(char, direction) {
    this.lastAction = null;
    const isForward = direction === "forward";
    const lines = this.state.lines;
    const end = isForward ? lines.length : -1;
    const step = isForward ? 1 : -1;
    for (let lineIdx = this.state.cursorLine;lineIdx !== end; lineIdx += step) {
      const line = lines[lineIdx] || "";
      const isCurrentLine = lineIdx === this.state.cursorLine;
      const searchFrom = isCurrentLine ? isForward ? this.state.cursorCol + 1 : this.state.cursorCol - 1 : undefined;
      const idx = isForward ? line.indexOf(char, searchFrom) : line.lastIndexOf(char, searchFrom);
      if (idx !== -1) {
        this.state.cursorLine = lineIdx;
        this.setCursorCol(idx);
        return;
      }
    }
  }
  moveWordForwards() {
    this.lastAction = null;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    if (this.state.cursorCol >= currentLine.length) {
      if (this.state.cursorLine < this.state.lines.length - 1) {
        this.state.cursorLine++;
        this.setCursorCol(0);
      }
      return;
    }
    const textAfterCursor = currentLine.slice(this.state.cursorCol);
    const segments = this.segment(textAfterCursor);
    const iterator = segments[Symbol.iterator]();
    let next = iterator.next();
    let newCol = this.state.cursorCol;
    while (!next.done && !isPasteMarker(next.value.segment) && isWhitespaceChar(next.value.segment)) {
      newCol += next.value.segment.length;
      next = iterator.next();
    }
    if (!next.done) {
      const firstGrapheme = next.value.segment;
      if (isPasteMarker(firstGrapheme)) {
        newCol += firstGrapheme.length;
      } else if (isPunctuationChar(firstGrapheme)) {
        while (!next.done && isPunctuationChar(next.value.segment) && !isPasteMarker(next.value.segment)) {
          newCol += next.value.segment.length;
          next = iterator.next();
        }
      } else {
        while (!next.done && !isWhitespaceChar(next.value.segment) && !isPunctuationChar(next.value.segment) && !isPasteMarker(next.value.segment)) {
          newCol += next.value.segment.length;
          next = iterator.next();
        }
      }
    }
    this.setCursorCol(newCol);
  }
  isSlashMenuAllowed() {
    return this.state.cursorLine === 0;
  }
  isAtStartOfMessage() {
    if (!this.isSlashMenuAllowed())
      return false;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    const beforeCursor = currentLine.slice(0, this.state.cursorCol);
    return beforeCursor.trim() === "" || beforeCursor.trim() === "/";
  }
  isInSlashCommandContext(textBeforeCursor) {
    return this.isSlashMenuAllowed() && textBeforeCursor.trimStart().startsWith("/");
  }
  getBestAutocompleteMatchIndex(items, prefix) {
    if (!prefix)
      return -1;
    let firstPrefixIndex = -1;
    for (let i = 0;i < items.length; i++) {
      const value = items[i].value;
      if (value === prefix) {
        return i;
      }
      if (firstPrefixIndex === -1 && value.startsWith(prefix)) {
        firstPrefixIndex = i;
      }
    }
    return firstPrefixIndex;
  }
  createAutocompleteList(prefix, items) {
    const layout = prefix.startsWith("/") ? SLASH_COMMAND_SELECT_LIST_LAYOUT : undefined;
    return new SelectList(items, this.autocompleteMaxVisible, this.theme.selectList, layout);
  }
  tryTriggerAutocomplete(explicitTab = false) {
    this.requestAutocomplete({ force: false, explicitTab });
  }
  handleTabCompletion() {
    if (!this.autocompleteProvider)
      return;
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    const beforeCursor = currentLine.slice(0, this.state.cursorCol);
    if (this.isInSlashCommandContext(beforeCursor) && !beforeCursor.trimStart().includes(" ")) {
      this.handleSlashCommandCompletion();
    } else {
      this.forceFileAutocomplete(true);
    }
  }
  handleSlashCommandCompletion() {
    this.requestAutocomplete({ force: false, explicitTab: true });
  }
  forceFileAutocomplete(explicitTab = false) {
    this.requestAutocomplete({ force: true, explicitTab });
  }
  requestAutocomplete(options) {
    if (!this.autocompleteProvider)
      return;
    if (options.force) {
      const provider = this.autocompleteProvider;
      const shouldTrigger = !provider.shouldTriggerFileCompletion || provider.shouldTriggerFileCompletion(this.state.lines, this.state.cursorLine, this.state.cursorCol);
      if (!shouldTrigger) {
        return;
      }
    }
    this.cancelAutocompleteRequest();
    const startToken = ++this.autocompleteStartToken;
    const debounceMs = this.getAutocompleteDebounceMs(options);
    if (debounceMs > 0) {
      this.autocompleteDebounceTimer = setTimeout(() => {
        this.autocompleteDebounceTimer = undefined;
        this.startAutocompleteRequest(startToken, options);
      }, debounceMs);
      return;
    }
    this.startAutocompleteRequest(startToken, options);
  }
  async startAutocompleteRequest(startToken, options) {
    const previousTask = this.autocompleteRequestTask;
    this.autocompleteRequestTask = (async () => {
      await previousTask;
      if (startToken !== this.autocompleteStartToken || !this.autocompleteProvider) {
        return;
      }
      const controller = new AbortController;
      this.autocompleteAbort = controller;
      const requestId = ++this.autocompleteRequestId;
      const snapshotText = this.getText();
      const snapshotLine = this.state.cursorLine;
      const snapshotCol = this.state.cursorCol;
      await this.runAutocompleteRequest(requestId, controller, snapshotText, snapshotLine, snapshotCol, options);
    })();
    await this.autocompleteRequestTask;
  }
  getAutocompleteDebounceMs(options) {
    if (options.explicitTab || options.force) {
      return 0;
    }
    const currentLine = this.state.lines[this.state.cursorLine] || "";
    const textBeforeCursor = currentLine.slice(0, this.state.cursorCol);
    const isAttachmentContext = /(?:^|[ \t])@(?:"[^"]*|[^\s]*)$/.test(textBeforeCursor);
    return isAttachmentContext ? ATTACHMENT_AUTOCOMPLETE_DEBOUNCE_MS : 0;
  }
  async runAutocompleteRequest(requestId, controller, snapshotText, snapshotLine, snapshotCol, options) {
    if (!this.autocompleteProvider)
      return;
    const suggestions = await this.autocompleteProvider.getSuggestions(this.state.lines, this.state.cursorLine, this.state.cursorCol, { signal: controller.signal, force: options.force });
    if (!this.isAutocompleteRequestCurrent(requestId, controller, snapshotText, snapshotLine, snapshotCol)) {
      return;
    }
    this.autocompleteAbort = undefined;
    if (!suggestions || !Array.isArray(suggestions.items) || suggestions.items.length === 0) {
      this.cancelAutocomplete();
      this.tui.requestRender();
      return;
    }
    if (options.force && options.explicitTab && suggestions.items.length === 1) {
      const item = suggestions.items[0];
      this.pushUndoSnapshot();
      this.lastAction = null;
      const result = this.autocompleteProvider.applyCompletion(this.state.lines, this.state.cursorLine, this.state.cursorCol, item, suggestions.prefix);
      this.state.lines = result.lines;
      this.state.cursorLine = result.cursorLine;
      this.setCursorCol(result.cursorCol);
      if (this.onChange)
        this.onChange(this.getText());
      this.tui.requestRender();
      return;
    }
    this.applyAutocompleteSuggestions(suggestions, options.force ? "force" : "regular");
    this.tui.requestRender();
  }
  isAutocompleteRequestCurrent(requestId, controller, snapshotText, snapshotLine, snapshotCol) {
    return !controller.signal.aborted && requestId === this.autocompleteRequestId && this.getText() === snapshotText && this.state.cursorLine === snapshotLine && this.state.cursorCol === snapshotCol;
  }
  applyAutocompleteSuggestions(suggestions, state) {
    this.autocompletePrefix = suggestions.prefix;
    this.autocompleteList = this.createAutocompleteList(suggestions.prefix, suggestions.items);
    const bestMatchIndex = this.getBestAutocompleteMatchIndex(suggestions.items, suggestions.prefix);
    if (bestMatchIndex >= 0) {
      this.autocompleteList.setSelectedIndex(bestMatchIndex);
    }
    this.autocompleteState = state;
  }
  cancelAutocompleteRequest() {
    this.autocompleteStartToken += 1;
    if (this.autocompleteDebounceTimer) {
      clearTimeout(this.autocompleteDebounceTimer);
      this.autocompleteDebounceTimer = undefined;
    }
    this.autocompleteAbort?.abort();
    this.autocompleteAbort = undefined;
  }
  clearAutocompleteUi() {
    this.autocompleteState = null;
    this.autocompleteList = undefined;
    this.autocompletePrefix = "";
  }
  cancelAutocomplete() {
    this.cancelAutocompleteRequest();
    this.clearAutocompleteUi();
  }
  isShowingAutocomplete() {
    return this.autocompleteState !== null;
  }
  updateAutocomplete() {
    if (!this.autocompleteState || !this.autocompleteProvider)
      return;
    this.requestAutocomplete({ force: this.autocompleteState === "force", explicitTab: false });
  }
}
// node_modules/@mariozechner/pi-tui/dist/components/input.js
var segmenter2 = getSegmenter();

class Input {
  value = "";
  cursor = 0;
  onSubmit;
  onEscape;
  focused = false;
  pasteBuffer = "";
  isInPaste = false;
  killRing = new KillRing;
  lastAction = null;
  undoStack = new UndoStack;
  getValue() {
    return this.value;
  }
  setValue(value) {
    this.value = value;
    this.cursor = Math.min(this.cursor, value.length);
  }
  handleInput(data) {
    if (data.includes("\x1B[200~")) {
      this.isInPaste = true;
      this.pasteBuffer = "";
      data = data.replace("\x1B[200~", "");
    }
    if (this.isInPaste) {
      this.pasteBuffer += data;
      const endIndex = this.pasteBuffer.indexOf("\x1B[201~");
      if (endIndex !== -1) {
        const pasteContent = this.pasteBuffer.substring(0, endIndex);
        this.handlePaste(pasteContent);
        this.isInPaste = false;
        const remaining = this.pasteBuffer.substring(endIndex + 6);
        this.pasteBuffer = "";
        if (remaining) {
          this.handleInput(remaining);
        }
      }
      return;
    }
    const kb = getKeybindings();
    if (kb.matches(data, "tui.select.cancel")) {
      if (this.onEscape)
        this.onEscape();
      return;
    }
    if (kb.matches(data, "tui.editor.undo")) {
      this.undo();
      return;
    }
    if (kb.matches(data, "tui.input.submit") || data === `
`) {
      if (this.onSubmit)
        this.onSubmit(this.value);
      return;
    }
    if (kb.matches(data, "tui.editor.deleteCharBackward")) {
      this.handleBackspace();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteCharForward")) {
      this.handleForwardDelete();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteWordBackward")) {
      this.deleteWordBackwards();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteWordForward")) {
      this.deleteWordForward();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteToLineStart")) {
      this.deleteToLineStart();
      return;
    }
    if (kb.matches(data, "tui.editor.deleteToLineEnd")) {
      this.deleteToLineEnd();
      return;
    }
    if (kb.matches(data, "tui.editor.yank")) {
      this.yank();
      return;
    }
    if (kb.matches(data, "tui.editor.yankPop")) {
      this.yankPop();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorLeft")) {
      this.lastAction = null;
      if (this.cursor > 0) {
        const beforeCursor = this.value.slice(0, this.cursor);
        const graphemes = [...segmenter2.segment(beforeCursor)];
        const lastGrapheme = graphemes[graphemes.length - 1];
        this.cursor -= lastGrapheme ? lastGrapheme.segment.length : 1;
      }
      return;
    }
    if (kb.matches(data, "tui.editor.cursorRight")) {
      this.lastAction = null;
      if (this.cursor < this.value.length) {
        const afterCursor = this.value.slice(this.cursor);
        const graphemes = [...segmenter2.segment(afterCursor)];
        const firstGrapheme = graphemes[0];
        this.cursor += firstGrapheme ? firstGrapheme.segment.length : 1;
      }
      return;
    }
    if (kb.matches(data, "tui.editor.cursorLineStart")) {
      this.lastAction = null;
      this.cursor = 0;
      return;
    }
    if (kb.matches(data, "tui.editor.cursorLineEnd")) {
      this.lastAction = null;
      this.cursor = this.value.length;
      return;
    }
    if (kb.matches(data, "tui.editor.cursorWordLeft")) {
      this.moveWordBackwards();
      return;
    }
    if (kb.matches(data, "tui.editor.cursorWordRight")) {
      this.moveWordForwards();
      return;
    }
    const kittyPrintable = decodeKittyPrintable(data);
    if (kittyPrintable !== undefined) {
      this.insertCharacter(kittyPrintable);
      return;
    }
    const hasControlChars = [...data].some((ch) => {
      const code = ch.charCodeAt(0);
      return code < 32 || code === 127 || code >= 128 && code <= 159;
    });
    if (!hasControlChars) {
      this.insertCharacter(data);
    }
  }
  insertCharacter(char) {
    if (isWhitespaceChar(char) || this.lastAction !== "type-word") {
      this.pushUndo();
    }
    this.lastAction = "type-word";
    this.value = this.value.slice(0, this.cursor) + char + this.value.slice(this.cursor);
    this.cursor += char.length;
  }
  handleBackspace() {
    this.lastAction = null;
    if (this.cursor > 0) {
      this.pushUndo();
      const beforeCursor = this.value.slice(0, this.cursor);
      const graphemes = [...segmenter2.segment(beforeCursor)];
      const lastGrapheme = graphemes[graphemes.length - 1];
      const graphemeLength = lastGrapheme ? lastGrapheme.segment.length : 1;
      this.value = this.value.slice(0, this.cursor - graphemeLength) + this.value.slice(this.cursor);
      this.cursor -= graphemeLength;
    }
  }
  handleForwardDelete() {
    this.lastAction = null;
    if (this.cursor < this.value.length) {
      this.pushUndo();
      const afterCursor = this.value.slice(this.cursor);
      const graphemes = [...segmenter2.segment(afterCursor)];
      const firstGrapheme = graphemes[0];
      const graphemeLength = firstGrapheme ? firstGrapheme.segment.length : 1;
      this.value = this.value.slice(0, this.cursor) + this.value.slice(this.cursor + graphemeLength);
    }
  }
  deleteToLineStart() {
    if (this.cursor === 0)
      return;
    this.pushUndo();
    const deletedText = this.value.slice(0, this.cursor);
    this.killRing.push(deletedText, { prepend: true, accumulate: this.lastAction === "kill" });
    this.lastAction = "kill";
    this.value = this.value.slice(this.cursor);
    this.cursor = 0;
  }
  deleteToLineEnd() {
    if (this.cursor >= this.value.length)
      return;
    this.pushUndo();
    const deletedText = this.value.slice(this.cursor);
    this.killRing.push(deletedText, { prepend: false, accumulate: this.lastAction === "kill" });
    this.lastAction = "kill";
    this.value = this.value.slice(0, this.cursor);
  }
  deleteWordBackwards() {
    if (this.cursor === 0)
      return;
    const wasKill = this.lastAction === "kill";
    this.pushUndo();
    const oldCursor = this.cursor;
    this.moveWordBackwards();
    const deleteFrom = this.cursor;
    this.cursor = oldCursor;
    const deletedText = this.value.slice(deleteFrom, this.cursor);
    this.killRing.push(deletedText, { prepend: true, accumulate: wasKill });
    this.lastAction = "kill";
    this.value = this.value.slice(0, deleteFrom) + this.value.slice(this.cursor);
    this.cursor = deleteFrom;
  }
  deleteWordForward() {
    if (this.cursor >= this.value.length)
      return;
    const wasKill = this.lastAction === "kill";
    this.pushUndo();
    const oldCursor = this.cursor;
    this.moveWordForwards();
    const deleteTo = this.cursor;
    this.cursor = oldCursor;
    const deletedText = this.value.slice(this.cursor, deleteTo);
    this.killRing.push(deletedText, { prepend: false, accumulate: wasKill });
    this.lastAction = "kill";
    this.value = this.value.slice(0, this.cursor) + this.value.slice(deleteTo);
  }
  yank() {
    const text = this.killRing.peek();
    if (!text)
      return;
    this.pushUndo();
    this.value = this.value.slice(0, this.cursor) + text + this.value.slice(this.cursor);
    this.cursor += text.length;
    this.lastAction = "yank";
  }
  yankPop() {
    if (this.lastAction !== "yank" || this.killRing.length <= 1)
      return;
    this.pushUndo();
    const prevText = this.killRing.peek() || "";
    this.value = this.value.slice(0, this.cursor - prevText.length) + this.value.slice(this.cursor);
    this.cursor -= prevText.length;
    this.killRing.rotate();
    const text = this.killRing.peek() || "";
    this.value = this.value.slice(0, this.cursor) + text + this.value.slice(this.cursor);
    this.cursor += text.length;
    this.lastAction = "yank";
  }
  pushUndo() {
    this.undoStack.push({ value: this.value, cursor: this.cursor });
  }
  undo() {
    const snapshot = this.undoStack.pop();
    if (!snapshot)
      return;
    this.value = snapshot.value;
    this.cursor = snapshot.cursor;
    this.lastAction = null;
  }
  moveWordBackwards() {
    if (this.cursor === 0) {
      return;
    }
    this.lastAction = null;
    const textBeforeCursor = this.value.slice(0, this.cursor);
    const graphemes = [...segmenter2.segment(textBeforeCursor)];
    while (graphemes.length > 0 && isWhitespaceChar(graphemes[graphemes.length - 1]?.segment || "")) {
      this.cursor -= graphemes.pop()?.segment.length || 0;
    }
    if (graphemes.length > 0) {
      const lastGrapheme = graphemes[graphemes.length - 1]?.segment || "";
      if (isPunctuationChar(lastGrapheme)) {
        while (graphemes.length > 0 && isPunctuationChar(graphemes[graphemes.length - 1]?.segment || "")) {
          this.cursor -= graphemes.pop()?.segment.length || 0;
        }
      } else {
        while (graphemes.length > 0 && !isWhitespaceChar(graphemes[graphemes.length - 1]?.segment || "") && !isPunctuationChar(graphemes[graphemes.length - 1]?.segment || "")) {
          this.cursor -= graphemes.pop()?.segment.length || 0;
        }
      }
    }
  }
  moveWordForwards() {
    if (this.cursor >= this.value.length) {
      return;
    }
    this.lastAction = null;
    const textAfterCursor = this.value.slice(this.cursor);
    const segments = segmenter2.segment(textAfterCursor);
    const iterator = segments[Symbol.iterator]();
    let next = iterator.next();
    while (!next.done && isWhitespaceChar(next.value.segment)) {
      this.cursor += next.value.segment.length;
      next = iterator.next();
    }
    if (!next.done) {
      const firstGrapheme = next.value.segment;
      if (isPunctuationChar(firstGrapheme)) {
        while (!next.done && isPunctuationChar(next.value.segment)) {
          this.cursor += next.value.segment.length;
          next = iterator.next();
        }
      } else {
        while (!next.done && !isWhitespaceChar(next.value.segment) && !isPunctuationChar(next.value.segment)) {
          this.cursor += next.value.segment.length;
          next = iterator.next();
        }
      }
    }
  }
  handlePaste(pastedText) {
    this.lastAction = null;
    this.pushUndo();
    const cleanText = pastedText.replace(/\r\n/g, "").replace(/\r/g, "").replace(/\n/g, "").replace(/\t/g, "    ");
    this.value = this.value.slice(0, this.cursor) + cleanText + this.value.slice(this.cursor);
    this.cursor += cleanText.length;
  }
  invalidate() {}
  render(width) {
    const prompt = "> ";
    const availableWidth = width - prompt.length;
    if (availableWidth <= 0) {
      return [prompt];
    }
    let visibleText = "";
    let cursorDisplay = this.cursor;
    const totalWidth = visibleWidth(this.value);
    if (totalWidth < availableWidth) {
      visibleText = this.value;
    } else {
      const scrollWidth = this.cursor === this.value.length ? availableWidth - 1 : availableWidth;
      const cursorCol = visibleWidth(this.value.slice(0, this.cursor));
      if (scrollWidth > 0) {
        const halfWidth = Math.floor(scrollWidth / 2);
        let startCol = 0;
        if (cursorCol < halfWidth) {
          startCol = 0;
        } else if (cursorCol > totalWidth - halfWidth) {
          startCol = Math.max(0, totalWidth - scrollWidth);
        } else {
          startCol = Math.max(0, cursorCol - halfWidth);
        }
        visibleText = sliceByColumn(this.value, startCol, scrollWidth, true);
        const beforeCursor2 = sliceByColumn(this.value, startCol, Math.max(0, cursorCol - startCol), true);
        cursorDisplay = beforeCursor2.length;
      } else {
        visibleText = "";
        cursorDisplay = 0;
      }
    }
    const graphemes = [...segmenter2.segment(visibleText.slice(cursorDisplay))];
    const cursorGrapheme = graphemes[0];
    const beforeCursor = visibleText.slice(0, cursorDisplay);
    const atCursor = cursorGrapheme?.segment ?? " ";
    const afterCursor = visibleText.slice(cursorDisplay + atCursor.length);
    const marker = this.focused ? CURSOR_MARKER : "";
    const cursorChar = `\x1B[7m${atCursor}\x1B[27m`;
    const textWithCursor = beforeCursor + marker + cursorChar + afterCursor;
    const visualLength = visibleWidth(textWithCursor);
    const padding = " ".repeat(Math.max(0, availableWidth - visualLength));
    const line = prompt + textWithCursor + padding;
    return [line];
  }
}
// node_modules/marked/lib/marked.esm.js
function _getDefaults() {
  return {
    async: false,
    breaks: false,
    extensions: null,
    gfm: true,
    hooks: null,
    pedantic: false,
    renderer: null,
    silent: false,
    tokenizer: null,
    walkTokens: null
  };
}
var _defaults = _getDefaults();
function changeDefaults(newDefaults) {
  _defaults = newDefaults;
}
var noopTest = { exec: () => null };
function edit(regex, opt = "") {
  let source = typeof regex === "string" ? regex : regex.source;
  const obj = {
    replace: (name, val) => {
      let valSource = typeof val === "string" ? val : val.source;
      valSource = valSource.replace(other.caret, "$1");
      source = source.replace(name, valSource);
      return obj;
    },
    getRegex: () => {
      return new RegExp(source, opt);
    }
  };
  return obj;
}
var other = {
  codeRemoveIndent: /^(?: {1,4}| {0,3}\t)/gm,
  outputLinkReplace: /\\([\[\]])/g,
  indentCodeCompensation: /^(\s+)(?:```)/,
  beginningSpace: /^\s+/,
  endingHash: /#$/,
  startingSpaceChar: /^ /,
  endingSpaceChar: / $/,
  nonSpaceChar: /[^ ]/,
  newLineCharGlobal: /\n/g,
  tabCharGlobal: /\t/g,
  multipleSpaceGlobal: /\s+/g,
  blankLine: /^[ \t]*$/,
  doubleBlankLine: /\n[ \t]*\n[ \t]*$/,
  blockquoteStart: /^ {0,3}>/,
  blockquoteSetextReplace: /\n {0,3}((?:=+|-+) *)(?=\n|$)/g,
  blockquoteSetextReplace2: /^ {0,3}>[ \t]?/gm,
  listReplaceTabs: /^\t+/,
  listReplaceNesting: /^ {1,4}(?=( {4})*[^ ])/g,
  listIsTask: /^\[[ xX]\] /,
  listReplaceTask: /^\[[ xX]\] +/,
  anyLine: /\n.*\n/,
  hrefBrackets: /^<(.*)>$/,
  tableDelimiter: /[:|]/,
  tableAlignChars: /^\||\| *$/g,
  tableRowBlankLine: /\n[ \t]*$/,
  tableAlignRight: /^ *-+: *$/,
  tableAlignCenter: /^ *:-+: *$/,
  tableAlignLeft: /^ *:-+ *$/,
  startATag: /^<a /i,
  endATag: /^<\/a>/i,
  startPreScriptTag: /^<(pre|code|kbd|script)(\s|>)/i,
  endPreScriptTag: /^<\/(pre|code|kbd|script)(\s|>)/i,
  startAngleBracket: /^</,
  endAngleBracket: />$/,
  pedanticHrefTitle: /^([^'"]*[^\s])\s+(['"])(.*)\2/,
  unicodeAlphaNumeric: /[\p{L}\p{N}]/u,
  escapeTest: /[&<>"']/,
  escapeReplace: /[&<>"']/g,
  escapeTestNoEncode: /[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/,
  escapeReplaceNoEncode: /[<>"']|&(?!(#\d{1,7}|#[Xx][a-fA-F0-9]{1,6}|\w+);)/g,
  unescapeTest: /&(#(?:\d+)|(?:#x[0-9A-Fa-f]+)|(?:\w+));?/ig,
  caret: /(^|[^\[])\^/g,
  percentDecode: /%25/g,
  findPipe: /\|/g,
  splitPipe: / \|/,
  slashPipe: /\\\|/g,
  carriageReturn: /\r\n|\r/g,
  spaceLine: /^ +$/gm,
  notSpaceStart: /^\S*/,
  endingNewline: /\n$/,
  listItemRegex: (bull) => new RegExp(`^( {0,3}${bull})((?:[	 ][^\\n]*)?(?:\\n|$))`),
  nextBulletRegex: (indent) => new RegExp(`^ {0,${Math.min(3, indent - 1)}}(?:[*+-]|\\d{1,9}[.)])((?:[ 	][^\\n]*)?(?:\\n|$))`),
  hrRegex: (indent) => new RegExp(`^ {0,${Math.min(3, indent - 1)}}((?:- *){3,}|(?:_ *){3,}|(?:\\* *){3,})(?:\\n+|$)`),
  fencesBeginRegex: (indent) => new RegExp(`^ {0,${Math.min(3, indent - 1)}}(?:\`\`\`|~~~)`),
  headingBeginRegex: (indent) => new RegExp(`^ {0,${Math.min(3, indent - 1)}}#`),
  htmlBeginRegex: (indent) => new RegExp(`^ {0,${Math.min(3, indent - 1)}}<(?:[a-z].*>|!--)`, "i")
};
var newline = /^(?:[ \t]*(?:\n|$))+/;
var blockCode = /^((?: {4}| {0,3}\t)[^\n]+(?:\n(?:[ \t]*(?:\n|$))*)?)+/;
var fences = /^ {0,3}(`{3,}(?=[^`\n]*(?:\n|$))|~{3,})([^\n]*)(?:\n|$)(?:|([\s\S]*?)(?:\n|$))(?: {0,3}\1[~`]* *(?=\n|$)|$)/;
var hr = /^ {0,3}((?:-[\t ]*){3,}|(?:_[ \t]*){3,}|(?:\*[ \t]*){3,})(?:\n+|$)/;
var heading = /^ {0,3}(#{1,6})(?=\s|$)(.*)(?:\n+|$)/;
var bullet = /(?:[*+-]|\d{1,9}[.)])/;
var lheadingCore = /^(?!bull |blockCode|fences|blockquote|heading|html|table)((?:.|\n(?!\s*?\n|bull |blockCode|fences|blockquote|heading|html|table))+?)\n {0,3}(=+|-+) *(?:\n+|$)/;
var lheading = edit(lheadingCore).replace(/bull/g, bullet).replace(/blockCode/g, /(?: {4}| {0,3}\t)/).replace(/fences/g, / {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g, / {0,3}>/).replace(/heading/g, / {0,3}#{1,6}/).replace(/html/g, / {0,3}<[^\n>]+>\n/).replace(/\|table/g, "").getRegex();
var lheadingGfm = edit(lheadingCore).replace(/bull/g, bullet).replace(/blockCode/g, /(?: {4}| {0,3}\t)/).replace(/fences/g, / {0,3}(?:`{3,}|~{3,})/).replace(/blockquote/g, / {0,3}>/).replace(/heading/g, / {0,3}#{1,6}/).replace(/html/g, / {0,3}<[^\n>]+>\n/).replace(/table/g, / {0,3}\|?(?:[:\- ]*\|)+[\:\- ]*\n/).getRegex();
var _paragraph = /^([^\n]+(?:\n(?!hr|heading|lheading|blockquote|fences|list|html|table| +\n)[^\n]+)*)/;
var blockText = /^[^\n]+/;
var _blockLabel = /(?!\s*\])(?:\\.|[^\[\]\\])+/;
var def = edit(/^ {0,3}\[(label)\]: *(?:\n[ \t]*)?([^<\s][^\s]*|<.*?>)(?:(?: +(?:\n[ \t]*)?| *\n[ \t]*)(title))? *(?:\n+|$)/).replace("label", _blockLabel).replace("title", /(?:"(?:\\"?|[^"\\])*"|'[^'\n]*(?:\n[^'\n]+)*\n?'|\([^()]*\))/).getRegex();
var list = edit(/^( {0,3}bull)([ \t][^\n]+?)?(?:\n|$)/).replace(/bull/g, bullet).getRegex();
var _tag = "address|article|aside|base|basefont|blockquote|body|caption|center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|legend|li|link|main|menu|menuitem|meta|nav|noframes|ol|optgroup|option|p|param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|track|ul";
var _comment = /<!--(?:-?>|[\s\S]*?(?:-->|$))/;
var html = edit("^ {0,3}(?:<(script|pre|style|textarea)[\\s>][\\s\\S]*?(?:</\\1>[^\\n]*\\n+|$)|comment[^\\n]*(\\n+|$)|<\\?[\\s\\S]*?(?:\\?>\\n*|$)|<![A-Z][\\s\\S]*?(?:>\\n*|$)|<!\\[CDATA\\[[\\s\\S]*?(?:\\]\\]>\\n*|$)|</?(tag)(?: +|\\n|/?>)[\\s\\S]*?(?:(?:\\n[ \t]*)+\\n|$)|<(?!script|pre|style|textarea)([a-z][\\w-]*)(?:attribute)*? */?>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ \t]*)+\\n|$)|</(?!script|pre|style|textarea)[a-z][\\w-]*\\s*>(?=[ \\t]*(?:\\n|$))[\\s\\S]*?(?:(?:\\n[ 	]*)+\\n|$))", "i").replace("comment", _comment).replace("tag", _tag).replace("attribute", / +[a-zA-Z:_][\w.:-]*(?: *= *"[^"\n]*"| *= *'[^'\n]*'| *= *[^\s"'=<>`]+)?/).getRegex();
var paragraph = edit(_paragraph).replace("hr", hr).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("|lheading", "").replace("|table", "").replace("blockquote", " {0,3}>").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list", " {0,3}(?:[*+-]|1[.)]) ").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", _tag).getRegex();
var blockquote = edit(/^( {0,3}> ?(paragraph|[^\n]*)(?:\n|$))+/).replace("paragraph", paragraph).getRegex();
var blockNormal = {
  blockquote,
  code: blockCode,
  def,
  fences,
  heading,
  hr,
  html,
  lheading,
  list,
  newline,
  paragraph,
  table: noopTest,
  text: blockText
};
var gfmTable = edit("^ *([^\\n ].*)\\n {0,3}((?:\\| *)?:?-+:? *(?:\\| *:?-+:? *)*(?:\\| *)?)(?:\\n((?:(?! *\\n|hr|heading|blockquote|code|fences|list|html).*(?:\\n|$))*)\\n*|$)").replace("hr", hr).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("blockquote", " {0,3}>").replace("code", "(?: {4}| {0,3}\t)[^\\n]").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list", " {0,3}(?:[*+-]|1[.)]) ").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", _tag).getRegex();
var blockGfm = {
  ...blockNormal,
  lheading: lheadingGfm,
  table: gfmTable,
  paragraph: edit(_paragraph).replace("hr", hr).replace("heading", " {0,3}#{1,6}(?:\\s|$)").replace("|lheading", "").replace("table", gfmTable).replace("blockquote", " {0,3}>").replace("fences", " {0,3}(?:`{3,}(?=[^`\\n]*\\n)|~{3,})[^\\n]*\\n").replace("list", " {0,3}(?:[*+-]|1[.)]) ").replace("html", "</?(?:tag)(?: +|\\n|/?>)|<(?:script|pre|style|textarea|!--)").replace("tag", _tag).getRegex()
};
var blockPedantic = {
  ...blockNormal,
  html: edit(`^ *(?:comment *(?:\\n|\\s*$)|<(tag)[\\s\\S]+?</\\1> *(?:\\n{2,}|\\s*$)|<tag(?:"[^"]*"|'[^']*'|\\s[^'"/>\\s]*)*?/?> *(?:\\n{2,}|\\s*$))`).replace("comment", _comment).replace(/tag/g, "(?!(?:a|em|strong|small|s|cite|q|dfn|abbr|data|time|code|var|samp|kbd|sub|sup|i|b|u|mark|ruby|rt|rp|bdi|bdo|span|br|wbr|ins|del|img)\\b)\\w+(?!:|[^\\w\\s@]*@)\\b").getRegex(),
  def: /^ *\[([^\]]+)\]: *<?([^\s>]+)>?(?: +(["(][^\n]+[")]))? *(?:\n+|$)/,
  heading: /^(#{1,6})(.*)(?:\n+|$)/,
  fences: noopTest,
  lheading: /^(.+?)\n {0,3}(=+|-+) *(?:\n+|$)/,
  paragraph: edit(_paragraph).replace("hr", hr).replace("heading", ` *#{1,6} *[^
]`).replace("lheading", lheading).replace("|table", "").replace("blockquote", " {0,3}>").replace("|fences", "").replace("|list", "").replace("|html", "").replace("|tag", "").getRegex()
};
var escape = /^\\([!"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])/;
var inlineCode = /^(`+)([^`]|[^`][\s\S]*?[^`])\1(?!`)/;
var br = /^( {2,}|\\)\n(?!\s*$)/;
var inlineText = /^(`+|[^`])(?:(?= {2,}\n)|[\s\S]*?(?:(?=[\\<!\[`*_]|\b_|$)|[^ ](?= {2,}\n)))/;
var _punctuation = /[\p{P}\p{S}]/u;
var _punctuationOrSpace = /[\s\p{P}\p{S}]/u;
var _notPunctuationOrSpace = /[^\s\p{P}\p{S}]/u;
var punctuation = edit(/^((?![*_])punctSpace)/, "u").replace(/punctSpace/g, _punctuationOrSpace).getRegex();
var _punctuationGfmStrongEm = /(?!~)[\p{P}\p{S}]/u;
var _punctuationOrSpaceGfmStrongEm = /(?!~)[\s\p{P}\p{S}]/u;
var _notPunctuationOrSpaceGfmStrongEm = /(?:[^\s\p{P}\p{S}]|~)/u;
var blockSkip = /\[[^[\]]*?\]\((?:\\.|[^\\\(\)]|\((?:\\.|[^\\\(\)])*\))*\)|`[^`]*?`|<[^<>]*?>/g;
var emStrongLDelimCore = /^(?:\*+(?:((?!\*)punct)|[^\s*]))|^_+(?:((?!_)punct)|([^\s_]))/;
var emStrongLDelim = edit(emStrongLDelimCore, "u").replace(/punct/g, _punctuation).getRegex();
var emStrongLDelimGfm = edit(emStrongLDelimCore, "u").replace(/punct/g, _punctuationGfmStrongEm).getRegex();
var emStrongRDelimAstCore = "^[^_*]*?__[^_*]*?\\*[^_*]*?(?=__)|[^*]+(?=[^*])|(?!\\*)punct(\\*+)(?=[\\s]|$)|notPunctSpace(\\*+)(?!\\*)(?=punctSpace|$)|(?!\\*)punctSpace(\\*+)(?=notPunctSpace)|[\\s](\\*+)(?!\\*)(?=punct)|(?!\\*)punct(\\*+)(?!\\*)(?=punct)|notPunctSpace(\\*+)(?=notPunctSpace)";
var emStrongRDelimAst = edit(emStrongRDelimAstCore, "gu").replace(/notPunctSpace/g, _notPunctuationOrSpace).replace(/punctSpace/g, _punctuationOrSpace).replace(/punct/g, _punctuation).getRegex();
var emStrongRDelimAstGfm = edit(emStrongRDelimAstCore, "gu").replace(/notPunctSpace/g, _notPunctuationOrSpaceGfmStrongEm).replace(/punctSpace/g, _punctuationOrSpaceGfmStrongEm).replace(/punct/g, _punctuationGfmStrongEm).getRegex();
var emStrongRDelimUnd = edit("^[^_*]*?\\*\\*[^_*]*?_[^_*]*?(?=\\*\\*)|[^_]+(?=[^_])|(?!_)punct(_+)(?=[\\s]|$)|notPunctSpace(_+)(?!_)(?=punctSpace|$)|(?!_)punctSpace(_+)(?=notPunctSpace)|[\\s](_+)(?!_)(?=punct)|(?!_)punct(_+)(?!_)(?=punct)", "gu").replace(/notPunctSpace/g, _notPunctuationOrSpace).replace(/punctSpace/g, _punctuationOrSpace).replace(/punct/g, _punctuation).getRegex();
var anyPunctuation = edit(/\\(punct)/, "gu").replace(/punct/g, _punctuation).getRegex();
var autolink = edit(/^<(scheme:[^\s\x00-\x1f<>]*|email)>/).replace("scheme", /[a-zA-Z][a-zA-Z0-9+.-]{1,31}/).replace("email", /[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+(@)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+(?![-_])/).getRegex();
var _inlineComment = edit(_comment).replace("(?:-->|$)", "-->").getRegex();
var tag = edit("^comment|^</[a-zA-Z][\\w:-]*\\s*>|^<[a-zA-Z][\\w-]*(?:attribute)*?\\s*/?>|^<\\?[\\s\\S]*?\\?>|^<![a-zA-Z]+\\s[\\s\\S]*?>|^<!\\[CDATA\\[[\\s\\S]*?\\]\\]>").replace("comment", _inlineComment).replace("attribute", /\s+[a-zA-Z:_][\w.:-]*(?:\s*=\s*"[^"]*"|\s*=\s*'[^']*'|\s*=\s*[^\s"'=<>`]+)?/).getRegex();
var _inlineLabel = /(?:\[(?:\\.|[^\[\]\\])*\]|\\.|`[^`]*`|[^\[\]\\`])*?/;
var link = edit(/^!?\[(label)\]\(\s*(href)(?:(?:[ \t]*(?:\n[ \t]*)?)(title))?\s*\)/).replace("label", _inlineLabel).replace("href", /<(?:\\.|[^\n<>\\])+>|[^ \t\n\x00-\x1f]*/).replace("title", /"(?:\\"?|[^"\\])*"|'(?:\\'?|[^'\\])*'|\((?:\\\)?|[^)\\])*\)/).getRegex();
var reflink = edit(/^!?\[(label)\]\[(ref)\]/).replace("label", _inlineLabel).replace("ref", _blockLabel).getRegex();
var nolink = edit(/^!?\[(ref)\](?:\[\])?/).replace("ref", _blockLabel).getRegex();
var reflinkSearch = edit("reflink|nolink(?!\\()", "g").replace("reflink", reflink).replace("nolink", nolink).getRegex();
var inlineNormal = {
  _backpedal: noopTest,
  anyPunctuation,
  autolink,
  blockSkip,
  br,
  code: inlineCode,
  del: noopTest,
  emStrongLDelim,
  emStrongRDelimAst,
  emStrongRDelimUnd,
  escape,
  link,
  nolink,
  punctuation,
  reflink,
  reflinkSearch,
  tag,
  text: inlineText,
  url: noopTest
};
var inlinePedantic = {
  ...inlineNormal,
  link: edit(/^!?\[(label)\]\((.*?)\)/).replace("label", _inlineLabel).getRegex(),
  reflink: edit(/^!?\[(label)\]\s*\[([^\]]*)\]/).replace("label", _inlineLabel).getRegex()
};
var inlineGfm = {
  ...inlineNormal,
  emStrongRDelimAst: emStrongRDelimAstGfm,
  emStrongLDelim: emStrongLDelimGfm,
  url: edit(/^((?:ftp|https?):\/\/|www\.)(?:[a-zA-Z0-9\-]+\.?)+[^\s<]*|^email/, "i").replace("email", /[A-Za-z0-9._+-]+(@)[a-zA-Z0-9-_]+(?:\.[a-zA-Z0-9-_]*[a-zA-Z0-9])+(?![-_])/).getRegex(),
  _backpedal: /(?:[^?!.,:;*_'"~()&]+|\([^)]*\)|&(?![a-zA-Z0-9]+;$)|[?!.,:;*_'"~)]+(?!$))+/,
  del: /^(~~?)(?=[^\s~])((?:\\.|[^\\])*?(?:\\.|[^\s~\\]))\1(?=[^~]|$)/,
  text: /^([`~]+|[^`~])(?:(?= {2,}\n)|(?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)|[\s\S]*?(?:(?=[\\<!\[`*~_]|\b_|https?:\/\/|ftp:\/\/|www\.|$)|[^ ](?= {2,}\n)|[^a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-](?=[a-zA-Z0-9.!#$%&'*+\/=?_`{\|}~-]+@)))/
};
var inlineBreaks = {
  ...inlineGfm,
  br: edit(br).replace("{2,}", "*").getRegex(),
  text: edit(inlineGfm.text).replace("\\b_", "\\b_| {2,}\\n").replace(/\{2,\}/g, "*").getRegex()
};
var block = {
  normal: blockNormal,
  gfm: blockGfm,
  pedantic: blockPedantic
};
var inline = {
  normal: inlineNormal,
  gfm: inlineGfm,
  breaks: inlineBreaks,
  pedantic: inlinePedantic
};
var escapeReplacements = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;"
};
var getEscapeReplacement = (ch) => escapeReplacements[ch];
function escape2(html2, encode) {
  if (encode) {
    if (other.escapeTest.test(html2)) {
      return html2.replace(other.escapeReplace, getEscapeReplacement);
    }
  } else {
    if (other.escapeTestNoEncode.test(html2)) {
      return html2.replace(other.escapeReplaceNoEncode, getEscapeReplacement);
    }
  }
  return html2;
}
function cleanUrl(href) {
  try {
    href = encodeURI(href).replace(other.percentDecode, "%");
  } catch {
    return null;
  }
  return href;
}
function splitCells(tableRow, count) {
  const row = tableRow.replace(other.findPipe, (match, offset, str) => {
    let escaped = false;
    let curr = offset;
    while (--curr >= 0 && str[curr] === "\\")
      escaped = !escaped;
    if (escaped) {
      return "|";
    } else {
      return " |";
    }
  }), cells = row.split(other.splitPipe);
  let i = 0;
  if (!cells[0].trim()) {
    cells.shift();
  }
  if (cells.length > 0 && !cells.at(-1)?.trim()) {
    cells.pop();
  }
  if (count) {
    if (cells.length > count) {
      cells.splice(count);
    } else {
      while (cells.length < count)
        cells.push("");
    }
  }
  for (;i < cells.length; i++) {
    cells[i] = cells[i].trim().replace(other.slashPipe, "|");
  }
  return cells;
}
function rtrim(str, c, invert) {
  const l = str.length;
  if (l === 0) {
    return "";
  }
  let suffLen = 0;
  while (suffLen < l) {
    const currChar = str.charAt(l - suffLen - 1);
    if (currChar === c && !invert) {
      suffLen++;
    } else if (currChar !== c && invert) {
      suffLen++;
    } else {
      break;
    }
  }
  return str.slice(0, l - suffLen);
}
function findClosingBracket(str, b) {
  if (str.indexOf(b[1]) === -1) {
    return -1;
  }
  let level = 0;
  for (let i = 0;i < str.length; i++) {
    if (str[i] === "\\") {
      i++;
    } else if (str[i] === b[0]) {
      level++;
    } else if (str[i] === b[1]) {
      level--;
      if (level < 0) {
        return i;
      }
    }
  }
  if (level > 0) {
    return -2;
  }
  return -1;
}
function outputLink(cap, link2, raw, lexer2, rules) {
  const href = link2.href;
  const title = link2.title || null;
  const text = cap[1].replace(rules.other.outputLinkReplace, "$1");
  lexer2.state.inLink = true;
  const token = {
    type: cap[0].charAt(0) === "!" ? "image" : "link",
    raw,
    href,
    title,
    text,
    tokens: lexer2.inlineTokens(text)
  };
  lexer2.state.inLink = false;
  return token;
}
function indentCodeCompensation(raw, text, rules) {
  const matchIndentToCode = raw.match(rules.other.indentCodeCompensation);
  if (matchIndentToCode === null) {
    return text;
  }
  const indentToCode = matchIndentToCode[1];
  return text.split(`
`).map((node) => {
    const matchIndentInNode = node.match(rules.other.beginningSpace);
    if (matchIndentInNode === null) {
      return node;
    }
    const [indentInNode] = matchIndentInNode;
    if (indentInNode.length >= indentToCode.length) {
      return node.slice(indentToCode.length);
    }
    return node;
  }).join(`
`);
}
var _Tokenizer = class {
  options;
  rules;
  lexer;
  constructor(options2) {
    this.options = options2 || _defaults;
  }
  space(src) {
    const cap = this.rules.block.newline.exec(src);
    if (cap && cap[0].length > 0) {
      return {
        type: "space",
        raw: cap[0]
      };
    }
  }
  code(src) {
    const cap = this.rules.block.code.exec(src);
    if (cap) {
      const text = cap[0].replace(this.rules.other.codeRemoveIndent, "");
      return {
        type: "code",
        raw: cap[0],
        codeBlockStyle: "indented",
        text: !this.options.pedantic ? rtrim(text, `
`) : text
      };
    }
  }
  fences(src) {
    const cap = this.rules.block.fences.exec(src);
    if (cap) {
      const raw = cap[0];
      const text = indentCodeCompensation(raw, cap[3] || "", this.rules);
      return {
        type: "code",
        raw,
        lang: cap[2] ? cap[2].trim().replace(this.rules.inline.anyPunctuation, "$1") : cap[2],
        text
      };
    }
  }
  heading(src) {
    const cap = this.rules.block.heading.exec(src);
    if (cap) {
      let text = cap[2].trim();
      if (this.rules.other.endingHash.test(text)) {
        const trimmed = rtrim(text, "#");
        if (this.options.pedantic) {
          text = trimmed.trim();
        } else if (!trimmed || this.rules.other.endingSpaceChar.test(trimmed)) {
          text = trimmed.trim();
        }
      }
      return {
        type: "heading",
        raw: cap[0],
        depth: cap[1].length,
        text,
        tokens: this.lexer.inline(text)
      };
    }
  }
  hr(src) {
    const cap = this.rules.block.hr.exec(src);
    if (cap) {
      return {
        type: "hr",
        raw: rtrim(cap[0], `
`)
      };
    }
  }
  blockquote(src) {
    const cap = this.rules.block.blockquote.exec(src);
    if (cap) {
      let lines = rtrim(cap[0], `
`).split(`
`);
      let raw = "";
      let text = "";
      const tokens = [];
      while (lines.length > 0) {
        let inBlockquote = false;
        const currentLines = [];
        let i;
        for (i = 0;i < lines.length; i++) {
          if (this.rules.other.blockquoteStart.test(lines[i])) {
            currentLines.push(lines[i]);
            inBlockquote = true;
          } else if (!inBlockquote) {
            currentLines.push(lines[i]);
          } else {
            break;
          }
        }
        lines = lines.slice(i);
        const currentRaw = currentLines.join(`
`);
        const currentText = currentRaw.replace(this.rules.other.blockquoteSetextReplace, `
    $1`).replace(this.rules.other.blockquoteSetextReplace2, "");
        raw = raw ? `${raw}
${currentRaw}` : currentRaw;
        text = text ? `${text}
${currentText}` : currentText;
        const top = this.lexer.state.top;
        this.lexer.state.top = true;
        this.lexer.blockTokens(currentText, tokens, true);
        this.lexer.state.top = top;
        if (lines.length === 0) {
          break;
        }
        const lastToken = tokens.at(-1);
        if (lastToken?.type === "code") {
          break;
        } else if (lastToken?.type === "blockquote") {
          const oldToken = lastToken;
          const newText = oldToken.raw + `
` + lines.join(`
`);
          const newToken = this.blockquote(newText);
          tokens[tokens.length - 1] = newToken;
          raw = raw.substring(0, raw.length - oldToken.raw.length) + newToken.raw;
          text = text.substring(0, text.length - oldToken.text.length) + newToken.text;
          break;
        } else if (lastToken?.type === "list") {
          const oldToken = lastToken;
          const newText = oldToken.raw + `
` + lines.join(`
`);
          const newToken = this.list(newText);
          tokens[tokens.length - 1] = newToken;
          raw = raw.substring(0, raw.length - lastToken.raw.length) + newToken.raw;
          text = text.substring(0, text.length - oldToken.raw.length) + newToken.raw;
          lines = newText.substring(tokens.at(-1).raw.length).split(`
`);
          continue;
        }
      }
      return {
        type: "blockquote",
        raw,
        tokens,
        text
      };
    }
  }
  list(src) {
    let cap = this.rules.block.list.exec(src);
    if (cap) {
      let bull = cap[1].trim();
      const isordered = bull.length > 1;
      const list2 = {
        type: "list",
        raw: "",
        ordered: isordered,
        start: isordered ? +bull.slice(0, -1) : "",
        loose: false,
        items: []
      };
      bull = isordered ? `\\d{1,9}\\${bull.slice(-1)}` : `\\${bull}`;
      if (this.options.pedantic) {
        bull = isordered ? bull : "[*+-]";
      }
      const itemRegex = this.rules.other.listItemRegex(bull);
      let endsWithBlankLine = false;
      while (src) {
        let endEarly = false;
        let raw = "";
        let itemContents = "";
        if (!(cap = itemRegex.exec(src))) {
          break;
        }
        if (this.rules.block.hr.test(src)) {
          break;
        }
        raw = cap[0];
        src = src.substring(raw.length);
        let line = cap[2].split(`
`, 1)[0].replace(this.rules.other.listReplaceTabs, (t) => " ".repeat(3 * t.length));
        let nextLine = src.split(`
`, 1)[0];
        let blankLine = !line.trim();
        let indent = 0;
        if (this.options.pedantic) {
          indent = 2;
          itemContents = line.trimStart();
        } else if (blankLine) {
          indent = cap[1].length + 1;
        } else {
          indent = cap[2].search(this.rules.other.nonSpaceChar);
          indent = indent > 4 ? 1 : indent;
          itemContents = line.slice(indent);
          indent += cap[1].length;
        }
        if (blankLine && this.rules.other.blankLine.test(nextLine)) {
          raw += nextLine + `
`;
          src = src.substring(nextLine.length + 1);
          endEarly = true;
        }
        if (!endEarly) {
          const nextBulletRegex = this.rules.other.nextBulletRegex(indent);
          const hrRegex = this.rules.other.hrRegex(indent);
          const fencesBeginRegex = this.rules.other.fencesBeginRegex(indent);
          const headingBeginRegex = this.rules.other.headingBeginRegex(indent);
          const htmlBeginRegex = this.rules.other.htmlBeginRegex(indent);
          while (src) {
            const rawLine = src.split(`
`, 1)[0];
            let nextLineWithoutTabs;
            nextLine = rawLine;
            if (this.options.pedantic) {
              nextLine = nextLine.replace(this.rules.other.listReplaceNesting, "  ");
              nextLineWithoutTabs = nextLine;
            } else {
              nextLineWithoutTabs = nextLine.replace(this.rules.other.tabCharGlobal, "    ");
            }
            if (fencesBeginRegex.test(nextLine)) {
              break;
            }
            if (headingBeginRegex.test(nextLine)) {
              break;
            }
            if (htmlBeginRegex.test(nextLine)) {
              break;
            }
            if (nextBulletRegex.test(nextLine)) {
              break;
            }
            if (hrRegex.test(nextLine)) {
              break;
            }
            if (nextLineWithoutTabs.search(this.rules.other.nonSpaceChar) >= indent || !nextLine.trim()) {
              itemContents += `
` + nextLineWithoutTabs.slice(indent);
            } else {
              if (blankLine) {
                break;
              }
              if (line.replace(this.rules.other.tabCharGlobal, "    ").search(this.rules.other.nonSpaceChar) >= 4) {
                break;
              }
              if (fencesBeginRegex.test(line)) {
                break;
              }
              if (headingBeginRegex.test(line)) {
                break;
              }
              if (hrRegex.test(line)) {
                break;
              }
              itemContents += `
` + nextLine;
            }
            if (!blankLine && !nextLine.trim()) {
              blankLine = true;
            }
            raw += rawLine + `
`;
            src = src.substring(rawLine.length + 1);
            line = nextLineWithoutTabs.slice(indent);
          }
        }
        if (!list2.loose) {
          if (endsWithBlankLine) {
            list2.loose = true;
          } else if (this.rules.other.doubleBlankLine.test(raw)) {
            endsWithBlankLine = true;
          }
        }
        let istask = null;
        let ischecked;
        if (this.options.gfm) {
          istask = this.rules.other.listIsTask.exec(itemContents);
          if (istask) {
            ischecked = istask[0] !== "[ ] ";
            itemContents = itemContents.replace(this.rules.other.listReplaceTask, "");
          }
        }
        list2.items.push({
          type: "list_item",
          raw,
          task: !!istask,
          checked: ischecked,
          loose: false,
          text: itemContents,
          tokens: []
        });
        list2.raw += raw;
      }
      const lastItem = list2.items.at(-1);
      if (lastItem) {
        lastItem.raw = lastItem.raw.trimEnd();
        lastItem.text = lastItem.text.trimEnd();
      } else {
        return;
      }
      list2.raw = list2.raw.trimEnd();
      for (let i = 0;i < list2.items.length; i++) {
        this.lexer.state.top = false;
        list2.items[i].tokens = this.lexer.blockTokens(list2.items[i].text, []);
        if (!list2.loose) {
          const spacers = list2.items[i].tokens.filter((t) => t.type === "space");
          const hasMultipleLineBreaks = spacers.length > 0 && spacers.some((t) => this.rules.other.anyLine.test(t.raw));
          list2.loose = hasMultipleLineBreaks;
        }
      }
      if (list2.loose) {
        for (let i = 0;i < list2.items.length; i++) {
          list2.items[i].loose = true;
        }
      }
      return list2;
    }
  }
  html(src) {
    const cap = this.rules.block.html.exec(src);
    if (cap) {
      const token = {
        type: "html",
        block: true,
        raw: cap[0],
        pre: cap[1] === "pre" || cap[1] === "script" || cap[1] === "style",
        text: cap[0]
      };
      return token;
    }
  }
  def(src) {
    const cap = this.rules.block.def.exec(src);
    if (cap) {
      const tag2 = cap[1].toLowerCase().replace(this.rules.other.multipleSpaceGlobal, " ");
      const href = cap[2] ? cap[2].replace(this.rules.other.hrefBrackets, "$1").replace(this.rules.inline.anyPunctuation, "$1") : "";
      const title = cap[3] ? cap[3].substring(1, cap[3].length - 1).replace(this.rules.inline.anyPunctuation, "$1") : cap[3];
      return {
        type: "def",
        tag: tag2,
        raw: cap[0],
        href,
        title
      };
    }
  }
  table(src) {
    const cap = this.rules.block.table.exec(src);
    if (!cap) {
      return;
    }
    if (!this.rules.other.tableDelimiter.test(cap[2])) {
      return;
    }
    const headers = splitCells(cap[1]);
    const aligns = cap[2].replace(this.rules.other.tableAlignChars, "").split("|");
    const rows = cap[3]?.trim() ? cap[3].replace(this.rules.other.tableRowBlankLine, "").split(`
`) : [];
    const item = {
      type: "table",
      raw: cap[0],
      header: [],
      align: [],
      rows: []
    };
    if (headers.length !== aligns.length) {
      return;
    }
    for (const align of aligns) {
      if (this.rules.other.tableAlignRight.test(align)) {
        item.align.push("right");
      } else if (this.rules.other.tableAlignCenter.test(align)) {
        item.align.push("center");
      } else if (this.rules.other.tableAlignLeft.test(align)) {
        item.align.push("left");
      } else {
        item.align.push(null);
      }
    }
    for (let i = 0;i < headers.length; i++) {
      item.header.push({
        text: headers[i],
        tokens: this.lexer.inline(headers[i]),
        header: true,
        align: item.align[i]
      });
    }
    for (const row of rows) {
      item.rows.push(splitCells(row, item.header.length).map((cell, i) => {
        return {
          text: cell,
          tokens: this.lexer.inline(cell),
          header: false,
          align: item.align[i]
        };
      }));
    }
    return item;
  }
  lheading(src) {
    const cap = this.rules.block.lheading.exec(src);
    if (cap) {
      return {
        type: "heading",
        raw: cap[0],
        depth: cap[2].charAt(0) === "=" ? 1 : 2,
        text: cap[1],
        tokens: this.lexer.inline(cap[1])
      };
    }
  }
  paragraph(src) {
    const cap = this.rules.block.paragraph.exec(src);
    if (cap) {
      const text = cap[1].charAt(cap[1].length - 1) === `
` ? cap[1].slice(0, -1) : cap[1];
      return {
        type: "paragraph",
        raw: cap[0],
        text,
        tokens: this.lexer.inline(text)
      };
    }
  }
  text(src) {
    const cap = this.rules.block.text.exec(src);
    if (cap) {
      return {
        type: "text",
        raw: cap[0],
        text: cap[0],
        tokens: this.lexer.inline(cap[0])
      };
    }
  }
  escape(src) {
    const cap = this.rules.inline.escape.exec(src);
    if (cap) {
      return {
        type: "escape",
        raw: cap[0],
        text: cap[1]
      };
    }
  }
  tag(src) {
    const cap = this.rules.inline.tag.exec(src);
    if (cap) {
      if (!this.lexer.state.inLink && this.rules.other.startATag.test(cap[0])) {
        this.lexer.state.inLink = true;
      } else if (this.lexer.state.inLink && this.rules.other.endATag.test(cap[0])) {
        this.lexer.state.inLink = false;
      }
      if (!this.lexer.state.inRawBlock && this.rules.other.startPreScriptTag.test(cap[0])) {
        this.lexer.state.inRawBlock = true;
      } else if (this.lexer.state.inRawBlock && this.rules.other.endPreScriptTag.test(cap[0])) {
        this.lexer.state.inRawBlock = false;
      }
      return {
        type: "html",
        raw: cap[0],
        inLink: this.lexer.state.inLink,
        inRawBlock: this.lexer.state.inRawBlock,
        block: false,
        text: cap[0]
      };
    }
  }
  link(src) {
    const cap = this.rules.inline.link.exec(src);
    if (cap) {
      const trimmedUrl = cap[2].trim();
      if (!this.options.pedantic && this.rules.other.startAngleBracket.test(trimmedUrl)) {
        if (!this.rules.other.endAngleBracket.test(trimmedUrl)) {
          return;
        }
        const rtrimSlash = rtrim(trimmedUrl.slice(0, -1), "\\");
        if ((trimmedUrl.length - rtrimSlash.length) % 2 === 0) {
          return;
        }
      } else {
        const lastParenIndex = findClosingBracket(cap[2], "()");
        if (lastParenIndex === -2) {
          return;
        }
        if (lastParenIndex > -1) {
          const start = cap[0].indexOf("!") === 0 ? 5 : 4;
          const linkLen = start + cap[1].length + lastParenIndex;
          cap[2] = cap[2].substring(0, lastParenIndex);
          cap[0] = cap[0].substring(0, linkLen).trim();
          cap[3] = "";
        }
      }
      let href = cap[2];
      let title = "";
      if (this.options.pedantic) {
        const link2 = this.rules.other.pedanticHrefTitle.exec(href);
        if (link2) {
          href = link2[1];
          title = link2[3];
        }
      } else {
        title = cap[3] ? cap[3].slice(1, -1) : "";
      }
      href = href.trim();
      if (this.rules.other.startAngleBracket.test(href)) {
        if (this.options.pedantic && !this.rules.other.endAngleBracket.test(trimmedUrl)) {
          href = href.slice(1);
        } else {
          href = href.slice(1, -1);
        }
      }
      return outputLink(cap, {
        href: href ? href.replace(this.rules.inline.anyPunctuation, "$1") : href,
        title: title ? title.replace(this.rules.inline.anyPunctuation, "$1") : title
      }, cap[0], this.lexer, this.rules);
    }
  }
  reflink(src, links) {
    let cap;
    if ((cap = this.rules.inline.reflink.exec(src)) || (cap = this.rules.inline.nolink.exec(src))) {
      const linkString = (cap[2] || cap[1]).replace(this.rules.other.multipleSpaceGlobal, " ");
      const link2 = links[linkString.toLowerCase()];
      if (!link2) {
        const text = cap[0].charAt(0);
        return {
          type: "text",
          raw: text,
          text
        };
      }
      return outputLink(cap, link2, cap[0], this.lexer, this.rules);
    }
  }
  emStrong(src, maskedSrc, prevChar = "") {
    let match = this.rules.inline.emStrongLDelim.exec(src);
    if (!match)
      return;
    if (match[3] && prevChar.match(this.rules.other.unicodeAlphaNumeric))
      return;
    const nextChar = match[1] || match[2] || "";
    if (!nextChar || !prevChar || this.rules.inline.punctuation.exec(prevChar)) {
      const lLength = [...match[0]].length - 1;
      let rDelim, rLength, delimTotal = lLength, midDelimTotal = 0;
      const endReg = match[0][0] === "*" ? this.rules.inline.emStrongRDelimAst : this.rules.inline.emStrongRDelimUnd;
      endReg.lastIndex = 0;
      maskedSrc = maskedSrc.slice(-1 * src.length + lLength);
      while ((match = endReg.exec(maskedSrc)) != null) {
        rDelim = match[1] || match[2] || match[3] || match[4] || match[5] || match[6];
        if (!rDelim)
          continue;
        rLength = [...rDelim].length;
        if (match[3] || match[4]) {
          delimTotal += rLength;
          continue;
        } else if (match[5] || match[6]) {
          if (lLength % 3 && !((lLength + rLength) % 3)) {
            midDelimTotal += rLength;
            continue;
          }
        }
        delimTotal -= rLength;
        if (delimTotal > 0)
          continue;
        rLength = Math.min(rLength, rLength + delimTotal + midDelimTotal);
        const lastCharLength = [...match[0]][0].length;
        const raw = src.slice(0, lLength + match.index + lastCharLength + rLength);
        if (Math.min(lLength, rLength) % 2) {
          const text2 = raw.slice(1, -1);
          return {
            type: "em",
            raw,
            text: text2,
            tokens: this.lexer.inlineTokens(text2)
          };
        }
        const text = raw.slice(2, -2);
        return {
          type: "strong",
          raw,
          text,
          tokens: this.lexer.inlineTokens(text)
        };
      }
    }
  }
  codespan(src) {
    const cap = this.rules.inline.code.exec(src);
    if (cap) {
      let text = cap[2].replace(this.rules.other.newLineCharGlobal, " ");
      const hasNonSpaceChars = this.rules.other.nonSpaceChar.test(text);
      const hasSpaceCharsOnBothEnds = this.rules.other.startingSpaceChar.test(text) && this.rules.other.endingSpaceChar.test(text);
      if (hasNonSpaceChars && hasSpaceCharsOnBothEnds) {
        text = text.substring(1, text.length - 1);
      }
      return {
        type: "codespan",
        raw: cap[0],
        text
      };
    }
  }
  br(src) {
    const cap = this.rules.inline.br.exec(src);
    if (cap) {
      return {
        type: "br",
        raw: cap[0]
      };
    }
  }
  del(src) {
    const cap = this.rules.inline.del.exec(src);
    if (cap) {
      return {
        type: "del",
        raw: cap[0],
        text: cap[2],
        tokens: this.lexer.inlineTokens(cap[2])
      };
    }
  }
  autolink(src) {
    const cap = this.rules.inline.autolink.exec(src);
    if (cap) {
      let text, href;
      if (cap[2] === "@") {
        text = cap[1];
        href = "mailto:" + text;
      } else {
        text = cap[1];
        href = text;
      }
      return {
        type: "link",
        raw: cap[0],
        text,
        href,
        tokens: [
          {
            type: "text",
            raw: text,
            text
          }
        ]
      };
    }
  }
  url(src) {
    let cap;
    if (cap = this.rules.inline.url.exec(src)) {
      let text, href;
      if (cap[2] === "@") {
        text = cap[0];
        href = "mailto:" + text;
      } else {
        let prevCapZero;
        do {
          prevCapZero = cap[0];
          cap[0] = this.rules.inline._backpedal.exec(cap[0])?.[0] ?? "";
        } while (prevCapZero !== cap[0]);
        text = cap[0];
        if (cap[1] === "www.") {
          href = "http://" + cap[0];
        } else {
          href = cap[0];
        }
      }
      return {
        type: "link",
        raw: cap[0],
        text,
        href,
        tokens: [
          {
            type: "text",
            raw: text,
            text
          }
        ]
      };
    }
  }
  inlineText(src) {
    const cap = this.rules.inline.text.exec(src);
    if (cap) {
      const escaped = this.lexer.state.inRawBlock;
      return {
        type: "text",
        raw: cap[0],
        text: cap[0],
        escaped
      };
    }
  }
};
var _Lexer = class __Lexer {
  tokens;
  options;
  state;
  tokenizer;
  inlineQueue;
  constructor(options2) {
    this.tokens = [];
    this.tokens.links = /* @__PURE__ */ Object.create(null);
    this.options = options2 || _defaults;
    this.options.tokenizer = this.options.tokenizer || new _Tokenizer;
    this.tokenizer = this.options.tokenizer;
    this.tokenizer.options = this.options;
    this.tokenizer.lexer = this;
    this.inlineQueue = [];
    this.state = {
      inLink: false,
      inRawBlock: false,
      top: true
    };
    const rules = {
      other,
      block: block.normal,
      inline: inline.normal
    };
    if (this.options.pedantic) {
      rules.block = block.pedantic;
      rules.inline = inline.pedantic;
    } else if (this.options.gfm) {
      rules.block = block.gfm;
      if (this.options.breaks) {
        rules.inline = inline.breaks;
      } else {
        rules.inline = inline.gfm;
      }
    }
    this.tokenizer.rules = rules;
  }
  static get rules() {
    return {
      block,
      inline
    };
  }
  static lex(src, options2) {
    const lexer2 = new __Lexer(options2);
    return lexer2.lex(src);
  }
  static lexInline(src, options2) {
    const lexer2 = new __Lexer(options2);
    return lexer2.inlineTokens(src);
  }
  lex(src) {
    src = src.replace(other.carriageReturn, `
`);
    this.blockTokens(src, this.tokens);
    for (let i = 0;i < this.inlineQueue.length; i++) {
      const next = this.inlineQueue[i];
      this.inlineTokens(next.src, next.tokens);
    }
    this.inlineQueue = [];
    return this.tokens;
  }
  blockTokens(src, tokens = [], lastParagraphClipped = false) {
    if (this.options.pedantic) {
      src = src.replace(other.tabCharGlobal, "    ").replace(other.spaceLine, "");
    }
    while (src) {
      let token;
      if (this.options.extensions?.block?.some((extTokenizer) => {
        if (token = extTokenizer.call({ lexer: this }, src, tokens)) {
          src = src.substring(token.raw.length);
          tokens.push(token);
          return true;
        }
        return false;
      })) {
        continue;
      }
      if (token = this.tokenizer.space(src)) {
        src = src.substring(token.raw.length);
        const lastToken = tokens.at(-1);
        if (token.raw.length === 1 && lastToken !== undefined) {
          lastToken.raw += `
`;
        } else {
          tokens.push(token);
        }
        continue;
      }
      if (token = this.tokenizer.code(src)) {
        src = src.substring(token.raw.length);
        const lastToken = tokens.at(-1);
        if (lastToken?.type === "paragraph" || lastToken?.type === "text") {
          lastToken.raw += `
` + token.raw;
          lastToken.text += `
` + token.text;
          this.inlineQueue.at(-1).src = lastToken.text;
        } else {
          tokens.push(token);
        }
        continue;
      }
      if (token = this.tokenizer.fences(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.heading(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.hr(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.blockquote(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.list(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.html(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.def(src)) {
        src = src.substring(token.raw.length);
        const lastToken = tokens.at(-1);
        if (lastToken?.type === "paragraph" || lastToken?.type === "text") {
          lastToken.raw += `
` + token.raw;
          lastToken.text += `
` + token.raw;
          this.inlineQueue.at(-1).src = lastToken.text;
        } else if (!this.tokens.links[token.tag]) {
          this.tokens.links[token.tag] = {
            href: token.href,
            title: token.title
          };
        }
        continue;
      }
      if (token = this.tokenizer.table(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.lheading(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      let cutSrc = src;
      if (this.options.extensions?.startBlock) {
        let startIndex = Infinity;
        const tempSrc = src.slice(1);
        let tempStart;
        this.options.extensions.startBlock.forEach((getStartIndex) => {
          tempStart = getStartIndex.call({ lexer: this }, tempSrc);
          if (typeof tempStart === "number" && tempStart >= 0) {
            startIndex = Math.min(startIndex, tempStart);
          }
        });
        if (startIndex < Infinity && startIndex >= 0) {
          cutSrc = src.substring(0, startIndex + 1);
        }
      }
      if (this.state.top && (token = this.tokenizer.paragraph(cutSrc))) {
        const lastToken = tokens.at(-1);
        if (lastParagraphClipped && lastToken?.type === "paragraph") {
          lastToken.raw += `
` + token.raw;
          lastToken.text += `
` + token.text;
          this.inlineQueue.pop();
          this.inlineQueue.at(-1).src = lastToken.text;
        } else {
          tokens.push(token);
        }
        lastParagraphClipped = cutSrc.length !== src.length;
        src = src.substring(token.raw.length);
        continue;
      }
      if (token = this.tokenizer.text(src)) {
        src = src.substring(token.raw.length);
        const lastToken = tokens.at(-1);
        if (lastToken?.type === "text") {
          lastToken.raw += `
` + token.raw;
          lastToken.text += `
` + token.text;
          this.inlineQueue.pop();
          this.inlineQueue.at(-1).src = lastToken.text;
        } else {
          tokens.push(token);
        }
        continue;
      }
      if (src) {
        const errMsg = "Infinite loop on byte: " + src.charCodeAt(0);
        if (this.options.silent) {
          console.error(errMsg);
          break;
        } else {
          throw new Error(errMsg);
        }
      }
    }
    this.state.top = true;
    return tokens;
  }
  inline(src, tokens = []) {
    this.inlineQueue.push({ src, tokens });
    return tokens;
  }
  inlineTokens(src, tokens = []) {
    let maskedSrc = src;
    let match = null;
    if (this.tokens.links) {
      const links = Object.keys(this.tokens.links);
      if (links.length > 0) {
        while ((match = this.tokenizer.rules.inline.reflinkSearch.exec(maskedSrc)) != null) {
          if (links.includes(match[0].slice(match[0].lastIndexOf("[") + 1, -1))) {
            maskedSrc = maskedSrc.slice(0, match.index) + "[" + "a".repeat(match[0].length - 2) + "]" + maskedSrc.slice(this.tokenizer.rules.inline.reflinkSearch.lastIndex);
          }
        }
      }
    }
    while ((match = this.tokenizer.rules.inline.anyPunctuation.exec(maskedSrc)) != null) {
      maskedSrc = maskedSrc.slice(0, match.index) + "++" + maskedSrc.slice(this.tokenizer.rules.inline.anyPunctuation.lastIndex);
    }
    while ((match = this.tokenizer.rules.inline.blockSkip.exec(maskedSrc)) != null) {
      maskedSrc = maskedSrc.slice(0, match.index) + "[" + "a".repeat(match[0].length - 2) + "]" + maskedSrc.slice(this.tokenizer.rules.inline.blockSkip.lastIndex);
    }
    let keepPrevChar = false;
    let prevChar = "";
    while (src) {
      if (!keepPrevChar) {
        prevChar = "";
      }
      keepPrevChar = false;
      let token;
      if (this.options.extensions?.inline?.some((extTokenizer) => {
        if (token = extTokenizer.call({ lexer: this }, src, tokens)) {
          src = src.substring(token.raw.length);
          tokens.push(token);
          return true;
        }
        return false;
      })) {
        continue;
      }
      if (token = this.tokenizer.escape(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.tag(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.link(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.reflink(src, this.tokens.links)) {
        src = src.substring(token.raw.length);
        const lastToken = tokens.at(-1);
        if (token.type === "text" && lastToken?.type === "text") {
          lastToken.raw += token.raw;
          lastToken.text += token.text;
        } else {
          tokens.push(token);
        }
        continue;
      }
      if (token = this.tokenizer.emStrong(src, maskedSrc, prevChar)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.codespan(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.br(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.del(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (token = this.tokenizer.autolink(src)) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      if (!this.state.inLink && (token = this.tokenizer.url(src))) {
        src = src.substring(token.raw.length);
        tokens.push(token);
        continue;
      }
      let cutSrc = src;
      if (this.options.extensions?.startInline) {
        let startIndex = Infinity;
        const tempSrc = src.slice(1);
        let tempStart;
        this.options.extensions.startInline.forEach((getStartIndex) => {
          tempStart = getStartIndex.call({ lexer: this }, tempSrc);
          if (typeof tempStart === "number" && tempStart >= 0) {
            startIndex = Math.min(startIndex, tempStart);
          }
        });
        if (startIndex < Infinity && startIndex >= 0) {
          cutSrc = src.substring(0, startIndex + 1);
        }
      }
      if (token = this.tokenizer.inlineText(cutSrc)) {
        src = src.substring(token.raw.length);
        if (token.raw.slice(-1) !== "_") {
          prevChar = token.raw.slice(-1);
        }
        keepPrevChar = true;
        const lastToken = tokens.at(-1);
        if (lastToken?.type === "text") {
          lastToken.raw += token.raw;
          lastToken.text += token.text;
        } else {
          tokens.push(token);
        }
        continue;
      }
      if (src) {
        const errMsg = "Infinite loop on byte: " + src.charCodeAt(0);
        if (this.options.silent) {
          console.error(errMsg);
          break;
        } else {
          throw new Error(errMsg);
        }
      }
    }
    return tokens;
  }
};
var _Renderer = class {
  options;
  parser;
  constructor(options2) {
    this.options = options2 || _defaults;
  }
  space(token) {
    return "";
  }
  code({ text, lang, escaped }) {
    const langString = (lang || "").match(other.notSpaceStart)?.[0];
    const code = text.replace(other.endingNewline, "") + `
`;
    if (!langString) {
      return "<pre><code>" + (escaped ? code : escape2(code, true)) + `</code></pre>
`;
    }
    return '<pre><code class="language-' + escape2(langString) + '">' + (escaped ? code : escape2(code, true)) + `</code></pre>
`;
  }
  blockquote({ tokens }) {
    const body = this.parser.parse(tokens);
    return `<blockquote>
${body}</blockquote>
`;
  }
  html({ text }) {
    return text;
  }
  heading({ tokens, depth }) {
    return `<h${depth}>${this.parser.parseInline(tokens)}</h${depth}>
`;
  }
  hr(token) {
    return `<hr>
`;
  }
  list(token) {
    const ordered = token.ordered;
    const start = token.start;
    let body = "";
    for (let j = 0;j < token.items.length; j++) {
      const item = token.items[j];
      body += this.listitem(item);
    }
    const type = ordered ? "ol" : "ul";
    const startAttr = ordered && start !== 1 ? ' start="' + start + '"' : "";
    return "<" + type + startAttr + `>
` + body + "</" + type + `>
`;
  }
  listitem(item) {
    let itemBody = "";
    if (item.task) {
      const checkbox = this.checkbox({ checked: !!item.checked });
      if (item.loose) {
        if (item.tokens[0]?.type === "paragraph") {
          item.tokens[0].text = checkbox + " " + item.tokens[0].text;
          if (item.tokens[0].tokens && item.tokens[0].tokens.length > 0 && item.tokens[0].tokens[0].type === "text") {
            item.tokens[0].tokens[0].text = checkbox + " " + escape2(item.tokens[0].tokens[0].text);
            item.tokens[0].tokens[0].escaped = true;
          }
        } else {
          item.tokens.unshift({
            type: "text",
            raw: checkbox + " ",
            text: checkbox + " ",
            escaped: true
          });
        }
      } else {
        itemBody += checkbox + " ";
      }
    }
    itemBody += this.parser.parse(item.tokens, !!item.loose);
    return `<li>${itemBody}</li>
`;
  }
  checkbox({ checked }) {
    return "<input " + (checked ? 'checked="" ' : "") + 'disabled="" type="checkbox">';
  }
  paragraph({ tokens }) {
    return `<p>${this.parser.parseInline(tokens)}</p>
`;
  }
  table(token) {
    let header = "";
    let cell = "";
    for (let j = 0;j < token.header.length; j++) {
      cell += this.tablecell(token.header[j]);
    }
    header += this.tablerow({ text: cell });
    let body = "";
    for (let j = 0;j < token.rows.length; j++) {
      const row = token.rows[j];
      cell = "";
      for (let k = 0;k < row.length; k++) {
        cell += this.tablecell(row[k]);
      }
      body += this.tablerow({ text: cell });
    }
    if (body)
      body = `<tbody>${body}</tbody>`;
    return `<table>
<thead>
` + header + `</thead>
` + body + `</table>
`;
  }
  tablerow({ text }) {
    return `<tr>
${text}</tr>
`;
  }
  tablecell(token) {
    const content = this.parser.parseInline(token.tokens);
    const type = token.header ? "th" : "td";
    const tag2 = token.align ? `<${type} align="${token.align}">` : `<${type}>`;
    return tag2 + content + `</${type}>
`;
  }
  strong({ tokens }) {
    return `<strong>${this.parser.parseInline(tokens)}</strong>`;
  }
  em({ tokens }) {
    return `<em>${this.parser.parseInline(tokens)}</em>`;
  }
  codespan({ text }) {
    return `<code>${escape2(text, true)}</code>`;
  }
  br(token) {
    return "<br>";
  }
  del({ tokens }) {
    return `<del>${this.parser.parseInline(tokens)}</del>`;
  }
  link({ href, title, tokens }) {
    const text = this.parser.parseInline(tokens);
    const cleanHref = cleanUrl(href);
    if (cleanHref === null) {
      return text;
    }
    href = cleanHref;
    let out = '<a href="' + href + '"';
    if (title) {
      out += ' title="' + escape2(title) + '"';
    }
    out += ">" + text + "</a>";
    return out;
  }
  image({ href, title, text, tokens }) {
    if (tokens) {
      text = this.parser.parseInline(tokens, this.parser.textRenderer);
    }
    const cleanHref = cleanUrl(href);
    if (cleanHref === null) {
      return escape2(text);
    }
    href = cleanHref;
    let out = `<img src="${href}" alt="${text}"`;
    if (title) {
      out += ` title="${escape2(title)}"`;
    }
    out += ">";
    return out;
  }
  text(token) {
    return "tokens" in token && token.tokens ? this.parser.parseInline(token.tokens) : ("escaped" in token) && token.escaped ? token.text : escape2(token.text);
  }
};
var _TextRenderer = class {
  strong({ text }) {
    return text;
  }
  em({ text }) {
    return text;
  }
  codespan({ text }) {
    return text;
  }
  del({ text }) {
    return text;
  }
  html({ text }) {
    return text;
  }
  text({ text }) {
    return text;
  }
  link({ text }) {
    return "" + text;
  }
  image({ text }) {
    return "" + text;
  }
  br() {
    return "";
  }
};
var _Parser = class __Parser {
  options;
  renderer;
  textRenderer;
  constructor(options2) {
    this.options = options2 || _defaults;
    this.options.renderer = this.options.renderer || new _Renderer;
    this.renderer = this.options.renderer;
    this.renderer.options = this.options;
    this.renderer.parser = this;
    this.textRenderer = new _TextRenderer;
  }
  static parse(tokens, options2) {
    const parser2 = new __Parser(options2);
    return parser2.parse(tokens);
  }
  static parseInline(tokens, options2) {
    const parser2 = new __Parser(options2);
    return parser2.parseInline(tokens);
  }
  parse(tokens, top = true) {
    let out = "";
    for (let i = 0;i < tokens.length; i++) {
      const anyToken = tokens[i];
      if (this.options.extensions?.renderers?.[anyToken.type]) {
        const genericToken = anyToken;
        const ret = this.options.extensions.renderers[genericToken.type].call({ parser: this }, genericToken);
        if (ret !== false || !["space", "hr", "heading", "code", "table", "blockquote", "list", "html", "paragraph", "text"].includes(genericToken.type)) {
          out += ret || "";
          continue;
        }
      }
      const token = anyToken;
      switch (token.type) {
        case "space": {
          out += this.renderer.space(token);
          continue;
        }
        case "hr": {
          out += this.renderer.hr(token);
          continue;
        }
        case "heading": {
          out += this.renderer.heading(token);
          continue;
        }
        case "code": {
          out += this.renderer.code(token);
          continue;
        }
        case "table": {
          out += this.renderer.table(token);
          continue;
        }
        case "blockquote": {
          out += this.renderer.blockquote(token);
          continue;
        }
        case "list": {
          out += this.renderer.list(token);
          continue;
        }
        case "html": {
          out += this.renderer.html(token);
          continue;
        }
        case "paragraph": {
          out += this.renderer.paragraph(token);
          continue;
        }
        case "text": {
          let textToken = token;
          let body = this.renderer.text(textToken);
          while (i + 1 < tokens.length && tokens[i + 1].type === "text") {
            textToken = tokens[++i];
            body += `
` + this.renderer.text(textToken);
          }
          if (top) {
            out += this.renderer.paragraph({
              type: "paragraph",
              raw: body,
              text: body,
              tokens: [{ type: "text", raw: body, text: body, escaped: true }]
            });
          } else {
            out += body;
          }
          continue;
        }
        default: {
          const errMsg = 'Token with "' + token.type + '" type was not found.';
          if (this.options.silent) {
            console.error(errMsg);
            return "";
          } else {
            throw new Error(errMsg);
          }
        }
      }
    }
    return out;
  }
  parseInline(tokens, renderer = this.renderer) {
    let out = "";
    for (let i = 0;i < tokens.length; i++) {
      const anyToken = tokens[i];
      if (this.options.extensions?.renderers?.[anyToken.type]) {
        const ret = this.options.extensions.renderers[anyToken.type].call({ parser: this }, anyToken);
        if (ret !== false || !["escape", "html", "link", "image", "strong", "em", "codespan", "br", "del", "text"].includes(anyToken.type)) {
          out += ret || "";
          continue;
        }
      }
      const token = anyToken;
      switch (token.type) {
        case "escape": {
          out += renderer.text(token);
          break;
        }
        case "html": {
          out += renderer.html(token);
          break;
        }
        case "link": {
          out += renderer.link(token);
          break;
        }
        case "image": {
          out += renderer.image(token);
          break;
        }
        case "strong": {
          out += renderer.strong(token);
          break;
        }
        case "em": {
          out += renderer.em(token);
          break;
        }
        case "codespan": {
          out += renderer.codespan(token);
          break;
        }
        case "br": {
          out += renderer.br(token);
          break;
        }
        case "del": {
          out += renderer.del(token);
          break;
        }
        case "text": {
          out += renderer.text(token);
          break;
        }
        default: {
          const errMsg = 'Token with "' + token.type + '" type was not found.';
          if (this.options.silent) {
            console.error(errMsg);
            return "";
          } else {
            throw new Error(errMsg);
          }
        }
      }
    }
    return out;
  }
};
var _Hooks = class {
  options;
  block;
  constructor(options2) {
    this.options = options2 || _defaults;
  }
  static passThroughHooks = /* @__PURE__ */ new Set([
    "preprocess",
    "postprocess",
    "processAllTokens"
  ]);
  preprocess(markdown) {
    return markdown;
  }
  postprocess(html2) {
    return html2;
  }
  processAllTokens(tokens) {
    return tokens;
  }
  provideLexer() {
    return this.block ? _Lexer.lex : _Lexer.lexInline;
  }
  provideParser() {
    return this.block ? _Parser.parse : _Parser.parseInline;
  }
};
var Marked = class {
  defaults = _getDefaults();
  options = this.setOptions;
  parse = this.parseMarkdown(true);
  parseInline = this.parseMarkdown(false);
  Parser = _Parser;
  Renderer = _Renderer;
  TextRenderer = _TextRenderer;
  Lexer = _Lexer;
  Tokenizer = _Tokenizer;
  Hooks = _Hooks;
  constructor(...args) {
    this.use(...args);
  }
  walkTokens(tokens, callback) {
    let values = [];
    for (const token of tokens) {
      values = values.concat(callback.call(this, token));
      switch (token.type) {
        case "table": {
          const tableToken = token;
          for (const cell of tableToken.header) {
            values = values.concat(this.walkTokens(cell.tokens, callback));
          }
          for (const row of tableToken.rows) {
            for (const cell of row) {
              values = values.concat(this.walkTokens(cell.tokens, callback));
            }
          }
          break;
        }
        case "list": {
          const listToken = token;
          values = values.concat(this.walkTokens(listToken.items, callback));
          break;
        }
        default: {
          const genericToken = token;
          if (this.defaults.extensions?.childTokens?.[genericToken.type]) {
            this.defaults.extensions.childTokens[genericToken.type].forEach((childTokens) => {
              const tokens2 = genericToken[childTokens].flat(Infinity);
              values = values.concat(this.walkTokens(tokens2, callback));
            });
          } else if (genericToken.tokens) {
            values = values.concat(this.walkTokens(genericToken.tokens, callback));
          }
        }
      }
    }
    return values;
  }
  use(...args) {
    const extensions = this.defaults.extensions || { renderers: {}, childTokens: {} };
    args.forEach((pack) => {
      const opts = { ...pack };
      opts.async = this.defaults.async || opts.async || false;
      if (pack.extensions) {
        pack.extensions.forEach((ext) => {
          if (!ext.name) {
            throw new Error("extension name required");
          }
          if ("renderer" in ext) {
            const prevRenderer = extensions.renderers[ext.name];
            if (prevRenderer) {
              extensions.renderers[ext.name] = function(...args2) {
                let ret = ext.renderer.apply(this, args2);
                if (ret === false) {
                  ret = prevRenderer.apply(this, args2);
                }
                return ret;
              };
            } else {
              extensions.renderers[ext.name] = ext.renderer;
            }
          }
          if ("tokenizer" in ext) {
            if (!ext.level || ext.level !== "block" && ext.level !== "inline") {
              throw new Error("extension level must be 'block' or 'inline'");
            }
            const extLevel = extensions[ext.level];
            if (extLevel) {
              extLevel.unshift(ext.tokenizer);
            } else {
              extensions[ext.level] = [ext.tokenizer];
            }
            if (ext.start) {
              if (ext.level === "block") {
                if (extensions.startBlock) {
                  extensions.startBlock.push(ext.start);
                } else {
                  extensions.startBlock = [ext.start];
                }
              } else if (ext.level === "inline") {
                if (extensions.startInline) {
                  extensions.startInline.push(ext.start);
                } else {
                  extensions.startInline = [ext.start];
                }
              }
            }
          }
          if ("childTokens" in ext && ext.childTokens) {
            extensions.childTokens[ext.name] = ext.childTokens;
          }
        });
        opts.extensions = extensions;
      }
      if (pack.renderer) {
        const renderer = this.defaults.renderer || new _Renderer(this.defaults);
        for (const prop in pack.renderer) {
          if (!(prop in renderer)) {
            throw new Error(`renderer '${prop}' does not exist`);
          }
          if (["options", "parser"].includes(prop)) {
            continue;
          }
          const rendererProp = prop;
          const rendererFunc = pack.renderer[rendererProp];
          const prevRenderer = renderer[rendererProp];
          renderer[rendererProp] = (...args2) => {
            let ret = rendererFunc.apply(renderer, args2);
            if (ret === false) {
              ret = prevRenderer.apply(renderer, args2);
            }
            return ret || "";
          };
        }
        opts.renderer = renderer;
      }
      if (pack.tokenizer) {
        const tokenizer = this.defaults.tokenizer || new _Tokenizer(this.defaults);
        for (const prop in pack.tokenizer) {
          if (!(prop in tokenizer)) {
            throw new Error(`tokenizer '${prop}' does not exist`);
          }
          if (["options", "rules", "lexer"].includes(prop)) {
            continue;
          }
          const tokenizerProp = prop;
          const tokenizerFunc = pack.tokenizer[tokenizerProp];
          const prevTokenizer = tokenizer[tokenizerProp];
          tokenizer[tokenizerProp] = (...args2) => {
            let ret = tokenizerFunc.apply(tokenizer, args2);
            if (ret === false) {
              ret = prevTokenizer.apply(tokenizer, args2);
            }
            return ret;
          };
        }
        opts.tokenizer = tokenizer;
      }
      if (pack.hooks) {
        const hooks = this.defaults.hooks || new _Hooks;
        for (const prop in pack.hooks) {
          if (!(prop in hooks)) {
            throw new Error(`hook '${prop}' does not exist`);
          }
          if (["options", "block"].includes(prop)) {
            continue;
          }
          const hooksProp = prop;
          const hooksFunc = pack.hooks[hooksProp];
          const prevHook = hooks[hooksProp];
          if (_Hooks.passThroughHooks.has(prop)) {
            hooks[hooksProp] = (arg) => {
              if (this.defaults.async) {
                return Promise.resolve(hooksFunc.call(hooks, arg)).then((ret2) => {
                  return prevHook.call(hooks, ret2);
                });
              }
              const ret = hooksFunc.call(hooks, arg);
              return prevHook.call(hooks, ret);
            };
          } else {
            hooks[hooksProp] = (...args2) => {
              let ret = hooksFunc.apply(hooks, args2);
              if (ret === false) {
                ret = prevHook.apply(hooks, args2);
              }
              return ret;
            };
          }
        }
        opts.hooks = hooks;
      }
      if (pack.walkTokens) {
        const walkTokens2 = this.defaults.walkTokens;
        const packWalktokens = pack.walkTokens;
        opts.walkTokens = function(token) {
          let values = [];
          values.push(packWalktokens.call(this, token));
          if (walkTokens2) {
            values = values.concat(walkTokens2.call(this, token));
          }
          return values;
        };
      }
      this.defaults = { ...this.defaults, ...opts };
    });
    return this;
  }
  setOptions(opt) {
    this.defaults = { ...this.defaults, ...opt };
    return this;
  }
  lexer(src, options2) {
    return _Lexer.lex(src, options2 ?? this.defaults);
  }
  parser(tokens, options2) {
    return _Parser.parse(tokens, options2 ?? this.defaults);
  }
  parseMarkdown(blockType) {
    const parse2 = (src, options2) => {
      const origOpt = { ...options2 };
      const opt = { ...this.defaults, ...origOpt };
      const throwError = this.onError(!!opt.silent, !!opt.async);
      if (this.defaults.async === true && origOpt.async === false) {
        return throwError(new Error("marked(): The async option was set to true by an extension. Remove async: false from the parse options object to return a Promise."));
      }
      if (typeof src === "undefined" || src === null) {
        return throwError(new Error("marked(): input parameter is undefined or null"));
      }
      if (typeof src !== "string") {
        return throwError(new Error("marked(): input parameter is of type " + Object.prototype.toString.call(src) + ", string expected"));
      }
      if (opt.hooks) {
        opt.hooks.options = opt;
        opt.hooks.block = blockType;
      }
      const lexer2 = opt.hooks ? opt.hooks.provideLexer() : blockType ? _Lexer.lex : _Lexer.lexInline;
      const parser2 = opt.hooks ? opt.hooks.provideParser() : blockType ? _Parser.parse : _Parser.parseInline;
      if (opt.async) {
        return Promise.resolve(opt.hooks ? opt.hooks.preprocess(src) : src).then((src2) => lexer2(src2, opt)).then((tokens) => opt.hooks ? opt.hooks.processAllTokens(tokens) : tokens).then((tokens) => opt.walkTokens ? Promise.all(this.walkTokens(tokens, opt.walkTokens)).then(() => tokens) : tokens).then((tokens) => parser2(tokens, opt)).then((html2) => opt.hooks ? opt.hooks.postprocess(html2) : html2).catch(throwError);
      }
      try {
        if (opt.hooks) {
          src = opt.hooks.preprocess(src);
        }
        let tokens = lexer2(src, opt);
        if (opt.hooks) {
          tokens = opt.hooks.processAllTokens(tokens);
        }
        if (opt.walkTokens) {
          this.walkTokens(tokens, opt.walkTokens);
        }
        let html2 = parser2(tokens, opt);
        if (opt.hooks) {
          html2 = opt.hooks.postprocess(html2);
        }
        return html2;
      } catch (e) {
        return throwError(e);
      }
    };
    return parse2;
  }
  onError(silent, async) {
    return (e) => {
      e.message += `
Please report this to https://github.com/markedjs/marked.`;
      if (silent) {
        const msg = "<p>An error occurred:</p><pre>" + escape2(e.message + "", true) + "</pre>";
        if (async) {
          return Promise.resolve(msg);
        }
        return msg;
      }
      if (async) {
        return Promise.reject(e);
      }
      throw e;
    };
  }
};
var markedInstance = new Marked;
function marked(src, opt) {
  return markedInstance.parse(src, opt);
}
marked.options = marked.setOptions = function(options2) {
  markedInstance.setOptions(options2);
  marked.defaults = markedInstance.defaults;
  changeDefaults(marked.defaults);
  return marked;
};
marked.getDefaults = _getDefaults;
marked.defaults = _defaults;
marked.use = function(...args) {
  markedInstance.use(...args);
  marked.defaults = markedInstance.defaults;
  changeDefaults(marked.defaults);
  return marked;
};
marked.walkTokens = function(tokens, callback) {
  return markedInstance.walkTokens(tokens, callback);
};
marked.parseInline = markedInstance.parseInline;
marked.Parser = _Parser;
marked.parser = _Parser.parse;
marked.Renderer = _Renderer;
marked.TextRenderer = _TextRenderer;
marked.Lexer = _Lexer;
marked.lexer = _Lexer.lex;
marked.Tokenizer = _Tokenizer;
marked.Hooks = _Hooks;
marked.parse = marked;
var options = marked.options;
var setOptions = marked.setOptions;
var use = marked.use;
var walkTokens = marked.walkTokens;
var parseInline = marked.parseInline;
var parser = _Parser.parse;
var lexer = _Lexer.lex;

// node_modules/@mariozechner/pi-tui/dist/components/markdown.js
class Markdown {
  text;
  paddingX;
  paddingY;
  defaultTextStyle;
  theme;
  defaultStylePrefix;
  cachedText;
  cachedWidth;
  cachedLines;
  constructor(text, paddingX, paddingY, theme, defaultTextStyle) {
    this.text = text;
    this.paddingX = paddingX;
    this.paddingY = paddingY;
    this.theme = theme;
    this.defaultTextStyle = defaultTextStyle;
  }
  setText(text) {
    this.text = text;
    this.invalidate();
  }
  invalidate() {
    this.cachedText = undefined;
    this.cachedWidth = undefined;
    this.cachedLines = undefined;
  }
  render(width) {
    if (this.cachedLines && this.cachedText === this.text && this.cachedWidth === width) {
      return this.cachedLines;
    }
    const contentWidth = Math.max(1, width - this.paddingX * 2);
    if (!this.text || this.text.trim() === "") {
      const result2 = [];
      this.cachedText = this.text;
      this.cachedWidth = width;
      this.cachedLines = result2;
      return result2;
    }
    const normalizedText = this.text.replace(/\t/g, "   ");
    const tokens = marked.lexer(normalizedText);
    const renderedLines = [];
    for (let i = 0;i < tokens.length; i++) {
      const token = tokens[i];
      const nextToken = tokens[i + 1];
      const tokenLines = this.renderToken(token, contentWidth, nextToken?.type);
      renderedLines.push(...tokenLines);
    }
    const wrappedLines = [];
    for (const line of renderedLines) {
      if (isImageLine(line)) {
        wrappedLines.push(line);
      } else {
        wrappedLines.push(...wrapTextWithAnsi(line, contentWidth));
      }
    }
    const leftMargin = " ".repeat(this.paddingX);
    const rightMargin = " ".repeat(this.paddingX);
    const bgFn = this.defaultTextStyle?.bgColor;
    const contentLines = [];
    for (const line of wrappedLines) {
      if (isImageLine(line)) {
        contentLines.push(line);
        continue;
      }
      const lineWithMargins = leftMargin + line + rightMargin;
      if (bgFn) {
        contentLines.push(applyBackgroundToLine(lineWithMargins, width, bgFn));
      } else {
        const visibleLen = visibleWidth(lineWithMargins);
        const paddingNeeded = Math.max(0, width - visibleLen);
        contentLines.push(lineWithMargins + " ".repeat(paddingNeeded));
      }
    }
    const emptyLine = " ".repeat(width);
    const emptyLines = [];
    for (let i = 0;i < this.paddingY; i++) {
      const line = bgFn ? applyBackgroundToLine(emptyLine, width, bgFn) : emptyLine;
      emptyLines.push(line);
    }
    const result = [...emptyLines, ...contentLines, ...emptyLines];
    this.cachedText = this.text;
    this.cachedWidth = width;
    this.cachedLines = result;
    return result.length > 0 ? result : [""];
  }
  applyDefaultStyle(text) {
    if (!this.defaultTextStyle) {
      return text;
    }
    let styled = text;
    if (this.defaultTextStyle.color) {
      styled = this.defaultTextStyle.color(styled);
    }
    if (this.defaultTextStyle.bold) {
      styled = this.theme.bold(styled);
    }
    if (this.defaultTextStyle.italic) {
      styled = this.theme.italic(styled);
    }
    if (this.defaultTextStyle.strikethrough) {
      styled = this.theme.strikethrough(styled);
    }
    if (this.defaultTextStyle.underline) {
      styled = this.theme.underline(styled);
    }
    return styled;
  }
  getDefaultStylePrefix() {
    if (!this.defaultTextStyle) {
      return "";
    }
    if (this.defaultStylePrefix !== undefined) {
      return this.defaultStylePrefix;
    }
    const sentinel = "\x00";
    let styled = sentinel;
    if (this.defaultTextStyle.color) {
      styled = this.defaultTextStyle.color(styled);
    }
    if (this.defaultTextStyle.bold) {
      styled = this.theme.bold(styled);
    }
    if (this.defaultTextStyle.italic) {
      styled = this.theme.italic(styled);
    }
    if (this.defaultTextStyle.strikethrough) {
      styled = this.theme.strikethrough(styled);
    }
    if (this.defaultTextStyle.underline) {
      styled = this.theme.underline(styled);
    }
    const sentinelIndex = styled.indexOf(sentinel);
    this.defaultStylePrefix = sentinelIndex >= 0 ? styled.slice(0, sentinelIndex) : "";
    return this.defaultStylePrefix;
  }
  getStylePrefix(styleFn) {
    const sentinel = "\x00";
    const styled = styleFn(sentinel);
    const sentinelIndex = styled.indexOf(sentinel);
    return sentinelIndex >= 0 ? styled.slice(0, sentinelIndex) : "";
  }
  getDefaultInlineStyleContext() {
    return {
      applyText: (text) => this.applyDefaultStyle(text),
      stylePrefix: this.getDefaultStylePrefix()
    };
  }
  renderToken(token, width, nextTokenType, styleContext) {
    const lines = [];
    switch (token.type) {
      case "heading": {
        const headingLevel = token.depth;
        const headingPrefix = `${"#".repeat(headingLevel)} `;
        let headingStyleFn;
        if (headingLevel === 1) {
          headingStyleFn = (text) => this.theme.heading(this.theme.bold(this.theme.underline(text)));
        } else {
          headingStyleFn = (text) => this.theme.heading(this.theme.bold(text));
        }
        const headingStyleContext = {
          applyText: headingStyleFn,
          stylePrefix: this.getStylePrefix(headingStyleFn)
        };
        const headingText = this.renderInlineTokens(token.tokens || [], headingStyleContext);
        const styledHeading = headingLevel >= 3 ? headingStyleFn(headingPrefix) + headingText : headingText;
        lines.push(styledHeading);
        if (nextTokenType && nextTokenType !== "space") {
          lines.push("");
        }
        break;
      }
      case "paragraph": {
        const paragraphText = this.renderInlineTokens(token.tokens || [], styleContext);
        lines.push(paragraphText);
        if (nextTokenType && nextTokenType !== "list" && nextTokenType !== "space") {
          lines.push("");
        }
        break;
      }
      case "code": {
        const indent = this.theme.codeBlockIndent ?? "  ";
        lines.push(this.theme.codeBlockBorder(`\`\`\`${token.lang || ""}`));
        if (this.theme.highlightCode) {
          const highlightedLines = this.theme.highlightCode(token.text, token.lang);
          for (const hlLine of highlightedLines) {
            lines.push(`${indent}${hlLine}`);
          }
        } else {
          const codeLines = token.text.split(`
`);
          for (const codeLine of codeLines) {
            lines.push(`${indent}${this.theme.codeBlock(codeLine)}`);
          }
        }
        lines.push(this.theme.codeBlockBorder("```"));
        if (nextTokenType && nextTokenType !== "space") {
          lines.push("");
        }
        break;
      }
      case "list": {
        const listLines = this.renderList(token, 0, styleContext);
        lines.push(...listLines);
        break;
      }
      case "table": {
        const tableLines = this.renderTable(token, width, nextTokenType, styleContext);
        lines.push(...tableLines);
        break;
      }
      case "blockquote": {
        const quoteStyle = (text) => this.theme.quote(this.theme.italic(text));
        const quoteStylePrefix = this.getStylePrefix(quoteStyle);
        const applyQuoteStyle = (line) => {
          if (!quoteStylePrefix) {
            return quoteStyle(line);
          }
          const lineWithReappliedStyle = line.replace(/\x1b\[0m/g, `\x1B[0m${quoteStylePrefix}`);
          return quoteStyle(lineWithReappliedStyle);
        };
        const quoteContentWidth = Math.max(1, width - 2);
        const quoteInlineStyleContext = {
          applyText: (text) => text,
          stylePrefix: quoteStylePrefix
        };
        const quoteTokens = token.tokens || [];
        const renderedQuoteLines = [];
        for (let i = 0;i < quoteTokens.length; i++) {
          const quoteToken = quoteTokens[i];
          const nextQuoteToken = quoteTokens[i + 1];
          renderedQuoteLines.push(...this.renderToken(quoteToken, quoteContentWidth, nextQuoteToken?.type, quoteInlineStyleContext));
        }
        while (renderedQuoteLines.length > 0 && renderedQuoteLines[renderedQuoteLines.length - 1] === "") {
          renderedQuoteLines.pop();
        }
        for (const quoteLine of renderedQuoteLines) {
          const styledLine = applyQuoteStyle(quoteLine);
          const wrappedLines = wrapTextWithAnsi(styledLine, quoteContentWidth);
          for (const wrappedLine of wrappedLines) {
            lines.push(this.theme.quoteBorder("\u2502 ") + wrappedLine);
          }
        }
        if (nextTokenType && nextTokenType !== "space") {
          lines.push("");
        }
        break;
      }
      case "hr":
        lines.push(this.theme.hr("\u2500".repeat(Math.min(width, 80))));
        if (nextTokenType && nextTokenType !== "space") {
          lines.push("");
        }
        break;
      case "html":
        if ("raw" in token && typeof token.raw === "string") {
          lines.push(this.applyDefaultStyle(token.raw.trim()));
        }
        break;
      case "space":
        lines.push("");
        break;
      default:
        if ("text" in token && typeof token.text === "string") {
          lines.push(token.text);
        }
    }
    return lines;
  }
  renderInlineTokens(tokens, styleContext) {
    let result = "";
    const resolvedStyleContext = styleContext ?? this.getDefaultInlineStyleContext();
    const { applyText, stylePrefix } = resolvedStyleContext;
    const applyTextWithNewlines = (text) => {
      const segments = text.split(`
`);
      return segments.map((segment) => applyText(segment)).join(`
`);
    };
    for (const token of tokens) {
      switch (token.type) {
        case "text":
          if (token.tokens && token.tokens.length > 0) {
            result += this.renderInlineTokens(token.tokens, resolvedStyleContext);
          } else {
            result += applyTextWithNewlines(token.text);
          }
          break;
        case "paragraph":
          result += this.renderInlineTokens(token.tokens || [], resolvedStyleContext);
          break;
        case "strong": {
          const boldContent = this.renderInlineTokens(token.tokens || [], resolvedStyleContext);
          result += this.theme.bold(boldContent) + stylePrefix;
          break;
        }
        case "em": {
          const italicContent = this.renderInlineTokens(token.tokens || [], resolvedStyleContext);
          result += this.theme.italic(italicContent) + stylePrefix;
          break;
        }
        case "codespan":
          result += this.theme.code(token.text) + stylePrefix;
          break;
        case "link": {
          const linkText = this.renderInlineTokens(token.tokens || [], resolvedStyleContext);
          const hrefForComparison = token.href.startsWith("mailto:") ? token.href.slice(7) : token.href;
          if (token.text === token.href || token.text === hrefForComparison) {
            result += this.theme.link(this.theme.underline(linkText)) + stylePrefix;
          } else {
            result += this.theme.link(this.theme.underline(linkText)) + this.theme.linkUrl(` (${token.href})`) + stylePrefix;
          }
          break;
        }
        case "br":
          result += `
`;
          break;
        case "del": {
          const delContent = this.renderInlineTokens(token.tokens || [], resolvedStyleContext);
          result += this.theme.strikethrough(delContent) + stylePrefix;
          break;
        }
        case "html":
          if ("raw" in token && typeof token.raw === "string") {
            result += applyTextWithNewlines(token.raw);
          }
          break;
        default:
          if ("text" in token && typeof token.text === "string") {
            result += applyTextWithNewlines(token.text);
          }
      }
    }
    while (stylePrefix && result.endsWith(stylePrefix)) {
      result = result.slice(0, -stylePrefix.length);
    }
    return result;
  }
  renderList(token, depth, styleContext) {
    const lines = [];
    const indent = "  ".repeat(depth);
    const startNumber = token.start ?? 1;
    for (let i = 0;i < token.items.length; i++) {
      const item = token.items[i];
      const bullet2 = token.ordered ? `${startNumber + i}. ` : "- ";
      const itemLines = this.renderListItem(item.tokens || [], depth, styleContext);
      if (itemLines.length > 0) {
        const firstLine = itemLines[0];
        const isNestedList = /^\s+\x1b\[36m[-\d]/.test(firstLine);
        if (isNestedList) {
          lines.push(firstLine);
        } else {
          lines.push(indent + this.theme.listBullet(bullet2) + firstLine);
        }
        for (let j = 1;j < itemLines.length; j++) {
          const line = itemLines[j];
          const isNestedListLine = /^\s+\x1b\[36m[-\d]/.test(line);
          if (isNestedListLine) {
            lines.push(line);
          } else {
            lines.push(`${indent}  ${line}`);
          }
        }
      } else {
        lines.push(indent + this.theme.listBullet(bullet2));
      }
    }
    return lines;
  }
  renderListItem(tokens, parentDepth, styleContext) {
    const lines = [];
    for (const token of tokens) {
      if (token.type === "list") {
        const nestedLines = this.renderList(token, parentDepth + 1, styleContext);
        lines.push(...nestedLines);
      } else if (token.type === "text") {
        const text = token.tokens && token.tokens.length > 0 ? this.renderInlineTokens(token.tokens, styleContext) : token.text || "";
        lines.push(text);
      } else if (token.type === "paragraph") {
        const text = this.renderInlineTokens(token.tokens || [], styleContext);
        lines.push(text);
      } else if (token.type === "code") {
        const indent = this.theme.codeBlockIndent ?? "  ";
        lines.push(this.theme.codeBlockBorder(`\`\`\`${token.lang || ""}`));
        if (this.theme.highlightCode) {
          const highlightedLines = this.theme.highlightCode(token.text, token.lang);
          for (const hlLine of highlightedLines) {
            lines.push(`${indent}${hlLine}`);
          }
        } else {
          const codeLines = token.text.split(`
`);
          for (const codeLine of codeLines) {
            lines.push(`${indent}${this.theme.codeBlock(codeLine)}`);
          }
        }
        lines.push(this.theme.codeBlockBorder("```"));
      } else {
        const text = this.renderInlineTokens([token], styleContext);
        if (text) {
          lines.push(text);
        }
      }
    }
    return lines;
  }
  getLongestWordWidth(text, maxWidth) {
    const words = text.split(/\s+/).filter((word) => word.length > 0);
    let longest = 0;
    for (const word of words) {
      longest = Math.max(longest, visibleWidth(word));
    }
    if (maxWidth === undefined) {
      return longest;
    }
    return Math.min(longest, maxWidth);
  }
  wrapCellText(text, maxWidth) {
    return wrapTextWithAnsi(text, Math.max(1, maxWidth));
  }
  renderTable(token, availableWidth, nextTokenType, styleContext) {
    const lines = [];
    const numCols = token.header.length;
    if (numCols === 0) {
      return lines;
    }
    const borderOverhead = 3 * numCols + 1;
    const availableForCells = availableWidth - borderOverhead;
    if (availableForCells < numCols) {
      const fallbackLines = token.raw ? wrapTextWithAnsi(token.raw, availableWidth) : [];
      if (nextTokenType && nextTokenType !== "space") {
        fallbackLines.push("");
      }
      return fallbackLines;
    }
    const maxUnbrokenWordWidth = 30;
    const naturalWidths = [];
    const minWordWidths = [];
    for (let i = 0;i < numCols; i++) {
      const headerText = this.renderInlineTokens(token.header[i].tokens || [], styleContext);
      naturalWidths[i] = visibleWidth(headerText);
      minWordWidths[i] = Math.max(1, this.getLongestWordWidth(headerText, maxUnbrokenWordWidth));
    }
    for (const row of token.rows) {
      for (let i = 0;i < row.length; i++) {
        const cellText = this.renderInlineTokens(row[i].tokens || [], styleContext);
        naturalWidths[i] = Math.max(naturalWidths[i] || 0, visibleWidth(cellText));
        minWordWidths[i] = Math.max(minWordWidths[i] || 1, this.getLongestWordWidth(cellText, maxUnbrokenWordWidth));
      }
    }
    let minColumnWidths = minWordWidths;
    let minCellsWidth = minColumnWidths.reduce((a, b) => a + b, 0);
    if (minCellsWidth > availableForCells) {
      minColumnWidths = new Array(numCols).fill(1);
      const remaining = availableForCells - numCols;
      if (remaining > 0) {
        const totalWeight = minWordWidths.reduce((total, width) => total + Math.max(0, width - 1), 0);
        const growth = minWordWidths.map((width) => {
          const weight = Math.max(0, width - 1);
          return totalWeight > 0 ? Math.floor(weight / totalWeight * remaining) : 0;
        });
        for (let i = 0;i < numCols; i++) {
          minColumnWidths[i] += growth[i] ?? 0;
        }
        const allocated = growth.reduce((total, width) => total + width, 0);
        let leftover = remaining - allocated;
        for (let i = 0;leftover > 0 && i < numCols; i++) {
          minColumnWidths[i]++;
          leftover--;
        }
      }
      minCellsWidth = minColumnWidths.reduce((a, b) => a + b, 0);
    }
    const totalNaturalWidth = naturalWidths.reduce((a, b) => a + b, 0) + borderOverhead;
    let columnWidths;
    if (totalNaturalWidth <= availableWidth) {
      columnWidths = naturalWidths.map((width, index) => Math.max(width, minColumnWidths[index]));
    } else {
      const totalGrowPotential = naturalWidths.reduce((total, width, index) => {
        return total + Math.max(0, width - minColumnWidths[index]);
      }, 0);
      const extraWidth = Math.max(0, availableForCells - minCellsWidth);
      columnWidths = minColumnWidths.map((minWidth, index) => {
        const naturalWidth = naturalWidths[index];
        const minWidthDelta = Math.max(0, naturalWidth - minWidth);
        let grow = 0;
        if (totalGrowPotential > 0) {
          grow = Math.floor(minWidthDelta / totalGrowPotential * extraWidth);
        }
        return minWidth + grow;
      });
      const allocated = columnWidths.reduce((a, b) => a + b, 0);
      let remaining = availableForCells - allocated;
      while (remaining > 0) {
        let grew = false;
        for (let i = 0;i < numCols && remaining > 0; i++) {
          if (columnWidths[i] < naturalWidths[i]) {
            columnWidths[i]++;
            remaining--;
            grew = true;
          }
        }
        if (!grew) {
          break;
        }
      }
    }
    const topBorderCells = columnWidths.map((w) => "\u2500".repeat(w));
    lines.push(`\u250C\u2500${topBorderCells.join("\u2500\u252C\u2500")}\u2500\u2510`);
    const headerCellLines = token.header.map((cell, i) => {
      const text = this.renderInlineTokens(cell.tokens || [], styleContext);
      return this.wrapCellText(text, columnWidths[i]);
    });
    const headerLineCount = Math.max(...headerCellLines.map((c) => c.length));
    for (let lineIdx = 0;lineIdx < headerLineCount; lineIdx++) {
      const rowParts = headerCellLines.map((cellLines, colIdx) => {
        const text = cellLines[lineIdx] || "";
        const padded = text + " ".repeat(Math.max(0, columnWidths[colIdx] - visibleWidth(text)));
        return this.theme.bold(padded);
      });
      lines.push(`\u2502 ${rowParts.join(" \u2502 ")} \u2502`);
    }
    const separatorCells = columnWidths.map((w) => "\u2500".repeat(w));
    const separatorLine = `\u251C\u2500${separatorCells.join("\u2500\u253C\u2500")}\u2500\u2524`;
    lines.push(separatorLine);
    for (let rowIndex = 0;rowIndex < token.rows.length; rowIndex++) {
      const row = token.rows[rowIndex];
      const rowCellLines = row.map((cell, i) => {
        const text = this.renderInlineTokens(cell.tokens || [], styleContext);
        return this.wrapCellText(text, columnWidths[i]);
      });
      const rowLineCount = Math.max(...rowCellLines.map((c) => c.length));
      for (let lineIdx = 0;lineIdx < rowLineCount; lineIdx++) {
        const rowParts = rowCellLines.map((cellLines, colIdx) => {
          const text = cellLines[lineIdx] || "";
          return text + " ".repeat(Math.max(0, columnWidths[colIdx] - visibleWidth(text)));
        });
        lines.push(`\u2502 ${rowParts.join(" \u2502 ")} \u2502`);
      }
      if (rowIndex < token.rows.length - 1) {
        lines.push(separatorLine);
      }
    }
    const bottomBorderCells = columnWidths.map((w) => "\u2500".repeat(w));
    lines.push(`\u2514\u2500${bottomBorderCells.join("\u2500\u2534\u2500")}\u2500\u2518`);
    if (nextTokenType && nextTokenType !== "space") {
      lines.push("");
    }
    return lines;
  }
}
// node_modules/@mariozechner/pi-tui/dist/stdin-buffer.js
import { EventEmitter } from "events";
var ESC = "\x1B";
var BRACKETED_PASTE_START = "\x1B[200~";
var BRACKETED_PASTE_END = "\x1B[201~";
function isCompleteSequence(data) {
  if (!data.startsWith(ESC)) {
    return "not-escape";
  }
  if (data.length === 1) {
    return "incomplete";
  }
  const afterEsc = data.slice(1);
  if (afterEsc.startsWith("[")) {
    if (afterEsc.startsWith("[M")) {
      return data.length >= 6 ? "complete" : "incomplete";
    }
    return isCompleteCsiSequence(data);
  }
  if (afterEsc.startsWith("]")) {
    return isCompleteOscSequence(data);
  }
  if (afterEsc.startsWith("P")) {
    return isCompleteDcsSequence(data);
  }
  if (afterEsc.startsWith("_")) {
    return isCompleteApcSequence(data);
  }
  if (afterEsc.startsWith("O")) {
    return afterEsc.length >= 2 ? "complete" : "incomplete";
  }
  if (afterEsc.length === 1) {
    return "complete";
  }
  return "complete";
}
function isCompleteCsiSequence(data) {
  if (!data.startsWith(`${ESC}[`)) {
    return "complete";
  }
  if (data.length < 3) {
    return "incomplete";
  }
  const payload = data.slice(2);
  const lastChar = payload[payload.length - 1];
  const lastCharCode = lastChar.charCodeAt(0);
  if (lastCharCode >= 64 && lastCharCode <= 126) {
    if (payload.startsWith("<")) {
      const mouseMatch = /^<\d+;\d+;\d+[Mm]$/.test(payload);
      if (mouseMatch) {
        return "complete";
      }
      if (lastChar === "M" || lastChar === "m") {
        const parts = payload.slice(1, -1).split(";");
        if (parts.length === 3 && parts.every((p) => /^\d+$/.test(p))) {
          return "complete";
        }
      }
      return "incomplete";
    }
    return "complete";
  }
  return "incomplete";
}
function isCompleteOscSequence(data) {
  if (!data.startsWith(`${ESC}]`)) {
    return "complete";
  }
  if (data.endsWith(`${ESC}\\`) || data.endsWith("\x07")) {
    return "complete";
  }
  return "incomplete";
}
function isCompleteDcsSequence(data) {
  if (!data.startsWith(`${ESC}P`)) {
    return "complete";
  }
  if (data.endsWith(`${ESC}\\`)) {
    return "complete";
  }
  return "incomplete";
}
function isCompleteApcSequence(data) {
  if (!data.startsWith(`${ESC}_`)) {
    return "complete";
  }
  if (data.endsWith(`${ESC}\\`)) {
    return "complete";
  }
  return "incomplete";
}
function extractCompleteSequences(buffer) {
  const sequences = [];
  let pos = 0;
  while (pos < buffer.length) {
    const remaining = buffer.slice(pos);
    if (remaining.startsWith(ESC)) {
      let seqEnd = 1;
      while (seqEnd <= remaining.length) {
        const candidate = remaining.slice(0, seqEnd);
        const status = isCompleteSequence(candidate);
        if (status === "complete") {
          sequences.push(candidate);
          pos += seqEnd;
          break;
        } else if (status === "incomplete") {
          seqEnd++;
        } else {
          sequences.push(candidate);
          pos += seqEnd;
          break;
        }
      }
      if (seqEnd > remaining.length) {
        return { sequences, remainder: remaining };
      }
    } else {
      sequences.push(remaining[0]);
      pos++;
    }
  }
  return { sequences, remainder: "" };
}

class StdinBuffer extends EventEmitter {
  buffer = "";
  timeout = null;
  timeoutMs;
  pasteMode = false;
  pasteBuffer = "";
  constructor(options2 = {}) {
    super();
    this.timeoutMs = options2.timeout ?? 10;
  }
  process(data) {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    let str;
    if (Buffer.isBuffer(data)) {
      if (data.length === 1 && data[0] > 127) {
        const byte = data[0] - 128;
        str = `\x1B${String.fromCharCode(byte)}`;
      } else {
        str = data.toString();
      }
    } else {
      str = data;
    }
    if (str.length === 0 && this.buffer.length === 0) {
      this.emit("data", "");
      return;
    }
    this.buffer += str;
    if (this.pasteMode) {
      this.pasteBuffer += this.buffer;
      this.buffer = "";
      const endIndex = this.pasteBuffer.indexOf(BRACKETED_PASTE_END);
      if (endIndex !== -1) {
        const pastedContent = this.pasteBuffer.slice(0, endIndex);
        const remaining = this.pasteBuffer.slice(endIndex + BRACKETED_PASTE_END.length);
        this.pasteMode = false;
        this.pasteBuffer = "";
        this.emit("paste", pastedContent);
        if (remaining.length > 0) {
          this.process(remaining);
        }
      }
      return;
    }
    const startIndex = this.buffer.indexOf(BRACKETED_PASTE_START);
    if (startIndex !== -1) {
      if (startIndex > 0) {
        const beforePaste = this.buffer.slice(0, startIndex);
        const result2 = extractCompleteSequences(beforePaste);
        for (const sequence of result2.sequences) {
          this.emit("data", sequence);
        }
      }
      this.buffer = this.buffer.slice(startIndex + BRACKETED_PASTE_START.length);
      this.pasteMode = true;
      this.pasteBuffer = this.buffer;
      this.buffer = "";
      const endIndex = this.pasteBuffer.indexOf(BRACKETED_PASTE_END);
      if (endIndex !== -1) {
        const pastedContent = this.pasteBuffer.slice(0, endIndex);
        const remaining = this.pasteBuffer.slice(endIndex + BRACKETED_PASTE_END.length);
        this.pasteMode = false;
        this.pasteBuffer = "";
        this.emit("paste", pastedContent);
        if (remaining.length > 0) {
          this.process(remaining);
        }
      }
      return;
    }
    const result = extractCompleteSequences(this.buffer);
    this.buffer = result.remainder;
    for (const sequence of result.sequences) {
      this.emit("data", sequence);
    }
    if (this.buffer.length > 0) {
      this.timeout = setTimeout(() => {
        const flushed = this.flush();
        for (const sequence of flushed) {
          this.emit("data", sequence);
        }
      }, this.timeoutMs);
    }
  }
  flush() {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    if (this.buffer.length === 0) {
      return [];
    }
    const sequences = [this.buffer];
    this.buffer = "";
    return sequences;
  }
  clear() {
    if (this.timeout) {
      clearTimeout(this.timeout);
      this.timeout = null;
    }
    this.buffer = "";
    this.pasteMode = false;
    this.pasteBuffer = "";
  }
  getBuffer() {
    return this.buffer;
  }
  destroy() {
    this.clear();
  }
}
// node_modules/@mariozechner/pi-tui/dist/terminal.js
import * as fs2 from "fs";
import { createRequire } from "module";
import * as path2 from "path";
var cjsRequire = createRequire(import.meta.url);

class ProcessTerminal {
  wasRaw = false;
  inputHandler;
  resizeHandler;
  _kittyProtocolActive = false;
  _modifyOtherKeysActive = false;
  stdinBuffer;
  stdinDataHandler;
  writeLogPath = (() => {
    const env = process.env.PI_TUI_WRITE_LOG || "";
    if (!env)
      return "";
    try {
      if (fs2.statSync(env).isDirectory()) {
        const now = new Date;
        const ts = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}_${String(now.getHours()).padStart(2, "0")}-${String(now.getMinutes()).padStart(2, "0")}-${String(now.getSeconds()).padStart(2, "0")}`;
        return path2.join(env, `tui-${ts}-${process.pid}.log`);
      }
    } catch {}
    return env;
  })();
  get kittyProtocolActive() {
    return this._kittyProtocolActive;
  }
  start(onInput, onResize) {
    this.inputHandler = onInput;
    this.resizeHandler = onResize;
    this.wasRaw = process.stdin.isRaw || false;
    if (process.stdin.setRawMode) {
      process.stdin.setRawMode(true);
    }
    process.stdin.setEncoding("utf8");
    process.stdin.resume();
    process.stdout.write("\x1B[?2004h");
    process.stdout.on("resize", this.resizeHandler);
    if (process.platform !== "win32") {
      process.kill(process.pid, "SIGWINCH");
    }
    this.enableWindowsVTInput();
    this.queryAndEnableKittyProtocol();
  }
  setupStdinBuffer() {
    this.stdinBuffer = new StdinBuffer({ timeout: 10 });
    const kittyResponsePattern = /^\x1b\[\?(\d+)u$/;
    this.stdinBuffer.on("data", (sequence) => {
      if (!this._kittyProtocolActive) {
        const match = sequence.match(kittyResponsePattern);
        if (match) {
          this._kittyProtocolActive = true;
          setKittyProtocolActive(true);
          process.stdout.write("\x1B[>7u");
          return;
        }
      }
      if (this.inputHandler) {
        this.inputHandler(sequence);
      }
    });
    this.stdinBuffer.on("paste", (content) => {
      if (this.inputHandler) {
        this.inputHandler(`\x1B[200~${content}\x1B[201~`);
      }
    });
    this.stdinDataHandler = (data) => {
      this.stdinBuffer.process(data);
    };
  }
  queryAndEnableKittyProtocol() {
    this.setupStdinBuffer();
    process.stdin.on("data", this.stdinDataHandler);
    process.stdout.write("\x1B[?u");
    setTimeout(() => {
      if (!this._kittyProtocolActive && !this._modifyOtherKeysActive) {
        process.stdout.write("\x1B[>4;2m");
        this._modifyOtherKeysActive = true;
      }
    }, 150);
  }
  enableWindowsVTInput() {
    if (process.platform !== "win32")
      return;
    try {
      const koffi = cjsRequire("koffi");
      const k32 = koffi.load("kernel32.dll");
      const GetStdHandle = k32.func("void* __stdcall GetStdHandle(int)");
      const GetConsoleMode = k32.func("bool __stdcall GetConsoleMode(void*, _Out_ uint32_t*)");
      const SetConsoleMode = k32.func("bool __stdcall SetConsoleMode(void*, uint32_t)");
      const STD_INPUT_HANDLE = -10;
      const ENABLE_VIRTUAL_TERMINAL_INPUT = 512;
      const handle = GetStdHandle(STD_INPUT_HANDLE);
      const mode = new Uint32Array(1);
      GetConsoleMode(handle, mode);
      SetConsoleMode(handle, mode[0] | ENABLE_VIRTUAL_TERMINAL_INPUT);
    } catch {}
  }
  async drainInput(maxMs = 1000, idleMs = 50) {
    if (this._kittyProtocolActive) {
      process.stdout.write("\x1B[<u");
      this._kittyProtocolActive = false;
      setKittyProtocolActive(false);
    }
    if (this._modifyOtherKeysActive) {
      process.stdout.write("\x1B[>4;0m");
      this._modifyOtherKeysActive = false;
    }
    const previousHandler = this.inputHandler;
    this.inputHandler = undefined;
    let lastDataTime = Date.now();
    const onData = () => {
      lastDataTime = Date.now();
    };
    process.stdin.on("data", onData);
    const endTime = Date.now() + maxMs;
    try {
      while (true) {
        const now = Date.now();
        const timeLeft = endTime - now;
        if (timeLeft <= 0)
          break;
        if (now - lastDataTime >= idleMs)
          break;
        await new Promise((resolve) => setTimeout(resolve, Math.min(idleMs, timeLeft)));
      }
    } finally {
      process.stdin.removeListener("data", onData);
      this.inputHandler = previousHandler;
    }
  }
  stop() {
    process.stdout.write("\x1B[?2004l");
    if (this._kittyProtocolActive) {
      process.stdout.write("\x1B[<u");
      this._kittyProtocolActive = false;
      setKittyProtocolActive(false);
    }
    if (this._modifyOtherKeysActive) {
      process.stdout.write("\x1B[>4;0m");
      this._modifyOtherKeysActive = false;
    }
    if (this.stdinBuffer) {
      this.stdinBuffer.destroy();
      this.stdinBuffer = undefined;
    }
    if (this.stdinDataHandler) {
      process.stdin.removeListener("data", this.stdinDataHandler);
      this.stdinDataHandler = undefined;
    }
    this.inputHandler = undefined;
    if (this.resizeHandler) {
      process.stdout.removeListener("resize", this.resizeHandler);
      this.resizeHandler = undefined;
    }
    process.stdin.pause();
    if (process.stdin.setRawMode) {
      process.stdin.setRawMode(this.wasRaw);
    }
  }
  write(data) {
    process.stdout.write(data);
    if (this.writeLogPath) {
      try {
        fs2.appendFileSync(this.writeLogPath, data, { encoding: "utf8" });
      } catch {}
    }
  }
  get columns() {
    return process.stdout.columns || 80;
  }
  get rows() {
    return process.stdout.rows || 24;
  }
  moveBy(lines) {
    if (lines > 0) {
      process.stdout.write(`\x1B[${lines}B`);
    } else if (lines < 0) {
      process.stdout.write(`\x1B[${-lines}A`);
    }
  }
  hideCursor() {
    process.stdout.write("\x1B[?25l");
  }
  showCursor() {
    process.stdout.write("\x1B[?25h");
  }
  clearLine() {
    process.stdout.write("\x1B[K");
  }
  clearFromCursor() {
    process.stdout.write("\x1B[J");
  }
  clearScreen() {
    process.stdout.write("\x1B[2J\x1B[H");
  }
  setTitle(title) {
    process.stdout.write(`\x1B]0;${title}\x07`);
  }
}
// src/vendor/acp-bridge/stream.ts
var parseNdjsonStream = (input, onMessage, onError) => {
  let buffer = "";
  input.on("data", (chunk) => {
    buffer += chunk.toString();
    const lines = buffer.split(`
`);
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim() === "")
        continue;
      try {
        onMessage(JSON.parse(line));
      } catch {
        onError(new Error(`Invalid NDJSON: ${line}`));
      }
    }
  });
};
// src/vendor/types/memory.ts
var MESSAGE_ROLES = new Set(["user", "assistant", "tool", "system"]);
var MEMORY_ITEM_KINDS = new Set(["fact", "summary"]);

// src/vendor/types/sessionLifecycle.ts
var OWNER_RESUMABLE_PARKED_REASONS = [
  "owner_disconnected",
  "runtime_timeout",
  "idle",
  "manual",
  "transfer_expired"
];
var AUTO_RESUME_ALLOWED_PARKED_REASONS = [
  "owner_disconnected",
  "runtime_timeout",
  "idle",
  "manual",
  "transfer_expired",
  "approval_pending"
];
var TAKEOVER_ALLOWED_PARKED_REASONS = [
  "owner_disconnected",
  "runtime_timeout",
  "idle",
  "manual",
  "transfer_expired"
];
var OWNER_RESUMABLE_PARKED_REASON_SET = new Set(OWNER_RESUMABLE_PARKED_REASONS);
var TAKEOVER_ALLOWED_PARKED_REASON_SET = new Set(TAKEOVER_ALLOWED_PARKED_REASONS);
var AUTO_RESUME_ALLOWED_PARKED_REASON_SET = new Set(AUTO_RESUME_ALLOWED_PARKED_REASONS);
var SESSION_LIFECYCLE_STATES = new Set([
  "live",
  "parked",
  "closed"
]);
var SESSION_PARKED_REASONS = new Set([
  "transfer_pending",
  "transfer_expired",
  "runtime_timeout",
  "idle",
  "owner_disconnected",
  "approval_pending",
  "manual"
]);
var SESSION_LIFECYCLE_EVENT_TYPES = new Set([
  "SESSION_CREATED",
  "APPROVAL_REQUESTED",
  "APPROVAL_RESOLVED",
  "TRANSFER_REQUESTED",
  "TRANSFER_ACCEPTED",
  "TRANSFER_DISMISSED",
  "TRANSFER_EXPIRED",
  "OWNER_RESUMED",
  "TAKEOVER",
  "RUNTIME_TIMEOUT",
  "IDLE_TIMEOUT",
  "OWNER_DISCONNECTED",
  "SESSION_CLOSED"
]);

// src/vendor/types/sessionInterruption.ts
var SESSION_INTERRUPTION_KINDS = new Set([
  "approval_pending"
]);

// src/vendor/types/protocol.ts
var CLIENT_MESSAGE_TYPES = new Set([
  "prompt",
  "approval_response",
  "cancel",
  "session_close",
  "session_new",
  "session_list",
  "session_lifecycle_query",
  "session_rename",
  "session_replay",
  "session_attach",
  "session_detach",
  "session_history",
  "session_continue",
  "session_takeover",
  "auth_proof",
  "session_transfer_request",
  "session_transfer_accept",
  "session_transfer_dismiss",
  "memory_query",
  "usage_query"
]);
var GATEWAY_EVENT_TYPES = new Set([
  "text_delta",
  "thinking_delta",
  "tool_start",
  "tool_end",
  "approval_request",
  "turn_end",
  "error",
  "session_created",
  "session_updated",
  "session_invalidated",
  "session_attached",
  "session_detached",
  "session_closed",
  "auth_challenge",
  "auth_result",
  "session_transfer_requested",
  "session_transfer_updated",
  "session_transferred",
  "session_lifecycle",
  "session_lifecycle_result",
  "runtime_health",
  "session_history",
  "session_list",
  "transcript",
  "memory_result",
  "usage_result"
]);
var MEMORY_QUERY_ACTIONS = new Set([
  "stats",
  "recent",
  "search",
  "context",
  "clear"
]);
var SESSION_ATTACHMENT_STATES = new Set([
  "controller",
  "elsewhere",
  "detached"
]);
var MEMORY_SCOPES = new Set([
  "session",
  "workspace",
  "hybrid"
]);
var USAGE_QUERY_ACTIONS = new Set([
  "summary",
  "stats",
  "recent",
  "search",
  "context",
  "clear"
]);
var PRINCIPAL_TYPES = new Set([
  "user",
  "service_account"
]);
var PROMPT_SOURCES = new Set([
  "interactive",
  "schedule",
  "hook",
  "api"
]);
// src/vendor/types/acp.ts
var isJsonRpcRequest = (value) => {
  if (typeof value !== "object" || value === null)
    return false;
  const obj = value;
  return obj.jsonrpc === "2.0" && typeof obj.method === "string" && "id" in obj;
};
var isJsonRpcResponse = (value) => {
  if (typeof value !== "object" || value === null)
    return false;
  const obj = value;
  return obj.jsonrpc === "2.0" && "id" in obj && !("method" in obj);
};
var isJsonRpcNotification = (value) => {
  if (typeof value !== "object" || value === null)
    return false;
  const obj = value;
  return obj.jsonrpc === "2.0" && typeof obj.method === "string" && !("id" in obj);
};
// src/vendor/types/state.ts
var SESSION_STATUSES = new Set(["active", "idle"]);
var OWNER_IDENTITY_STATUSES = new Set(["active", "revoked"]);
var PRINCIPAL_BINDING_STATUSES = new Set(["pending", "verified", "revoked"]);
var PRINCIPAL_BINDING_SOURCES = new Set(["web", "telegram", "tui", "cli", "api", "gateway"]);
var PRINCIPAL_BINDING_PROOF_FORMATS = new Set([
  "did-auth",
  "vc",
  "linked-domain",
  "nexus-signed-binding"
]);
var AUDIT_TYPES = new Set(["tool_call", "approval", "deny", "error"]);
var EXECUTION_STATES = new Set([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out"
]);
var CHANNEL_STREAMING_MODES = new Set(["off", "edit"]);
var CHANNEL_STEERING_MODES = new Set(["off", "on"]);
// src/vendor/types/policy.ts
var POLICY_ACTIONS = new Set(["allow", "deny", "ask"]);
var PRINCIPAL_TYPES2 = new Set(["user", "service_account"]);
var PROMPT_SOURCES2 = new Set(["interactive", "schedule", "hook", "api"]);
// src/vendor/acp-bridge/rpc.ts
var createRpcClient = (input, output, options2) => {
  const timeout = options2?.timeout ?? 30000;
  let nextId = 1;
  const pending = new Map;
  const notificationHandlers = [];
  const requestHandlers = [];
  const clearPendingTimers = (entry) => {
    if (entry.timeoutTimer) {
      clearTimeout(entry.timeoutTimer);
      entry.timeoutTimer = null;
    }
    if (entry.inactivityTimer) {
      clearTimeout(entry.inactivityTimer);
      entry.inactivityTimer = null;
    }
  };
  const startInactivityTimer = (entry) => {
    if (entry.inactivityTimeoutMs === null || entry.inactivityTimeoutMs <= 0)
      return;
    if (entry.inactivityTimer) {
      clearTimeout(entry.inactivityTimer);
    }
    entry.inactivityTimer = setTimeout(() => {
      pending.delete(entry.id);
      entry.inactivityTimer = null;
      entry.reject(new Error(`RPC request "${entry.method}" (id=${entry.id}) timed out after ${entry.inactivityTimeoutMs}ms of inactivity`));
    }, entry.inactivityTimeoutMs);
  };
  const touchActivity = (activityKey) => {
    if (!activityKey)
      return;
    for (const entry of pending.values()) {
      if (entry.activityKey !== activityKey)
        continue;
      startInactivityTimer(entry);
    }
  };
  const extractActivityKey = (msg) => {
    if (!msg || typeof msg !== "object")
      return;
    const params = msg.params;
    if (!params || typeof params !== "object")
      return;
    const sessionId = params.sessionId;
    return typeof sessionId === "string" && sessionId.length > 0 ? sessionId : undefined;
  };
  const dispatchRequest = async (method, params) => {
    let lastError;
    for (const handler of requestHandlers) {
      try {
        return await handler(method, params);
      } catch (err) {
        lastError = err;
        continue;
      }
    }
    throw lastError ?? new Error(`No handler for method: ${method}`);
  };
  const handleMessage = (msg) => {
    if (isJsonRpcRequest(msg)) {
      const req = msg;
      touchActivity(extractActivityKey(req));
      console.log(`[rpc] Incoming request: id=${req.id}, method=${req.method}`);
      if (requestHandlers.length > 0) {
        dispatchRequest(req.method, req.params).then((result) => {
          console.log(`[rpc] Sending response for id=${req.id}: ${JSON.stringify(result).slice(0, 200)}`);
          sendResponse(req.id, result);
        }, (err) => {
          console.log(`[rpc] Sending error response for id=${req.id}: ${err instanceof Error ? err.message : "Unknown error"}`);
          sendErrorResponse(req.id, -32000, err instanceof Error ? err.message : "Unknown error");
        });
      } else {
        sendErrorResponse(req.id, -32601, `Method not found: ${req.method}`);
      }
      return;
    }
    if (isJsonRpcNotification(msg)) {
      const notif = msg;
      touchActivity(extractActivityKey(notif));
      console.log(`[rpc] Incoming notification: method=${notif.method}`);
      for (const handler of notificationHandlers) {
        handler(notif);
      }
      return;
    }
    if (isJsonRpcResponse(msg)) {
      const resp = msg;
      console.log(`[rpc] Incoming response: id=${resp.id}`);
      const entry = pending.get(resp.id);
      if (!entry) {
        console.log(`[rpc] No pending entry for id=${resp.id}`);
        return;
      }
      pending.delete(msg.id);
      clearPendingTimers(entry);
      if (msg.error) {
        entry.reject(new Error(msg.error.message));
      } else {
        entry.resolve(msg.result);
      }
    }
  };
  parseNdjsonStream(input, handleMessage, () => {});
  const sendRequest = (method, params, requestOptions) => {
    const id = nextId++;
    const request = { jsonrpc: "2.0", id, method };
    if (params !== undefined)
      request.params = params;
    console.log(`[rpc] Sending request: id=${id}, method=${method}`);
    output.write(JSON.stringify(request) + `
`);
    return new Promise((resolve, reject) => {
      const timeoutMs = requestOptions?.timeout === undefined ? timeout : requestOptions.timeout;
      const inactivityTimeoutMs = requestOptions?.inactivityTimeout ?? null;
      const entry = {
        resolve,
        reject,
        timeoutTimer: null,
        inactivityTimer: null,
        timeoutMs,
        inactivityTimeoutMs,
        activityKey: requestOptions?.activityKey,
        method,
        id
      };
      if (timeoutMs !== null && timeoutMs > 0) {
        entry.timeoutTimer = setTimeout(() => {
          pending.delete(id);
          entry.timeoutTimer = null;
          reject(new Error(`RPC request "${method}" (id=${id}) timed out after ${timeoutMs}ms`));
        }, timeoutMs);
      }
      pending.set(id, entry);
      startInactivityTimer(entry);
    });
  };
  const sendNotification = (method, params) => {
    const notification = { jsonrpc: "2.0", method };
    if (params !== undefined)
      notification.params = params;
    output.write(JSON.stringify(notification) + `
`);
  };
  const sendResponse = (id, result) => {
    output.write(JSON.stringify({ jsonrpc: "2.0", id, result }) + `
`);
  };
  const sendErrorResponse = (id, code, message) => {
    output.write(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }) + `
`);
  };
  const onNotification = (handler) => {
    notificationHandlers.push(handler);
    return () => {
      const idx = notificationHandlers.indexOf(handler);
      if (idx !== -1)
        notificationHandlers.splice(idx, 1);
    };
  };
  const onRequest = (handler) => {
    requestHandlers.push(handler);
    return () => {
      const idx = requestHandlers.indexOf(handler);
      if (idx !== -1)
        requestHandlers.splice(idx, 1);
    };
  };
  const destroy = () => {
    for (const [, entry] of pending) {
      clearPendingTimers(entry);
    }
    pending.clear();
  };
  return { sendRequest, sendNotification, sendResponse, sendErrorResponse, onNotification, onRequest, destroy };
};
// src/vendor/acp-bridge/session.ts
import { Buffer as Buffer2 } from "buffer";
var extractText = (content) => {
  if (!content)
    return "";
  if (Array.isArray(content)) {
    return content.filter((b) => b.type === "text" && typeof b.text === "string").map((b) => b.text).join("");
  }
  return content.type === "text" && typeof content.text === "string" ? content.text : "";
};
var extractToolName = (update) => {
  if (update.title && update.title !== '"undefined"')
    return update.title;
  const baseName = update._meta?.claudeCode?.toolName ?? "unknown";
  const input = update.rawInput;
  if (input) {
    if (input.query)
      return `${baseName}: ${input.query}`;
    if (input.pattern)
      return `${baseName}: ${input.pattern}`;
    if (input.file_path)
      return `${baseName}: ${input.file_path}`;
    if (input.command)
      return `${baseName}: ${String(input.command).slice(0, 80)}`;
  }
  return baseName;
};
var translateNotification = (notification, gatewaySessionId, acpSessionId) => {
  if (notification.method !== "session/update")
    return null;
  const p = notification.params;
  if (!p || p.sessionId !== acpSessionId)
    return null;
  const update = p.update;
  switch (update.sessionUpdate) {
    case "agent_message_chunk":
    case "agent_message":
      return {
        type: "text_delta",
        sessionId: gatewaySessionId,
        delta: extractText(update.content)
      };
    case "agent_thought_chunk":
      return {
        type: "thinking_delta",
        sessionId: gatewaySessionId,
        delta: extractText(update.content)
      };
    case "tool_call":
      return {
        type: "tool_start",
        sessionId: gatewaySessionId,
        tool: extractToolName(update),
        toolCallId: update.toolCallId,
        params: update.rawInput ?? null
      };
    case "tool_call_update":
      if (update.status === "completed" || update.status === "failed") {
        return {
          type: "tool_end",
          sessionId: gatewaySessionId,
          tool: extractToolName(update),
          toolCallId: update.toolCallId,
          result: update.rawOutput
        };
      }
      return null;
    default:
      return null;
  }
};
var inferToolName = (toolCall) => {
  const kind = typeof toolCall.kind === "string" ? toolCall.kind.toLowerCase() : undefined;
  if (kind === "fetch")
    return "WebFetch";
  if (kind === "search" || kind === "web_search")
    return "WebSearch";
  if (kind === "bash")
    return "Bash";
  const input = toolCall.rawInput;
  if (!input)
    return;
  if ("query" in input)
    return "WebSearch";
  if ("command" in input && !("file_path" in input))
    return "Bash";
  if ("url" in input && "prompt" in input)
    return "WebFetch";
  return;
};
var createAcpSession = (rpc, acpSessionId, gatewaySessionId, options2) => {
  const policyEvaluator = options2?.policyEvaluator;
  const promptInactivityTimeoutMs = options2?.promptInactivityTimeoutMs ?? 600000;
  let eventHandler;
  const pendingPermissions = new Map;
  rpc.onNotification((notification) => {
    if (!eventHandler)
      return;
    const event = translateNotification(notification, gatewaySessionId, acpSessionId);
    if (event) {
      console.log(`[acp-session] Emitting event: type=${event.type}${event.type === "text_delta" ? `, delta=${event.delta.slice(0, 80)}` : ""}`);
      eventHandler(event);
    } else if (notification.method === "session/update") {
      const p = notification.params;
      console.log(`[acp-session] Dropped notification: sessionUpdate=${p?.update?.sessionUpdate}`);
    }
  });
  rpc.onRequest(async (method, params) => {
    console.log(`[acp-session] Received request: ${method}`);
    if (method === "session/request_permission") {
      const p = params;
      if (p.sessionId !== acpSessionId) {
        throw new Error(`Unknown session: ${p.sessionId}`);
      }
      const requestId = p.toolCall.toolCallId;
      const rawToolName = p.toolCall.title;
      const paramsStr = p.toolCall.rawInput ? JSON.stringify(p.toolCall.rawInput) : undefined;
      const toolName = inferToolName(p.toolCall) ?? rawToolName;
      const optionKinds = p.options.map((opt) => opt.kind).join(",");
      console.log(`[acp-session] Permission request: requestId=${requestId}, tool=${toolName} (raw: ${rawToolName}, kind: ${p.toolCall.kind}, options=[${optionKinds}])`);
      if (policyEvaluator) {
        const action = policyEvaluator(toolName, paramsStr);
        if (action === "allow") {
          console.log(`[acp-session] Policy auto-approved: ${toolName}`);
          return { outcome: { outcome: "selected", optionId: "allow_once" } };
        }
        if (action === "deny") {
          console.log(`[acp-session] Policy auto-denied: ${toolName}`);
          return { outcome: { outcome: "selected", optionId: "reject_once" } };
        }
      }
      if (eventHandler) {
        eventHandler({
          type: "approval_request",
          sessionId: gatewaySessionId,
          requestId,
          tool: toolName,
          description: paramsStr ?? toolName,
          options: p.options
        });
        return new Promise((resolve) => {
          pendingPermissions.set(requestId, { resolve });
          console.log(`[acp-session] Pending permissions: [${[...pendingPermissions.keys()].join(", ")}]`);
        });
      }
      return { outcome: { outcome: "cancelled" } };
    }
    throw new Error(`Unhandled method: ${method}`);
  });
  const resolveImageBlock = async (image) => {
    const url = image.url.trim();
    if (!url)
      return null;
    if (url.startsWith("data:")) {
      const commaIndex = url.indexOf(",");
      if (commaIndex < 0)
        return null;
      const meta = url.slice(5, commaIndex);
      const payload = url.slice(commaIndex + 1);
      const isBase64 = meta.includes(";base64");
      const mimeTypeFromDataUrl = meta.split(";")[0]?.trim();
      const mimeType2 = image.mediaType ?? mimeTypeFromDataUrl ?? "image/*";
      const data2 = isBase64 ? payload : Buffer2.from(decodeURIComponent(payload), "utf8").toString("base64");
      return {
        type: "image",
        data: data2,
        mimeType: mimeType2
      };
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Failed to fetch image URL (${response.status}): ${url}`);
    }
    const mimeType = image.mediaType ?? response.headers.get("content-type")?.split(";")[0]?.trim() ?? "image/*";
    const arrayBuffer = await response.arrayBuffer();
    const data = Buffer2.from(arrayBuffer).toString("base64");
    return {
      type: "image",
      data,
      mimeType,
      uri: url
    };
  };
  const buildPromptBlocks = async (text, images) => {
    const imageEntries = (images ?? []).filter((image) => typeof image.url === "string" && image.url.trim().length > 0);
    const imageBlocks = [];
    for (const image of imageEntries) {
      try {
        const block2 = await resolveImageBlock(image);
        if (block2)
          imageBlocks.push(block2);
      } catch (error) {
        console.warn(`[acp-session] Failed to resolve image block for ${image.url}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }
    const needsDefaultText = text.trim().length === 0 && imageBlocks.length > 0;
    const textBlock = {
      type: "text",
      text: needsDefaultText ? "Please analyze the provided image(s)." : text
    };
    return [textBlock, ...imageBlocks];
  };
  const prompt = async (text, images) => {
    const hasImages = Array.isArray(images) && images.length > 0;
    try {
      const promptBlocks = await buildPromptBlocks(text, images);
      return await rpc.sendRequest("session/prompt", {
        sessionId: acpSessionId,
        prompt: promptBlocks
      }, {
        timeout: null,
        inactivityTimeout: promptInactivityTimeoutMs,
        activityKey: acpSessionId
      });
    } catch (error) {
      if (!hasImages)
        throw error;
      console.warn(`[acp-session] Image blocks rejected by runtime; falling back to URL text prompt: ${error instanceof Error ? error.message : String(error)}`);
      const fallbackText = [
        text.trim(),
        "",
        "Attached image URLs:",
        ...(images ?? []).map((image, index) => `${index + 1}. ${image.url}`)
      ].join(`
`).trim();
      return rpc.sendRequest("session/prompt", {
        sessionId: acpSessionId,
        prompt: [{ type: "text", text: fallbackText }]
      }, {
        timeout: null,
        inactivityTimeout: promptInactivityTimeoutMs,
        activityKey: acpSessionId
      });
    }
  };
  const respondToPermission = (requestId, optionId) => {
    const pending = pendingPermissions.get(requestId);
    if (pending) {
      console.log(`[acp-session] Resolving permission: requestId=${requestId}, optionId=${optionId}`);
      pendingPermissions.delete(requestId);
      pending.resolve({ outcome: { outcome: "selected", optionId } });
      return true;
    }
    console.log(`[acp-session] No pending permission for requestId=${requestId} (pending: [${[...pendingPermissions.keys()].join(", ")}])`);
    return false;
  };
  const cancel = () => {
    rpc.sendNotification("session/cancel", { sessionId: acpSessionId });
    for (const [id, entry] of pendingPermissions) {
      entry.resolve({ outcome: { outcome: "cancelled" } });
      pendingPermissions.delete(id);
    }
  };
  const onEvent = (handler) => {
    eventHandler = handler;
  };
  return {
    id: gatewaySessionId,
    acpSessionId,
    prompt,
    respondToPermission,
    cancel,
    onEvent
  };
};
// src/vendor/acp-bridge/manager.ts
import { spawn as spawn2 } from "child_process";
var spawnAgent = (command, options2) => {
  const [cmd, ...args] = command;
  const child = spawn2(cmd, args, {
    stdio: ["pipe", "pipe", "pipe"],
    cwd: options2?.cwd,
    env: options2?.env ? { ...process.env, ...options2.env } : undefined
  });
  child.stderr?.on("data", (chunk) => {
    process.stderr.write(`[agent] ${chunk.toString()}`);
  });
  const rpc = createRpcClient(child.stdout, child.stdin, {
    timeout: options2?.timeout
  });
  let alive = true;
  child.on("close", () => {
    alive = false;
  });
  const isAlive = () => alive;
  const kill = () => new Promise((resolve) => {
    if (!alive) {
      resolve();
      return;
    }
    child.once("close", () => resolve());
    child.kill("SIGTERM");
  });
  const onExit = (handler) => {
    child.on("close", handler);
  };
  return { rpc, process: child, isAlive, kill, onExit };
};
// src/acp/agent.ts
init_terminal();

// src/prompts.ts
import { readFileSync } from "fs";
import { resolve, dirname as dirname3 } from "path";
import { fileURLToPath } from "url";
var __promptsDir = dirname3(fileURLToPath(import.meta.url));
function loadPrompt(name) {
  const candidates = [
    resolve(__promptsDir, "..", "prompts", name),
    resolve(__promptsDir, "prompts", name)
  ];
  for (const p of candidates) {
    try {
      return readFileSync(p, "utf8").trim();
    } catch {}
  }
  return "";
}

// src/acp/agent.ts
function buildSystemPrompt(activeConnection) {
  const isFte = process.env.DB_MCP_FTE === "1";
  const parts = [
    loadPrompt("system.md"),
    isFte ? loadPrompt("fte.md") : "",
    loadPrompt("query-workflow.md"),
    loadPrompt("init-flow.md"),
    loadPrompt("commands.md"),
    loadPrompt("rules.md")
  ].filter(Boolean);
  if (activeConnection) {
    parts.push(`## ACTIVE CONNECTION
The active connection is "${activeConnection}". Run \`db-mcp use ${activeConnection}\` as your first command.`);
  }
  return parts.join(`

`);
}

class Agent {
  config;
  process = null;
  session = null;
  _sessionId = null;
  _onEvent = null;
  constructor(config2) {
    this.config = config2;
  }
  get connected() {
    return this.session !== null;
  }
  get sessionId() {
    return this._sessionId;
  }
  get commandName() {
    const cmd = this.config.command[0] ?? "unknown";
    return cmd.split("/").pop() ?? cmd;
  }
  async connect(onEvent, activeConnection) {
    if (this.process) {
      throw new Error("Already connected");
    }
    this._onEvent = onEvent;
    try {
      this.process = spawnAgent(this.config.command, {
        timeout: 300000
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      throw new Error(`Could not start agent "${this.config.command.join(" ")}": ${msg}
` + `Install with: npm i -g @agentclientprotocol/claude-agent-acp`);
    }
    const { createWriteStream } = await import("fs");
    const logStream = createWriteStream("/tmp/db-mcp-agent.log", { flags: "a" });
    this.process.process.stderr?.removeAllListeners("data");
    this.process.process.stderr?.on("data", (chunk) => {
      logStream.write(chunk);
    });
    await new Promise((resolve2, reject) => {
      const proc = this.process.process;
      const onError = (err) => {
        cleanup();
        this.process = null;
        reject(new Error(`Could not start agent "${this.config.command.join(" ")}": ${err.message}
Install with: npm i -g @agentclientprotocol/claude-agent-acp`));
      };
      const onSpawn = () => {
        cleanup();
        resolve2();
      };
      const cleanup = () => {
        proc.removeListener("error", onError);
        proc.removeListener("spawn", onSpawn);
      };
      proc.once("error", onError);
      proc.once("spawn", onSpawn);
    });
    this.process.onExit((code) => {
      onEvent({ type: "error", message: `Agent exited with code ${code}` });
      this.process = null;
      this.session = null;
      this._sessionId = null;
    });
    const initResult = await this.process.rpc.sendRequest("initialize", {
      protocolVersion: 1,
      clientInfo: { name: "db-mcp-tui", version: "0.1.0" }
    });
    const sessionResult = await this.process.rpc.sendRequest("session/new", {
      cwd: process.cwd(),
      mcpServers: [],
      _meta: {
        systemPrompt: buildSystemPrompt(activeConnection)
      }
    });
    this._sessionId = sessionResult.sessionId;
    this.process.rpc.onRequest(async (method, params) => {
      if (method === "session/request_permission") {
        const p = params;
        if (p?.toolCall?.rawInput && this._onEvent) {
          const input = p.toolCall.rawInput;
          const cmd = input.command ?? input.query ?? input.sql ?? input.pattern ?? input.file_path;
          if (cmd) {
            const s = String(cmd).replace(/\n/g, " ").trim();
            const detail = s.length > 80 ? `${s.slice(0, 80)}\u2026` : s;
            this._onEvent({ type: "tool_update", detail });
          }
        }
        return { outcome: { outcome: "selected", optionId: "allow" } };
      }
      if (method === "create_terminal") {
        return handleCreateTerminal(params);
      }
      if (method === "terminal_output") {
        return await handleTerminalOutput(params);
      }
      if (method === "wait_for_terminal_exit") {
        return await handleWaitForTerminalExit(params);
      }
      if (method === "release_terminal" || method === "kill_terminal") {
        return handleReleaseTerminal(params);
      }
      if (method === "read_text_file" || method === "write_text_file") {
        throw new Error("File operations not available in TUI mode.");
      }
      throw new Error(`Unsupported method: ${method}`);
    });
    this.session = createAcpSession(this.process.rpc, this._sessionId, this._sessionId);
    this.process.rpc.onNotification((notification) => {
      if (notification.method !== "session/update")
        return;
      const p = notification.params;
      if (!p?.update)
        return;
      const su = p.update.sessionUpdate;
      if (su === "usage_update") {
        const { appendFileSync: appendFileSync3 } = __require("fs");
        appendFileSync3("/tmp/db-mcp-usage.log", JSON.stringify(p.update) + `
`);
        const u = p.update;
        const cost = u.cost;
        onEvent({
          type: "usage",
          usage: {
            used: Number(u.used ?? 0),
            size: Number(u.size ?? 0),
            cost: cost?.amount ?? 0,
            currency: cost?.currency ?? "USD"
          }
        });
        return;
      }
      if (su === "tool_call" || su === "tool_call_update") {
        const raw = p.update.rawInput;
        if (raw && this._onEvent) {
          const cmd = raw.command ?? raw.query ?? raw.sql ?? raw.pattern ?? raw.file_path ?? raw.intent ?? raw.connection ?? raw.name;
          if (cmd) {
            const s = String(cmd).replace(/\n/g, " ").trim();
            const detail = s.length > 80 ? `${s.slice(0, 80)}\u2026` : s;
            this._onEvent({ type: "tool_update", detail });
          }
        }
      }
    });
    this.session.onEvent((gatewayEvent) => {
      switch (gatewayEvent.type) {
        case "text_delta":
          onEvent({ type: "text_delta", delta: gatewayEvent.delta });
          break;
        case "thinking_delta":
          onEvent({ type: "thinking_delta", delta: gatewayEvent.delta });
          break;
        case "tool_start": {
          const ev = gatewayEvent;
          onEvent({ type: "tool_start", tool: ev.tool, params: ev.params });
          break;
        }
        case "tool_end":
          onEvent({
            type: "tool_end",
            tool: gatewayEvent.tool,
            result: gatewayEvent.result
          });
          break;
      }
    });
  }
  async prompt(text) {
    if (!this.session) {
      throw new Error("Not connected \u2014 call connect() first");
    }
    if (!this.process?.isAlive()) {
      throw new Error("Agent process is no longer running");
    }
    await this.session.prompt(text);
  }
  get alive() {
    return this.process?.isAlive() ?? false;
  }
  cancel() {
    if (this.session) {
      this.session.cancel();
    }
  }
  async disconnect() {
    if (this.process) {
      await this.process.kill();
      this.process = null;
      this.session = null;
      this._sessionId = null;
    }
  }
}
// node_modules/chalk/source/vendor/ansi-styles/index.js
var ANSI_BACKGROUND_OFFSET = 10;
var wrapAnsi16 = (offset = 0) => (code) => `\x1B[${code + offset}m`;
var wrapAnsi256 = (offset = 0) => (code) => `\x1B[${38 + offset};5;${code}m`;
var wrapAnsi16m = (offset = 0) => (red, green, blue) => `\x1B[${38 + offset};2;${red};${green};${blue}m`;
var styles = {
  modifier: {
    reset: [0, 0],
    bold: [1, 22],
    dim: [2, 22],
    italic: [3, 23],
    underline: [4, 24],
    overline: [53, 55],
    inverse: [7, 27],
    hidden: [8, 28],
    strikethrough: [9, 29]
  },
  color: {
    black: [30, 39],
    red: [31, 39],
    green: [32, 39],
    yellow: [33, 39],
    blue: [34, 39],
    magenta: [35, 39],
    cyan: [36, 39],
    white: [37, 39],
    blackBright: [90, 39],
    gray: [90, 39],
    grey: [90, 39],
    redBright: [91, 39],
    greenBright: [92, 39],
    yellowBright: [93, 39],
    blueBright: [94, 39],
    magentaBright: [95, 39],
    cyanBright: [96, 39],
    whiteBright: [97, 39]
  },
  bgColor: {
    bgBlack: [40, 49],
    bgRed: [41, 49],
    bgGreen: [42, 49],
    bgYellow: [43, 49],
    bgBlue: [44, 49],
    bgMagenta: [45, 49],
    bgCyan: [46, 49],
    bgWhite: [47, 49],
    bgBlackBright: [100, 49],
    bgGray: [100, 49],
    bgGrey: [100, 49],
    bgRedBright: [101, 49],
    bgGreenBright: [102, 49],
    bgYellowBright: [103, 49],
    bgBlueBright: [104, 49],
    bgMagentaBright: [105, 49],
    bgCyanBright: [106, 49],
    bgWhiteBright: [107, 49]
  }
};
var modifierNames = Object.keys(styles.modifier);
var foregroundColorNames = Object.keys(styles.color);
var backgroundColorNames = Object.keys(styles.bgColor);
var colorNames = [...foregroundColorNames, ...backgroundColorNames];
function assembleStyles() {
  const codes = new Map;
  for (const [groupName, group] of Object.entries(styles)) {
    for (const [styleName, style] of Object.entries(group)) {
      styles[styleName] = {
        open: `\x1B[${style[0]}m`,
        close: `\x1B[${style[1]}m`
      };
      group[styleName] = styles[styleName];
      codes.set(style[0], style[1]);
    }
    Object.defineProperty(styles, groupName, {
      value: group,
      enumerable: false
    });
  }
  Object.defineProperty(styles, "codes", {
    value: codes,
    enumerable: false
  });
  styles.color.close = "\x1B[39m";
  styles.bgColor.close = "\x1B[49m";
  styles.color.ansi = wrapAnsi16();
  styles.color.ansi256 = wrapAnsi256();
  styles.color.ansi16m = wrapAnsi16m();
  styles.bgColor.ansi = wrapAnsi16(ANSI_BACKGROUND_OFFSET);
  styles.bgColor.ansi256 = wrapAnsi256(ANSI_BACKGROUND_OFFSET);
  styles.bgColor.ansi16m = wrapAnsi16m(ANSI_BACKGROUND_OFFSET);
  Object.defineProperties(styles, {
    rgbToAnsi256: {
      value(red, green, blue) {
        if (red === green && green === blue) {
          if (red < 8) {
            return 16;
          }
          if (red > 248) {
            return 231;
          }
          return Math.round((red - 8) / 247 * 24) + 232;
        }
        return 16 + 36 * Math.round(red / 255 * 5) + 6 * Math.round(green / 255 * 5) + Math.round(blue / 255 * 5);
      },
      enumerable: false
    },
    hexToRgb: {
      value(hex) {
        const matches = /[a-f\d]{6}|[a-f\d]{3}/i.exec(hex.toString(16));
        if (!matches) {
          return [0, 0, 0];
        }
        let [colorString] = matches;
        if (colorString.length === 3) {
          colorString = [...colorString].map((character) => character + character).join("");
        }
        const integer = Number.parseInt(colorString, 16);
        return [
          integer >> 16 & 255,
          integer >> 8 & 255,
          integer & 255
        ];
      },
      enumerable: false
    },
    hexToAnsi256: {
      value: (hex) => styles.rgbToAnsi256(...styles.hexToRgb(hex)),
      enumerable: false
    },
    ansi256ToAnsi: {
      value(code) {
        if (code < 8) {
          return 30 + code;
        }
        if (code < 16) {
          return 90 + (code - 8);
        }
        let red;
        let green;
        let blue;
        if (code >= 232) {
          red = ((code - 232) * 10 + 8) / 255;
          green = red;
          blue = red;
        } else {
          code -= 16;
          const remainder = code % 36;
          red = Math.floor(code / 36) / 5;
          green = Math.floor(remainder / 6) / 5;
          blue = remainder % 6 / 5;
        }
        const value = Math.max(red, green, blue) * 2;
        if (value === 0) {
          return 30;
        }
        let result = 30 + (Math.round(blue) << 2 | Math.round(green) << 1 | Math.round(red));
        if (value === 2) {
          result += 60;
        }
        return result;
      },
      enumerable: false
    },
    rgbToAnsi: {
      value: (red, green, blue) => styles.ansi256ToAnsi(styles.rgbToAnsi256(red, green, blue)),
      enumerable: false
    },
    hexToAnsi: {
      value: (hex) => styles.ansi256ToAnsi(styles.hexToAnsi256(hex)),
      enumerable: false
    }
  });
  return styles;
}
var ansiStyles = assembleStyles();
var ansi_styles_default = ansiStyles;

// node_modules/chalk/source/vendor/supports-color/index.js
import process2 from "process";
import os2 from "os";
import tty from "tty";
function hasFlag(flag, argv = globalThis.Deno ? globalThis.Deno.args : process2.argv) {
  const prefix = flag.startsWith("-") ? "" : flag.length === 1 ? "-" : "--";
  const position = argv.indexOf(prefix + flag);
  const terminatorPosition = argv.indexOf("--");
  return position !== -1 && (terminatorPosition === -1 || position < terminatorPosition);
}
var { env } = process2;
var flagForceColor;
if (hasFlag("no-color") || hasFlag("no-colors") || hasFlag("color=false") || hasFlag("color=never")) {
  flagForceColor = 0;
} else if (hasFlag("color") || hasFlag("colors") || hasFlag("color=true") || hasFlag("color=always")) {
  flagForceColor = 1;
}
function envForceColor() {
  if ("FORCE_COLOR" in env) {
    if (env.FORCE_COLOR === "true") {
      return 1;
    }
    if (env.FORCE_COLOR === "false") {
      return 0;
    }
    return env.FORCE_COLOR.length === 0 ? 1 : Math.min(Number.parseInt(env.FORCE_COLOR, 10), 3);
  }
}
function translateLevel(level) {
  if (level === 0) {
    return false;
  }
  return {
    level,
    hasBasic: true,
    has256: level >= 2,
    has16m: level >= 3
  };
}
function _supportsColor(haveStream, { streamIsTTY, sniffFlags = true } = {}) {
  const noFlagForceColor = envForceColor();
  if (noFlagForceColor !== undefined) {
    flagForceColor = noFlagForceColor;
  }
  const forceColor = sniffFlags ? flagForceColor : noFlagForceColor;
  if (forceColor === 0) {
    return 0;
  }
  if (sniffFlags) {
    if (hasFlag("color=16m") || hasFlag("color=full") || hasFlag("color=truecolor")) {
      return 3;
    }
    if (hasFlag("color=256")) {
      return 2;
    }
  }
  if ("TF_BUILD" in env && "AGENT_NAME" in env) {
    return 1;
  }
  if (haveStream && !streamIsTTY && forceColor === undefined) {
    return 0;
  }
  const min = forceColor || 0;
  if (env.TERM === "dumb") {
    return min;
  }
  if (process2.platform === "win32") {
    const osRelease = os2.release().split(".");
    if (Number(osRelease[0]) >= 10 && Number(osRelease[2]) >= 10586) {
      return Number(osRelease[2]) >= 14931 ? 3 : 2;
    }
    return 1;
  }
  if ("CI" in env) {
    if (["GITHUB_ACTIONS", "GITEA_ACTIONS", "CIRCLECI"].some((key) => (key in env))) {
      return 3;
    }
    if (["TRAVIS", "APPVEYOR", "GITLAB_CI", "BUILDKITE", "DRONE"].some((sign) => (sign in env)) || env.CI_NAME === "codeship") {
      return 1;
    }
    return min;
  }
  if ("TEAMCITY_VERSION" in env) {
    return /^(9\.(0*[1-9]\d*)\.|\d{2,}\.)/.test(env.TEAMCITY_VERSION) ? 1 : 0;
  }
  if (env.COLORTERM === "truecolor") {
    return 3;
  }
  if (env.TERM === "xterm-kitty") {
    return 3;
  }
  if (env.TERM === "xterm-ghostty") {
    return 3;
  }
  if (env.TERM === "wezterm") {
    return 3;
  }
  if ("TERM_PROGRAM" in env) {
    const version = Number.parseInt((env.TERM_PROGRAM_VERSION || "").split(".")[0], 10);
    switch (env.TERM_PROGRAM) {
      case "iTerm.app": {
        return version >= 3 ? 3 : 2;
      }
      case "Apple_Terminal": {
        return 2;
      }
    }
  }
  if (/-256(color)?$/i.test(env.TERM)) {
    return 2;
  }
  if (/^screen|^xterm|^vt100|^vt220|^rxvt|color|ansi|cygwin|linux/i.test(env.TERM)) {
    return 1;
  }
  if ("COLORTERM" in env) {
    return 1;
  }
  return min;
}
function createSupportsColor(stream2, options2 = {}) {
  const level = _supportsColor(stream2, {
    streamIsTTY: stream2 && stream2.isTTY,
    ...options2
  });
  return translateLevel(level);
}
var supportsColor = {
  stdout: createSupportsColor({ isTTY: tty.isatty(1) }),
  stderr: createSupportsColor({ isTTY: tty.isatty(2) })
};
var supports_color_default = supportsColor;

// node_modules/chalk/source/utilities.js
function stringReplaceAll(string, substring, replacer) {
  let index = string.indexOf(substring);
  if (index === -1) {
    return string;
  }
  const substringLength = substring.length;
  let endIndex = 0;
  let returnValue = "";
  do {
    returnValue += string.slice(endIndex, index) + substring + replacer;
    endIndex = index + substringLength;
    index = string.indexOf(substring, endIndex);
  } while (index !== -1);
  returnValue += string.slice(endIndex);
  return returnValue;
}
function stringEncaseCRLFWithFirstIndex(string, prefix, postfix, index) {
  let endIndex = 0;
  let returnValue = "";
  do {
    const gotCR = string[index - 1] === "\r";
    returnValue += string.slice(endIndex, gotCR ? index - 1 : index) + prefix + (gotCR ? `\r
` : `
`) + postfix;
    endIndex = index + 1;
    index = string.indexOf(`
`, endIndex);
  } while (index !== -1);
  returnValue += string.slice(endIndex);
  return returnValue;
}

// node_modules/chalk/source/index.js
var { stdout: stdoutColor, stderr: stderrColor } = supports_color_default;
var GENERATOR = Symbol("GENERATOR");
var STYLER = Symbol("STYLER");
var IS_EMPTY = Symbol("IS_EMPTY");
var levelMapping = [
  "ansi",
  "ansi",
  "ansi256",
  "ansi16m"
];
var styles2 = Object.create(null);
var applyOptions = (object, options2 = {}) => {
  if (options2.level && !(Number.isInteger(options2.level) && options2.level >= 0 && options2.level <= 3)) {
    throw new Error("The `level` option should be an integer from 0 to 3");
  }
  const colorLevel = stdoutColor ? stdoutColor.level : 0;
  object.level = options2.level === undefined ? colorLevel : options2.level;
};
var chalkFactory = (options2) => {
  const chalk = (...strings) => strings.join(" ");
  applyOptions(chalk, options2);
  Object.setPrototypeOf(chalk, createChalk.prototype);
  return chalk;
};
function createChalk(options2) {
  return chalkFactory(options2);
}
Object.setPrototypeOf(createChalk.prototype, Function.prototype);
for (const [styleName, style] of Object.entries(ansi_styles_default)) {
  styles2[styleName] = {
    get() {
      const builder = createBuilder(this, createStyler(style.open, style.close, this[STYLER]), this[IS_EMPTY]);
      Object.defineProperty(this, styleName, { value: builder });
      return builder;
    }
  };
}
styles2.visible = {
  get() {
    const builder = createBuilder(this, this[STYLER], true);
    Object.defineProperty(this, "visible", { value: builder });
    return builder;
  }
};
var getModelAnsi = (model, level, type, ...arguments_) => {
  if (model === "rgb") {
    if (level === "ansi16m") {
      return ansi_styles_default[type].ansi16m(...arguments_);
    }
    if (level === "ansi256") {
      return ansi_styles_default[type].ansi256(ansi_styles_default.rgbToAnsi256(...arguments_));
    }
    return ansi_styles_default[type].ansi(ansi_styles_default.rgbToAnsi(...arguments_));
  }
  if (model === "hex") {
    return getModelAnsi("rgb", level, type, ...ansi_styles_default.hexToRgb(...arguments_));
  }
  return ansi_styles_default[type][model](...arguments_);
};
var usedModels = ["rgb", "hex", "ansi256"];
for (const model of usedModels) {
  styles2[model] = {
    get() {
      const { level } = this;
      return function(...arguments_) {
        const styler = createStyler(getModelAnsi(model, levelMapping[level], "color", ...arguments_), ansi_styles_default.color.close, this[STYLER]);
        return createBuilder(this, styler, this[IS_EMPTY]);
      };
    }
  };
  const bgModel = "bg" + model[0].toUpperCase() + model.slice(1);
  styles2[bgModel] = {
    get() {
      const { level } = this;
      return function(...arguments_) {
        const styler = createStyler(getModelAnsi(model, levelMapping[level], "bgColor", ...arguments_), ansi_styles_default.bgColor.close, this[STYLER]);
        return createBuilder(this, styler, this[IS_EMPTY]);
      };
    }
  };
}
var proto = Object.defineProperties(() => {}, {
  ...styles2,
  level: {
    enumerable: true,
    get() {
      return this[GENERATOR].level;
    },
    set(level) {
      this[GENERATOR].level = level;
    }
  }
});
var createStyler = (open, close, parent) => {
  let openAll;
  let closeAll;
  if (parent === undefined) {
    openAll = open;
    closeAll = close;
  } else {
    openAll = parent.openAll + open;
    closeAll = close + parent.closeAll;
  }
  return {
    open,
    close,
    openAll,
    closeAll,
    parent
  };
};
var createBuilder = (self, _styler, _isEmpty) => {
  const builder = (...arguments_) => applyStyle(builder, arguments_.length === 1 ? "" + arguments_[0] : arguments_.join(" "));
  Object.setPrototypeOf(builder, proto);
  builder[GENERATOR] = self;
  builder[STYLER] = _styler;
  builder[IS_EMPTY] = _isEmpty;
  return builder;
};
var applyStyle = (self, string) => {
  if (self.level <= 0 || !string) {
    return self[IS_EMPTY] ? "" : string;
  }
  let styler = self[STYLER];
  if (styler === undefined) {
    return string;
  }
  const { openAll, closeAll } = styler;
  if (string.includes("\x1B")) {
    while (styler !== undefined) {
      string = stringReplaceAll(string, styler.close, styler.open);
      styler = styler.parent;
    }
  }
  const lfIndex = string.indexOf(`
`);
  if (lfIndex !== -1) {
    string = stringEncaseCRLFWithFirstIndex(string, closeAll, openAll, lfIndex);
  }
  return openAll + string + closeAll;
};
Object.defineProperties(createChalk.prototype, styles2);
var chalk = createChalk();
var chalkStderr = createChalk({ level: stderrColor ? stderrColor.level : 0 });
var source_default = chalk;

// src/feed.ts
function shortToolName(name) {
  return name.replace(/^mcp__db-mcp__/, "").replace(/^mcp__.*?__/, "");
}

class Feed {
  messages = [];
  seenIds = new Set;
  markdown;
  dirty = true;
  currentTurn = null;
  _prefixLines = [];
  constructor(theme) {
    this.markdown = new Markdown("", 1, 0, theme);
  }
  addMessage(msg) {
    if (this.seenIds.has(msg.id))
      return;
    this.seenIds.add(msg.id);
    if (msg.role === "tool") {
      if (this.currentTurn) {
        if (this.currentTurn.text && !this.currentTurn.text.endsWith(`
`)) {
          this.currentTurn.text += `

`;
        }
        this.currentTurn.tools.push(shortToolName(msg.text));
      }
    } else {
      this.messages.push(msg);
    }
    this.dirty = true;
    this.rebuildMarkdown();
  }
  updateLastTool(detail) {
    if (this.currentTurn && this.currentTurn.tools.length > 0) {
      this.currentTurn.tools[this.currentTurn.tools.length - 1] = detail;
      this.dirty = true;
      this.rebuildMarkdown();
    }
  }
  appendDelta(text) {
    if (this.currentTurn) {
      this.currentTurn.text += text;
      this.dirty = true;
      this.rebuildMarkdown();
    }
  }
  startAssistant(id) {
    if (this.currentTurn) {
      this.completeTurn();
    }
    this.currentTurn = { tools: [], text: "", completed: false };
    this.messages.push({ id, role: "assistant", text: "" });
    this.dirty = true;
    this.rebuildMarkdown();
  }
  completeTurn() {
    if (this.currentTurn) {
      let assistantMsg;
      for (let i = this.messages.length - 1;i >= 0; i--) {
        const m = this.messages[i];
        if (m.role === "assistant" && !m._completed) {
          assistantMsg = m;
          break;
        }
      }
      if (assistantMsg) {
        assistantMsg.text = this.currentTurn.text;
        assistantMsg._tools = [...this.currentTurn.tools];
        assistantMsg._completed = true;
      }
      this.currentTurn = null;
      this.dirty = true;
      this.rebuildMarkdown();
    }
  }
  clear() {
    this.messages = [];
    this.seenIds.clear();
    this.currentTurn = null;
    this.dirty = true;
    this.rebuildMarkdown();
  }
  get messageCount() {
    return this.messages.length;
  }
  invalidate() {
    this.dirty = true;
  }
  setPrefixLines(lines) {
    this._prefixLines = lines;
  }
  render(width) {
    return [...this._prefixLines, ...this.markdown.render(width)];
  }
  formatToolLine(tool) {
    return source_default.dim.yellow(`\u251C ${tool}`);
  }
  formatToolSummary(tools) {
    const preview = tools.slice(0, 3).join(", ");
    const suffix = tools.length > 3 ? "\u2026" : "";
    return source_default.dim.yellow(`\u251C ${tools.length} tools: ${preview}${suffix}`);
  }
  rebuildMarkdown() {
    const parts = [];
    for (const msg of this.messages) {
      switch (msg.role) {
        case "system":
          parts.push(msg.text);
          break;
        case "user":
          parts.push(`**> ${msg.text}**`);
          break;
        case "assistant": {
          const completed = msg._completed;
          const tools = completed ? msg._tools ?? [] : this.currentTurn?.tools ?? [];
          const text = completed ? msg.text : this.currentTurn?.text ?? "";
          if (tools.length > 0) {
            if (completed && tools.length > 3) {
              parts.push(this.formatToolSummary(tools));
            } else {
              parts.push(tools.map((t) => this.formatToolLine(t)).join(`
`));
            }
          }
          if (text) {
            let normalized = text;
            normalized = normalized.replace(/(?<!\n)\n(?!\n)/g, `

`);
            normalized = normalized.replace(/([.:])([A-Z])/g, `$1

$2`);
            parts.push(normalized);
          } else if (!completed) {
            parts.push("_thinking..._");
          }
          break;
        }
        case "error":
          parts.push(`**Error:** ${msg.text}`);
          break;
      }
    }
    this.markdown.setText(parts.join(`

`));
  }
}

// src/status-bar.ts
function formatTokens(n) {
  if (n >= 1e6)
    return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1000)
    return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

class StatusBar {
  state = {
    connection: "none",
    healthy: false,
    agent: "",
    agentConnected: false,
    contextUsed: 0,
    contextSize: 0,
    cost: 0,
    currency: "USD"
  };
  update(partial) {
    Object.assign(this.state, partial);
  }
  updateUsage(usage) {
    this.state.contextUsed = usage.used;
    this.state.contextSize = usage.size;
    this.state.cost += usage.cost;
    this.state.currency = usage.currency;
  }
  invalidate() {}
  render(width) {
    const health = this.state.healthy ? source_default.green("\u25CF") : source_default.red("\u25CF");
    const conn = this.state.connection || "none";
    const parts = [` ${health} ${conn}`];
    if (this.state.agent) {
      const dot = this.state.agentConnected ? source_default.green("\u25CF") : source_default.dim("\u25CB");
      parts.push(`${dot} ${this.state.agent}`);
    }
    if (this.state.contextUsed > 0) {
      const pct = Math.round(this.state.contextUsed / this.state.contextSize * 100);
      parts.push(`ctx ${formatTokens(this.state.contextUsed)}/${formatTokens(this.state.contextSize)} (${pct}%)`);
    }
    if (this.state.cost > 0) {
      parts.push(`$${this.state.cost.toFixed(2)}`);
    }
    const line = parts.join("  \u2502  ");
    const pad = Math.max(0, width - visibleLen(line));
    return [source_default.bgGray.white(line + " ".repeat(pad))];
  }
}
function visibleLen(str) {
  return str.replace(/\x1b\[[0-9;]*m/g, "").length;
}

// src/commands.ts
var SLASH_COMMANDS = [
  { name: "help", description: "show help" },
  { name: "clear", description: "clear the feed" },
  { name: "status", description: "server status" },
  { name: "doctor", description: "run connection health checks" },
  { name: "env", description: "securely store a secret (not shared with agent)" },
  { name: "connections", description: "list connections" },
  { name: "use", description: "switch connection" },
  { name: "playground", description: "install sample database" },
  { name: "init", description: "set up a new connection" },
  { name: "schema", description: "show tables" },
  { name: "rules", description: "list business rules" },
  { name: "examples", description: "list query examples" },
  { name: "metrics", description: "list metrics" },
  { name: "gaps", description: "list knowledge gaps" },
  { name: "sync", description: "sync vault with git" },
  { name: "agent", description: "agent status" },
  { name: "session", description: "show session info" },
  { name: "quit", description: "exit" }
];

// src/theme.ts
var selectListTheme = {
  selectedPrefix: (str) => source_default.bgBlue.white(str),
  selectedText: (str) => source_default.bgBlue.white(str),
  description: (str) => source_default.dim(str),
  scrollInfo: (str) => source_default.dim(str),
  noMatch: (str) => source_default.dim(str)
};
var editorTheme = {
  borderColor: (str) => source_default.dim(str),
  selectList: selectListTheme
};
var markdownTheme = {
  heading: (str) => source_default.bold(str),
  link: (str) => source_default.cyan.underline(str),
  linkUrl: (str) => source_default.dim(str),
  code: (str) => source_default.yellow(str),
  codeBlock: (str) => str,
  codeBlockBorder: (str) => source_default.dim(str),
  quote: (str) => source_default.italic(str),
  quoteBorder: (str) => source_default.dim(str),
  hr: (str) => source_default.dim(str),
  listBullet: (str) => source_default.dim(str),
  bold: (str) => source_default.bold(str),
  italic: (str) => source_default.italic(str),
  strikethrough: (str) => source_default.strikethrough(str),
  underline: (str) => source_default.underline(str)
};

// src/index.ts
import { resolve as resolve2, dirname as dirname4 } from "path";
import { fileURLToPath as fileURLToPath2 } from "url";
import { existsSync as existsSync2 } from "fs";
if (process.env.DB_MCP_DEBUG) {} else {
  console.log = (...args) => {
    try {
      appendFileSync3("/tmp/db-mcp-rpc.log", args.map(String).join(" ") + `
`);
    } catch {}
  };
}
process.on("unhandledRejection", (err) => {
  const msg = err instanceof Error ? err.message : String(err);
  try {
    feed.addMessage({ id: `unhandled-${Date.now()}`, role: "error", text: msg });
    tui.requestRender();
  } catch {}
});
process.on("uncaughtException", (err) => {
  __require("fs").appendFileSync("/tmp/db-mcp-tui-crash.log", `${new Date().toISOString()} UNCAUGHT: ${err.stack ?? err.message}
`);
});
var BASE_URL = process.env.DB_MCP_URL ?? "http://localhost:8080";
var FORCE_FTE = process.env.DB_MCP_FTE === "1";
var __dirname2 = dirname4(fileURLToPath2(import.meta.url));
var BUNDLED_AGENTS = [
  "claude-agent-acp",
  "codex-acp"
];
function resolveAgentCommand() {
  if (process.env.DB_MCP_AGENT) {
    return process.env.DB_MCP_AGENT.split(" ");
  }
  const searchDirs = [
    resolve2(__dirname2, "..", "node_modules", ".bin"),
    resolve2(__dirname2, "node_modules", ".bin")
  ];
  for (const binDir of searchDirs) {
    for (const name of BUNDLED_AGENTS) {
      const localBin = resolve2(binDir, name);
      if (existsSync2(localBin)) {
        return [localBin];
      }
    }
  }
  return ["claude-agent-acp"];
}
var AGENT_CMD = resolveAgentCommand();
async function checkAgentPrerequisites() {
  const { execFileSync } = await import("child_process");
  const { which: which2 } = await Promise.resolve().then(() => (init_preflight(), exports_preflight));
  const agentBin = AGENT_CMD[0];
  if (!agentBin.includes("/") && !which2(agentBin)) {
    return [
      `**ACP adapter not found:** \`${agentBin}\``,
      "",
      "The TUI needs an ACP adapter to connect to an AI agent.",
      "Install it with:",
      "```",
      "npm i -g @agentclientprotocol/claude-agent-acp",
      "```"
    ].join(`
`);
  }
  if (!which2("claude")) {
    return [
      "**Claude Code not found.**",
      "",
      "The TUI uses Claude Code as its AI agent. Install it:",
      "```",
      "npm i -g @anthropic-ai/claude-code",
      "```",
      "Then run `claude` once to authenticate."
    ].join(`
`);
  }
  try {
    const out = execFileSync("claude", ["auth", "status"], {
      timeout: 5000,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"]
    });
    const status = JSON.parse(out);
    if (!status.loggedIn) {
      return [
        "**Claude Code is not authenticated.**",
        "",
        "Run this in your terminal to log in:",
        "```",
        "claude auth login",
        "```",
        "Then restart the TUI."
      ].join(`
`);
    }
  } catch {}
  return null;
}
var terminal = new ProcessTerminal;
var tui = new TUI(terminal, true);
var feed = new Feed(markdownTheme);
var editor = new Editor(tui, editorTheme, { paddingX: 1 });
var statusBar = new StatusBar;
var agent = new Agent({
  command: AGENT_CMD,
  mcpUrl: `${BASE_URL}/mcp`
});
var slashProvider = new CombinedAutocompleteProvider(SLASH_COMMANDS);
editor.setAutocompleteProvider(slashProvider);
tui.addInputListener((data) => {
  if (matchesKey(data, "ctrl+c") || data === "\x03") {
    shutdown();
    return { consume: true };
  }
  if (matchesKey(data, "escape") && promptRunning) {
    agent.cancel();
    feed.addMessage({
      id: `cancel-${Date.now()}`,
      role: "system",
      text: "_Cancelled._"
    });
    setTimeout(() => tui.requestRender(), 0);
    return { consume: true };
  }
  return;
});
tui.addChild(feed);
tui.addChild(editor);
tui.addChild(statusBar);
tui.setFocus(editor);
var logoRaw = loadPrompt("logo.ans");
var logoLines = logoRaw ? logoRaw.replace(/\[\?25[lh]/g, "").split(`
`).filter((l) => l.length > 0) : [];
feed.setPrefixLines([...logoLines, ""]);
var hasConnections = await (async () => {
  try {
    const resp = await fetch(`${BASE_URL}/api/connections/list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(2000)
    });
    const data = await resp.json();
    return (data.connections?.length ?? 0) > 0;
  } catch {
    return false;
  }
})();
var shouldRunFte = FORCE_FTE || !hasConnections;
if (shouldRunFte) {
  feed.addMessage({
    id: "welcome",
    role: "system",
    text: [
      "**db-mcp** by ApeLogic",
      "",
      "_Welcome! Let me help you get started..._"
    ].join(`
`)
  });
} else {
  feed.addMessage({
    id: "welcome",
    role: "system",
    text: [
      "**db-mcp** by ApeLogic",
      "",
      "Type a question to query your data. Type `/` for commands.",
      "_Press Ctrl+C to exit. ESC to cancel._"
    ].join(`
`)
  });
}
var currentAssistantId = null;
function handleAgentEvent(event) {
  switch (event.type) {
    case "text_delta":
      if (currentAssistantId) {
        feed.appendDelta(event.delta);
      }
      break;
    case "thinking_delta":
      break;
    case "tool_start": {
      const name = event.tool;
      let detail = name;
      if (event.params != null && typeof event.params === "object") {
        const p = event.params;
        const hint = p.command ?? p.query ?? p.sql ?? p.pattern ?? p.file_path ?? p.intent ?? p.connection ?? p.name;
        if (hint) {
          const s = String(hint).replace(/\n/g, " ").trim();
          detail = s.length > 60 ? `${name}: ${s.slice(0, 60)}\u2026` : `${name}: ${s}`;
        }
      }
      feed.addMessage({
        id: `tool-${Date.now()}-${Math.random()}`,
        role: "tool",
        text: detail
      });
      break;
    }
    case "tool_update": {
      feed.updateLastTool(event.detail);
      break;
    }
    case "tool_end":
      break;
    case "error":
      feed.addMessage({
        id: `agent-err-${Date.now()}`,
        role: "error",
        text: event.message
      });
      break;
    case "usage":
      statusBar.updateUsage(event.usage);
      break;
    case "done":
      currentAssistantId = null;
      break;
  }
  setTimeout(() => tui.requestRender(), 0);
}
var promptRunning = false;
var pendingMessages = [];
editor.onSubmit = async (text) => {
  const trimmed = text.trim();
  if (!trimmed)
    return;
  editor.setText("");
  editor.addToHistory(trimmed);
  if (trimmed.startsWith("/")) {
    await handleCommand(trimmed);
    tui.requestRender();
    return;
  }
  if (promptRunning) {
    pendingMessages.push(trimmed);
    feed.addMessage({
      id: `queued-${Date.now()}`,
      role: "user",
      text: `${trimmed}  _(queued)_`
    });
    setTimeout(() => tui.requestRender(), 0);
    return;
  }
  await runPrompt(trimmed);
};
async function runPrompt(text) {
  promptRunning = true;
  try {
    await handlePrompt(text);
  } finally {
    promptRunning = false;
    feed.completeTurn();
    currentAssistantId = null;
    setTimeout(() => tui.requestRender(), 0);
  }
  while (pendingMessages.length > 0) {
    const next = pendingMessages.shift();
    promptRunning = true;
    try {
      await handlePrompt(next);
    } finally {
      promptRunning = false;
      feed.completeTurn();
      currentAssistantId = null;
      setTimeout(() => tui.requestRender(), 0);
    }
  }
}
async function handleCommand(raw) {
  const [cmd, ...rest] = raw.split(" ");
  const arg = rest.join(" ").trim();
  switch (cmd) {
    case "/help":
      feed.addMessage({
        id: `help-${Date.now()}`,
        role: "system",
        text: [
          "**Commands:**",
          "",
          "| Command | Description |",
          "|---------|-------------|",
          ...SLASH_COMMANDS.map((c) => `| \`/${c.name}\` | ${c.description} |`),
          "",
          "Or type any question in natural language."
        ].join(`
`)
      });
      break;
    case "/clear":
      feed.clear();
      break;
    case "/status":
      await refreshStatus();
      feed.addMessage({
        id: `status-${Date.now()}`,
        role: "system",
        text: [
          `Server: ${statusBar["state"].healthy ? "\u2713 healthy" : "\u2717 disconnected"}`,
          `Connection: ${statusBar["state"].connection || "none"}`,
          `Agent: ${agent.connected ? "\u2713 connected" : "\u25CB not connected"} (${agent.commandName})`,
          agent.sessionId ? `Session: ${agent.sessionId}` : ""
        ].filter(Boolean).join(" \xB7 ")
      });
      break;
    case "/agent":
      if (agent.connected) {
        feed.addMessage({
          id: `agent-${Date.now()}`,
          role: "system",
          text: `Agent connected: \`${agent.commandName}\` \xB7 Session: ${agent.sessionId}`
        });
      } else {
        feed.addMessage({
          id: `agent-${Date.now()}`,
          role: "system",
          text: [
            `Agent: \`${agent.commandName}\` \u2014 not connected.`,
            "",
            "Type any question to auto-connect, or set agent with:",
            "`DB_MCP_AGENT=claude-agent-acp db-mcp tui`"
          ].join(`
`)
        });
      }
      break;
    case "/quit":
      shutdown();
      break;
    case "/doctor":
      await runCli("db-mcp doctor");
      break;
    case "/env": {
      const parts = arg.split(" ");
      if (parts.length < 3) {
        feed.addMessage({
          id: `env-err-${Date.now()}`,
          role: "error",
          text: "Usage: `/env <connection> <KEY> <value>`\nExample: `/env nova DATABASE_URL postgres://user:pass@host/db`"
        });
        break;
      }
      const [connName, key, ...valueParts] = parts;
      const value = valueParts.join(" ");
      try {
        const { mkdirSync: mkdirSync2, writeFileSync: writeFileSync2, readFileSync: readFileSync2, existsSync: existsSync3 } = await import("fs");
        const { homedir: homedir3 } = await import("os");
        const { join: join5 } = await import("path");
        const connDir = join5(homedir3(), ".db-mcp", "connections", connName);
        mkdirSync2(connDir, { recursive: true });
        const envFile = join5(connDir, ".env");
        let lines = [];
        if (existsSync3(envFile)) {
          lines = readFileSync2(envFile, "utf8").split(`
`).filter((l) => !l.startsWith(`${key}=`));
        }
        lines.push(`${key}=${value}`);
        writeFileSync2(envFile, lines.filter(Boolean).join(`
`) + `
`);
        feed.addMessage({
          id: `env-ok-${Date.now()}`,
          role: "system",
          text: `Secret \`${key}\` written to \`~/.db-mcp/connections/${connName}/.env\``
        });
      } catch (err) {
        feed.addMessage({
          id: `env-fail-${Date.now()}`,
          role: "error",
          text: `Failed to write secret: ${err instanceof Error ? err.message : String(err)}`
        });
      }
      break;
    }
    case "/playground":
      feed.addMessage({ id: `pg-${Date.now()}`, role: "system", text: "_Installing playground database..._" });
      tui.requestRender();
      await runCli("db-mcp playground install");
      await runCli("db-mcp use playground");
      await refreshStatus();
      feed.addMessage({
        id: `pg-done-${Date.now()}`,
        role: "system",
        text: "Playground ready! Try asking: _How many albums does each artist have?_"
      });
      break;
    case "/init":
      await runPrompt(arg ? `I want to set up a new db-mcp connection called "${arg}". Guide me through it.` : "I want to set up a new db-mcp database connection. Ask me what database I use and help me configure it step by step.");
      break;
    case "/connections":
      await runCli("db-mcp list");
      break;
    case "/use":
      if (!arg) {
        feed.addMessage({ id: `e-${Date.now()}`, role: "error", text: "Usage: /use CONNECTION_NAME" });
        break;
      }
      await runCli(`db-mcp use ${arg}`);
      await refreshStatus();
      break;
    case "/schema":
      await runCli(arg ? `db-mcp schema ${arg}` : "db-mcp schema show");
      break;
    case "/rules":
      await runCli(arg ? `db-mcp rules ${arg}` : "db-mcp rules list");
      break;
    case "/examples":
      await runCli(arg ? `db-mcp examples ${arg}` : "db-mcp examples list");
      break;
    case "/metrics":
      await runCli(arg ? `db-mcp metrics ${arg}` : "db-mcp metrics list");
      break;
    case "/gaps":
      await runCli(arg ? `db-mcp gaps ${arg}` : "db-mcp gaps list");
      break;
    case "/sync":
      await runCli("db-mcp sync");
      break;
    case "/model":
      feed.addMessage({ id: `m-${Date.now()}`, role: "system", text: "Model selection requires an active agent session." });
      break;
    case "/session":
      feed.addMessage({
        id: `s-${Date.now()}`,
        role: "system",
        text: agent.sessionId ? `Session: ${agent.sessionId} \xB7 Agent: ${agent.commandName}` : "No active session. Type a question to start."
      });
      break;
    default:
      feed.addMessage({
        id: `err-${Date.now()}`,
        role: "error",
        text: `Unknown command: ${cmd}`
      });
  }
}
async function runCli(command) {
  const { handleCreateTerminal: handleCreateTerminal2, handleTerminalOutput: handleTerminalOutput2, handleReleaseTerminal: handleReleaseTerminal2 } = await Promise.resolve().then(() => (init_terminal(), exports_terminal));
  const [cmd, ...args] = command.split(" ");
  const { terminalId } = handleCreateTerminal2({ command: cmd, args });
  const result = await handleTerminalOutput2({ terminalId });
  handleReleaseTerminal2({ terminalId });
  let output = result.output.trim();
  if (output) {
    output = output.replace(/Restart Claude Desktop to apply changes\.?\n?/g, "").replace(/^[\u2713\u2717\u25CF] /gm, "").replace(/'/g, "").trim();
    if (output) {
      feed.addMessage({
        id: `cli-${Date.now()}`,
        role: "system",
        text: output
      });
    }
  }
  if (result.exitStatus && result.exitStatus.exitCode !== 0 && result.exitStatus.exitCode !== 2) {
    feed.addMessage({
      id: `cli-err-${Date.now()}`,
      role: "error",
      text: `Exit code: ${result.exitStatus.exitCode}`
    });
  }
  setTimeout(() => tui.requestRender(), 0);
}
async function handlePrompt(text) {
  feed.addMessage({
    id: `user-${Date.now()}`,
    role: "user",
    text
  });
  if (!agent.connected) {
    const problem = await checkAgentPrerequisites();
    if (problem) {
      feed.addMessage({
        id: `preflight-${Date.now()}`,
        role: "error",
        text: problem
      });
      tui.requestRender();
      return;
    }
    feed.addMessage({
      id: `connecting-${Date.now()}`,
      role: "system",
      text: `_Connecting to agent \`${agent.commandName}\`..._`
    });
    tui.requestRender();
    try {
      await agent.connect(handleAgentEvent, statusBar.state.connection !== "none" ? statusBar.state.connection : undefined);
      statusBar.update({ agent: agent.commandName, agentConnected: true });
      feed.addMessage({
        id: `connected-${Date.now()}`,
        role: "system",
        text: `Agent connected. Session: ${agent.sessionId}`
      });
      tui.requestRender();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      feed.addMessage({
        id: `agent-fail-${Date.now()}`,
        role: "error",
        text: `Failed to connect to agent: ${msg}`
      });
      tui.requestRender();
      return;
    }
  }
  currentAssistantId = `assistant-${Date.now()}`;
  feed.startAssistant(currentAssistantId);
  tui.requestRender();
  try {
    await agent.prompt(text);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    feed.addMessage({
      id: `prompt-err-${Date.now()}`,
      role: "error",
      text: `Agent error: ${msg}`
    });
  }
}
async function refreshStatus() {
  try {
    const resp = await fetch(`${BASE_URL}/health`, { signal: AbortSignal.timeout(2000) });
    statusBar.update({ healthy: resp.ok });
    const connResp = await fetch(`${BASE_URL}/api/connections/list`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
      signal: AbortSignal.timeout(2000)
    });
    const connData = await connResp.json();
    const active = connData.connections?.find((c) => c.isActive);
    statusBar.update({ connection: active?.name ?? "none" });
  } catch {
    statusBar.update({ healthy: false });
  }
}
var pollInterval = setInterval(() => {
  refreshStatus().then(() => tui.requestRender());
}, 3000);
async function shutdown() {
  clearInterval(pollInterval);
  await agent.disconnect();
  process.stdout.write("\x1B[=0u");
  process.stdout.write("\x1B[<u");
  process.stdout.write("\x1B[>0m");
  process.stdout.write("\x1B[?25h");
  await terminal.drainInput(500, 100);
  tui.stop();
  await new Promise((resolve3) => setTimeout(resolve3, 150));
  process.exit(0);
}
process.on("SIGINT", () => shutdown());
process.on("SIGTERM", () => shutdown());
refreshStatus().then(() => {
  tui.start();
  tui.requestRender();
  if (shouldRunFte) {
    const ftePrompt = loadPrompt("fte-trigger.md") || "Help me get started";
    editor.setText(ftePrompt);
  }
});
