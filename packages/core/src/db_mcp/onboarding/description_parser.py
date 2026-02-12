"""Universal parser for table/column descriptions by matching against known schema.

Treats ALL input as unstructured text. Extracts descriptions by matching
against known table/column names from the discovered schema.
No JSON/YAML/CSV structure parsing - just text pattern matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class _TableMatch:
    full_name: str
    start: int
    end: int
    matched_text: str


def parse_descriptions(
    text: str, known_tables: dict[str, list[str]]
) -> tuple[dict[str, dict], list[str]]:
    """Parse descriptions from any text format by matching against known schema.

    Args:
        text: Input text in any format (JSON, YAML, plain text, markdown, etc.)
        known_tables: {"schema.table_name": ["col1", "col2", ...]}

    Returns:
        (result_dict, warnings)
    """
    text = (text or "").strip()
    if not text:
        return {}, ["Empty input"]
    if not known_tables:
        return {}, ["No known tables provided for matching"]

    warnings: list[str] = []
    warnings.extend(_heuristic_warnings(text))

    mentions = _find_all_table_mentions(text, known_tables)
    if not mentions:
        if warnings:
            return {}, warnings
        return {}, ["No matching tables found in the provided text"]

    # Build sections
    sections: list[tuple[_TableMatch, str]] = []
    for i, m in enumerate(mentions):
        end = mentions[i + 1].start if i + 1 < len(mentions) else len(text)
        sections.append((m, text[m.start:end]))

    out: dict[str, dict] = {}
    for m, section in sections:
        cols = known_tables.get(m.full_name, [])
        offset = m.end - m.start
        table_desc = _extract_table_description(section, offset)
        col_descs = _extract_column_descriptions(section, cols)
        if table_desc or col_descs:
            out[m.full_name] = {"description": table_desc, "columns": col_descs}

    if not out:
        if warnings:
            return {}, warnings
        return {}, ["No matching tables found in the provided text"]
    return out, warnings


# --------------- Table name matching ---------------


def _table_aliases(full_name: str) -> list[str]:
    parts = full_name.split(".")
    aliases = [full_name]
    if len(parts) >= 2:
        aliases.append(".".join(parts[-2:]))
    aliases.append(parts[-1])
    seen: set[str] = set()
    return [a for a in aliases if not (a in seen or seen.add(a))]  # type: ignore


def _fuzzy_pattern(phrase: str) -> re.Pattern[str]:
    norm = phrase.lower().replace("_", " ").strip()
    parts = [re.escape(p) for p in norm.split() if p]
    if not parts:
        return re.compile(r"a^")
    body = r"[_ ]+".join(parts)
    return re.compile(rf"(?<![A-Za-z0-9_.]){body}(?![A-Za-z0-9_])", re.IGNORECASE)


def _find_all_table_mentions(
    text: str, known_tables: dict[str, list[str]]
) -> list[_TableMatch]:
    alias_entries: list[tuple[str, str]] = []
    for full in known_tables:
        for alias in _table_aliases(full):
            alias_entries.append((full, alias))
    alias_entries.sort(key=lambda x: len(x[1]), reverse=True)

    raw: list[_TableMatch] = []
    for full, alias in alias_entries:
        pat = _fuzzy_pattern(alias)
        for m in pat.finditer(text):
            raw.append(_TableMatch(full, m.start(), m.end(), m.group(0)))

    raw.sort(key=lambda m: (m.start, -(m.end - m.start)))
    pruned: list[_TableMatch] = []
    last_end = -1
    for m in raw:
        if m.start < last_end:
            continue
        pruned.append(m)
        last_end = m.end

    seen: set[str] = set()
    unique: list[_TableMatch] = []
    for m in pruned:
        if m.full_name not in seen:
            seen.add(m.full_name)
            unique.append(m)
    unique.sort(key=lambda m: m.start)
    return unique


# --------------- Table description extraction ---------------


def _extract_table_description(section: str, name_offset: int) -> str:
    after = section[name_offset:]

    # 1) Explicit "description:" field
    m = re.search(
        r"""["']?description["']?\s*:\s*(\|)?\s*(.+?)(?:\s*$)""",
        after[:600],
        re.IGNORECASE | re.MULTILINE,
    )
    if m:
        is_block = bool(m.group(1))
        inline = (m.group(2) or "").strip()
        if is_block and not inline:
            block = _read_indented_block(after, m.end())
            if block:
                return block
        desc = _clean(inline) if inline else ""
        # Stop at "columns:" keyword
        desc = re.split(r"\bcolumns\b\s*:", desc, maxsplit=1, flags=re.IGNORECASE)[0].strip()
        if len(desc) > 2:
            return desc

    # 2) "info:" or "summary:" field
    for field in ("info", "summary", "desc"):
        m = re.search(
            rf"""["']?{field}["']?\s*:\s*["']?(.+?)(?:["']?\s*[,}}\n]|$)""",
            after[:600],
            re.IGNORECASE,
        )
        if m:
            desc = _clean(m.group(1))
            if len(desc) > 2:
                return desc

    # 3) Same-line after separator: "table: description"
    m = re.match(r"""["\s]*[:=\-|>]+\s*["']?(.+?)(?:["']?\s*$)""", after, re.MULTILINE)
    if m:
        desc = _clean(m.group(1))
        if desc and len(desc) > 3 and not re.match(
            r"^(description|columns?|tables?|schema|info|fields?)\s*[:=|]?\s*$",
            desc,
            re.IGNORECASE,
        ):
            return desc

    # 4) Prose: "table contains/stores/is ..."
    first_line = after.split("\n")[0].strip() if after else ""
    if first_line:
        m = re.match(
            r"\s*(?:table\s+)?(contains?|stores?|is|has|holds?|tracks?|maintains?)\s+(.+)",
            first_line,
            re.IGNORECASE,
        )
        if m:
            return _clean(m.group(0).strip())

    return ""


