/**
 * Theme for db-mcp TUI — minimal, matching Claude Code's aesthetic.
 */
import chalk from "chalk";
import type { EditorTheme, MarkdownTheme, SelectListTheme } from "@mariozechner/pi-tui";

export const selectListTheme: SelectListTheme = {
  selectedPrefix: (str: string) => chalk.bgBlue.white(str),
  selectedText: (str: string) => chalk.bgBlue.white(str),
  description: (str: string) => chalk.dim(str),
  scrollInfo: (str: string) => chalk.dim(str),
  noMatch: (str: string) => chalk.dim(str),
};

export const editorTheme: EditorTheme = {
  borderColor: (str: string) => chalk.dim(str),
  selectList: selectListTheme,
};

export const markdownTheme: MarkdownTheme = {
  heading: (str: string) => chalk.bold(str),
  link: (str: string) => chalk.cyan.underline(str),
  linkUrl: (str: string) => chalk.dim(str),
  code: (str: string) => chalk.yellow(str),
  codeBlock: (str: string) => str,
  codeBlockBorder: (str: string) => chalk.dim(str),
  quote: (str: string) => chalk.italic(str),
  quoteBorder: (str: string) => chalk.dim(str),
  hr: (str: string) => chalk.dim(str),
  listBullet: (str: string) => chalk.dim(str),
  bold: (str: string) => chalk.bold(str),
  italic: (str: string) => chalk.italic(str),
  strikethrough: (str: string) => chalk.strikethrough(str),
  underline: (str: string) => chalk.underline(str),
};
