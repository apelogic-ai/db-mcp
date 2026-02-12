"""Universal parser for table/column descriptions in multiple formats."""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

import yaml

logger = logging.getLogger(__name__)


def parse_descriptions(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parse descriptions from various text formats.
    
    Tries multiple formats in order:
    1. JSON (strict)
    2. YAML (nested)
    3. Text-based formats (key-value pairs, markdown tables, CSV-like)
    
    Args:
        text: Input text in any supported format
        
    Returns:
        Tuple of (parsed_dict, warnings)
        - parsed_dict: Normalized dict in format {"schema.table": {"description": "...", "columns": {"col": "..."}}}
        - warnings: List of warning messages for anything that couldn't be parsed
    """
    text = text.strip()
    if not text:
        return {}, ["Empty input"]
    
    warnings = []
    
    # Try JSON first
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            normalized, json_warnings = _normalize_structure(parsed)
            return normalized, json_warnings
        else:
            warnings.append("JSON parsed but result is not a dictionary")
    except json.JSONDecodeError:
        pass  # Not JSON, continue
    
    # Try YAML second
    try:
        parsed = yaml.safe_load(text)
        if isinstance(parsed, dict):
            normalized, yaml_warnings = _normalize_structure(parsed)
            return normalized, yaml_warnings
        else:
            warnings.append("YAML parsed but result is not a dictionary")
    except yaml.YAMLError:
        pass  # Not YAML, continue
    
    # Fall back to text parsing
    result, text_warnings = _parse_text_formats(text)
    warnings.extend(text_warnings)
    
    return result, warnings


def _normalize_structure(parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Normalize parsed data to expected format.
    
    Expected format:
    {
        "schema.table": {
            "description": "table description",
            "columns": {
                "col1": "column description",
                "col2": "column description"
            }
        }
    }
    """
    warnings = []
    result = {}
    
    for key, value in parsed.items():
        if not isinstance(value, dict):
            # Simple string value - treat as table description only
            if isinstance(value, str):
                result[key] = {"description": value, "columns": {}}
            else:
                warnings.append(f"Skipped {key}: value must be string or object")
            continue
        
        # It's a dict - normalize the structure
        table_entry = {"description": "", "columns": {}}
        
        # Handle description
        if "description" in value:
            if isinstance(value["description"], str):
                table_entry["description"] = value["description"]
            else:
                warnings.append(f"Skipped description for {key}: must be string")
        
        # Handle columns
        if "columns" in value:
            if isinstance(value["columns"], dict):
                for col_name, col_desc in value["columns"].items():
                    if isinstance(col_desc, str):
                        table_entry["columns"][col_name] = col_desc
                    else:
                        warnings.append(f"Skipped column {key}.{col_name}: description must be string")
            else:
                warnings.append(f"Skipped columns for {key}: must be object")
        
        result[key] = table_entry
    
    return result, warnings


def _parse_text_formats(text: str) -> Tuple[Dict[str, Any], List[str]]:
    """Parse various text formats using best-effort heuristics."""
    warnings = []
    result = {}
    
    lines = text.split('\n')
    
    # Try to detect format and parse accordingly
    if _looks_like_csv(lines):
        csv_result, csv_warnings = _parse_csv_format(lines)
        result.update(csv_result)
        warnings.extend(csv_warnings)
    
    if _looks_like_markdown_table(lines):
        md_result, md_warnings = _parse_markdown_table(lines)
        result.update(md_result)
        warnings.extend(md_warnings)
    
    # Always try key-value parsing as fallback
    kv_result, kv_warnings = _parse_key_value_lines(lines)
    result.update(kv_result)
    warnings.extend(kv_warnings)
    
    if not result:
        warnings.append("Could not parse any table descriptions from input")
    
    return result, warnings


def _looks_like_csv(lines: List[str]) -> bool:
    """Check if input looks like CSV format."""
    if len(lines) < 2:
        return False
    
    # Look for header that might be table,description or similar
    header_line = lines[0].strip()
    if ',' in header_line:
        header_parts = [p.strip().lower() for p in header_line.split(',')]
        return any('table' in part for part in header_parts) and any('desc' in part for part in header_parts)
    
    return False


def _looks_like_markdown_table(lines: List[str]) -> bool:
    """Check if input contains markdown tables."""
    for line in lines:
        if re.match(r'^\s*\|.*\|.*\|\s*$', line):
            return True
    return False


def _parse_csv_format(lines: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Parse CSV-like format: table,description"""
    warnings = []
    result = {}
    
    if not lines:
        return result, warnings
    
    # Parse header to find table and description columns
    header = lines[0].strip()
    if not header:
        warnings.append("CSV: Empty header line")
        return result, warnings
    
    header_parts = [p.strip() for p in header.split(',')]
    table_col_idx = None
    desc_col_idx = None
    
    for i, part in enumerate(header_parts):
        part_lower = part.lower()
        if 'table' in part_lower and table_col_idx is None:
            table_col_idx = i
        elif 'desc' in part_lower and desc_col_idx is None:
            desc_col_idx = i
    
    if table_col_idx is None or desc_col_idx is None:
        warnings.append("CSV: Could not find table and description columns")
        return result, warnings
    
    # Parse data rows
    for line_no, line in enumerate(lines[1:], 2):
        line = line.strip()
        if not line:
            continue
        
        parts = [p.strip() for p in line.split(',')]
        if len(parts) <= max(table_col_idx, desc_col_idx):
            warnings.append(f"CSV line {line_no}: Not enough columns")
            continue
        
        table_name = parts[table_col_idx]
        description = parts[desc_col_idx]
        
        if table_name and description:
            result[table_name] = {"description": description, "columns": {}}
    
    return result, warnings


def _parse_markdown_table(lines: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Parse markdown table format."""
    warnings = []
    result = {}
    
    # Find table boundaries and parse headers
    in_table = False
    headers = []
    table_col_idx = None
    desc_col_idx = None
    
    for line in lines:
        line = line.strip()
        
        if re.match(r'^\s*\|.*\|.*\|\s*$', line):
            if not in_table:
                # This is the header row
                in_table = True
                headers = [h.strip() for h in line.split('|')[1:-1]]  # Remove empty first/last
                
                # Find table and description columns
                for i, header in enumerate(headers):
                    header_lower = header.lower()
                    if 'table' in header_lower and table_col_idx is None:
                        table_col_idx = i
                    elif 'desc' in header_lower and desc_col_idx is None:
                        desc_col_idx = i
                
                if table_col_idx is None or desc_col_idx is None:
                    warnings.append("Markdown table: Could not find table and description columns")
                    in_table = False
                    continue
                
            elif re.match(r'^\s*\|[\s\-:]+\|\s*$', line):
                # This is the separator row, skip it
                continue
            else:
                # This is a data row
                parts = [p.strip() for p in line.split('|')[1:-1]]
                
                if len(parts) <= max(table_col_idx, desc_col_idx):
                    warnings.append("Markdown table: Data row has insufficient columns")
                    continue
                
                table_name = parts[table_col_idx]
                description = parts[desc_col_idx]
                
                if table_name and description:
                    result[table_name] = {"description": description, "columns": {}}
        else:
            in_table = False
    
    return result, warnings


def _parse_key_value_lines(lines: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Parse key-value format lines with various separators."""
    warnings = []
    result = {}
    current_table = None
    current_columns = {}
    
    for line_no, line in enumerate(lines, 1):
        original_line = line
        line = line.strip()
        
        if not line or line.startswith('#'):
            continue
        
        # Check if this line is indented (indicates columns under a table)
        is_indented = len(original_line) - len(original_line.lstrip()) > 0
        
        # Try different separators
        separator = None
        for sep in [':', '=', '->', '|']:
            if sep in line:
                separator = sep
                break
        
        if not separator:
            warnings.append(f"Line {line_no}: No recognized separator found")
            continue
        
        # Split on first occurrence of separator
        parts = line.split(separator, 1)
        if len(parts) != 2:
            warnings.append(f"Line {line_no}: Could not split into key and value")
            continue
        
        key = parts[0].strip()
        value = parts[1].strip()
        
        if not key or not value:
            warnings.append(f"Line {line_no}: Empty key or value")
            continue
        
        if is_indented and current_table:
            # This is a column description
            current_columns[key] = value
        else:
            # Save previous table if we have one with collected columns
            if current_table:
                if current_table not in result:
                    result[current_table] = {"description": "", "columns": current_columns.copy()}
                else:
                    result[current_table]["columns"].update(current_columns)
            
            # Start new table
            current_table = key
            result[current_table] = {"description": value, "columns": {}}
            current_columns = {}
    
    # Save final table
    if current_table and current_columns:
        if current_table not in result:
            result[current_table] = {"description": "", "columns": current_columns}
        else:
            result[current_table]["columns"].update(current_columns)
    
    return result, warnings