def _read_indented_block(text: str, pos: int) -> str:
    lines = text[pos:].splitlines()
    out: list[str] = []
    for ln in lines:
        if not ln.strip():
            if out:
                out.append("")
            continue
        if re.match(r"^\s+", ln):
            out.append(ln.strip())
            continue
        break
    return "\n".join(out).strip()


# --------------- Column description extraction ---------------


def _extract_column_descriptions(
    section: str, known_cols: list[str]
) -> dict[str, str]:
    result: dict[str, str] = {}
    lines = section.splitlines()

    for col in known_cols:
        pat = _fuzzy_pattern(col)
        candidates: list[tuple[int, str]] = []  # (priority, desc)

        for i, line in enumerate(lines):
            m = pat.search(line)
            if not m:
                continue

            # Check if column name is at "key position" (start of meaningful content)
            stripped = line.lstrip()
            cleaned_start = re.sub(r"""^[-*\s"']+""", "", stripped)
            col_at_key_pos = bool(pat.match(cleaned_start))

            # YAML-style nested: "col:\n  description: value" (only at key pos)
            if col_at_key_pos:
                desc = _col_desc_yaml_style(lines, i)
                if desc:
                    candidates.append((0, desc))
                    continue

            # Key-value on same line
            desc = _col_desc_from_line(line, m)
            if desc and col_at_key_pos:
                candidates.append((1, desc))
            elif desc:
                candidates.append((3, desc))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            result[col] = candidates[0][1]

    return result


def _col_desc_from_line(line: str, match: re.Match) -> str:
    after = line[match.end() :].strip()

    # Strip optional closing quote from JSON key
    after = after.lstrip("\"'")

    # Require a separator to avoid false positives in prose
    if not re.match(r"\s*[:=\-|>]|^\s*->", after):
        return ""

    # Remove separators
    after = re.sub(r"""^[\s\-:*|>"']+""", "", after).strip()

    # Parenthetical: col (desc)
    pm = re.match(r"\(([^)]{3,})\)", after)
    if pm:
        return pm.group(1).strip()

    if after:
        # For JSON-like content, stop at '", ' boundary
        m2 = re.match(r'^([^"]+)"', after)
        if m2 and ',' in after:
            return _clean(m2.group(1))
        return _clean(after)

    return ""


def _col_desc_yaml_style(lines: list[str], idx: int) -> str:
    # Only if this line ends with a bare colon (YAML key)
    if not re.search(r":\s*$", lines[idx]):
        return ""
    for j in range(idx + 1, min(len(lines), idx + 8)):
        ln = lines[j]
        m = re.search(r"\bdescription\b\s*:\s*(.+)$", ln, re.IGNORECASE)
        if m:
            return _clean(m.group(1))
        # Stop at next top-level key
        if re.match(r"^\S+\s*:", ln):
            break
    return ""


# --------------- Utilities ---------------


def _heuristic_warnings(text: str) -> list[str]:
    warnings: list[str] = []
    for i, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        # Lines that look like a key but missing the key.
        if s.startswith(":"):
            warnings.append(f"Line {i}: empty key before ':'")
        # obvious garbage marker
        if "some garbage" in s.lower():
            warnings.append(f"Line {i}: unparseable line")
    return warnings


def _clean(text: str) -> str:
    """Clean extracted description text."""
    text = text.strip()
    # If it looks like a JSON quoted string, extract it
    m = re.match(r'^"([^"]+)"', text)
    if m:
        return m.group(1).strip()
    # Remove surrounding quotes
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    # Remove trailing structural characters
    text = re.sub(r"""[";,{}()\[\]']+$""", "", text).strip()
    # Remove leading bullets
    text = re.sub(r"^[-*|>]\s*", "", text).strip()
    return text
