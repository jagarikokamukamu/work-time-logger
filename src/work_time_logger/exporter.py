"""Export module for Work Time Logger.

This module provides functionality to aggregate and export time logs into
formatted CSV files. It supports regex-based extraction from job codes
and Jinja2-based template rendering for notes and columns.
"""

import csv
import math
import os
import re
import tomllib
from datetime import datetime
from itertools import groupby

from jinja2 import Environment, Undefined

from . import operations

# Use a silent Undefined so missing vars render as empty string
_jinja_env = Environment(undefined=Undefined, autoescape=True)


def _render(template_str: str, context: dict) -> str:
    """Render a Jinja2 template string with the given context.

    Args:
        template_str (str): The Jinja2 template string to render.
        context (dict): The dictionary of variables for the template.

    Returns:
        str: The rendered string, or an empty string if rendering fails.
    """
    try:
        return _jinja_env.from_string(template_str).render(**context)
    except Exception:
        return ""


def _apply_rounding(value: float, precision: int, method: str) -> float:
    """Apply rounding method (round/floor/ceil) to a value.

    Args:
        value (float): The numeric value to round.
        precision (int): Number of decimal places.
        method (str): Rounding method: 'round', 'floor', or 'ceil'.

    Returns:
        float: The rounded value.
    """
    factor = 10**precision
    if method == "floor":
        return math.floor(value * factor) / factor
    elif method == "ceil":
        return math.ceil(value * factor) / factor
    else:
        return round(value, precision)


DEFAULT_PROFILE_TEMPLATE = """\
[export.extract]
# Extract attributes from job_code using regex named groups
job_code = "^(?P<type>[A-Za-z]+)-(?P<ticket>\\\\d+)$"

[export.defaults]
# Default values if regex extraction doesn't match or is empty
type = "General"
ticket = "None"

[export]
# Which keys from the extracted attributes to use to group notes and time together
group_by = ["type", "ticket"]
# Aggregated time precision and rounding: "round", "floor", or "ceil"
time_precision = 2
time_rounding = "round"
# Aggregation method: "sum_then_round" (default) or "round_then_sum"
time_aggregation_method = "sum_then_round"

[export.format]
# Jinja2 template for each note item. Variables: all extracted fields + memo,
# time_hours, project_name, job_name
note_item = "[{{ project_name }}/{{ job_name }}] {{ time_hours }}h: {{ memo }}"
note_separator = " / "

[export.columns]
# Mapping of final CSV column headers to Jinja2 templates
"Type"             = "{{ type }}"
"Ticket"           = "{{ ticket }}"
"Duration (Hours)" = "{{ aggregated_time }}"
"Details"          = "{{ aggregated_notes }}"

[import.mapping]
# How to map CSV columns to job attributes during import (Jinja2 templates)
name        = "{{ name }}"
description = "{{ description }}"
job_code    = "{{ type }}-{{ ticket }}"
"""


def load_profile(profile_path: str) -> dict:
    """Load the TOML profile from the given path, creating a default one if missing.

    Args:
        profile_path (str): Path to the TOML profile file.

    Returns:
        dict: The loaded profile configuration.
    """
    if not os.path.exists(profile_path):
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROFILE_TEMPLATE)

    with open(profile_path, "rb") as f:
        return tomllib.load(f)


def get_extract_regexes(export_config: dict) -> dict[str, re.Pattern | None]:
    """Compile extraction regexes from the export configuration.

    Args:
        export_config (dict): The export section of the profile.

    Returns:
        dict: A mapping of variable names to compiled regex patterns.
    """
    extract_rules = export_config.get("extract", {})
    compiled = {}
    for var, pattern in extract_rules.items():
        try:
            compiled[var] = re.compile(pattern)
        except re.error as e:
            print(f"Warning: Could not compile regex for '{var}': {e}")
            compiled[var] = None
    return compiled


def extract_fields(
    job_code: str, compiled_regexes: dict[str, re.Pattern | None], defaults: dict
) -> dict:
    """Extract fields from a job code using compiled regexes and default values.

    Args:
        job_code (str): The external reference code of a job.
        compiled_regexes (dict): Compiled regex patterns for extraction.
        defaults (dict): Default values for fields.

    Returns:
        dict: The dictionary of extracted and default fields.
    """
    row_data = defaults.copy()
    for var, pattern in compiled_regexes.items():
        if pattern:
            match = pattern.search(
                job_code if var == "job_code" else row_data.get(var, "")
            )
            if match:
                row_data.update(match.groupdict())
    return row_data


def render_columns(columns_config: dict, context: dict) -> dict[str, str]:
    """Render the final CSV columns using template configurations and context.

    Args:
        columns_config (dict): The column template mapping from the profile.
        context (dict): The dictionary of variables for rendering.

    Returns:
        dict: A mapping of column names to rendered string values.
    """
    final_row = {}
    for col_name, value_template in columns_config.items():
        final_row[col_name] = _render(value_template, context)
    return final_row


def aggregate_logs(
    profile_path: str, target_date: str | None = None, group_by_date: bool = False
) -> tuple[dict, list[dict]]:
    """Aggregate logs based on the provided TOML profile.

    Args:
        profile_path (str): Path to the TOML profile file.
        target_date (str | None): Optional date filter (YYYY-MM-DD).
        group_by_date (bool): Whether to include date in aggregation.

    Returns:
        tuple[dict, list[dict]]: (columns_config, rendered_results)
    """
    profile = load_profile(profile_path)
    export_config = profile.get("export", {})

    compiled_regexes = get_extract_regexes(export_config)
    defaults_config = export_config.get("defaults", {})

    group_by_keys = export_config.get("group_by", [])
    if group_by_date:
        group_by_keys = ["_date"] + group_by_keys

    note_item_template = export_config.get("format", {}).get("note_item", "")
    note_separator = export_config.get("format", {}).get("note_separator", "/")
    columns_config = export_config.get("columns", {})
    time_precision = export_config.get("time_precision", 2)
    time_rounding = export_config.get("time_rounding", "round")
    time_aggregation_method = export_config.get(
        "time_aggregation_method", "sum_then_round"
    )

    logs = operations.list_logs()

    # Filter by date if provided
    if target_date:
        logs = [
            log
            for log in logs
            if log["start_time"] and log["start_time"][:10] == target_date
        ]

    # Extract all variables into a flat list of dicts
    extracted_data = []

    for log in logs:
        job_code = log["job_code"] or ""
        row_data = extract_fields(job_code, compiled_regexes, defaults_config)

        row_data["memo"] = log["memo"] or ""
        row_data["project_name"] = log["project_name"] or ""
        row_data["job_name"] = log["job_name"] or ""

        if group_by_date:
            row_data["_date"] = log["start_time"][:10] if log["start_time"] else ""

        # Prefer explicit duration_hours, fall back to end-start calculation
        start_time = log["start_time"]
        end_time = log["end_time"]
        duration_hours = log["duration_hours"]

        if duration_hours is not None:
            time_hours = duration_hours
        elif start_time and end_time:
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            time_hours = (end_dt - start_dt).total_seconds() / 3600.0
        else:
            time_hours = 0.0

        # time_hours for display in note_item: rounded to time_precision
        row_data["time_hours"] = _apply_rounding(
            time_hours, time_precision, time_rounding
        )
        # _raw_time_hours for accurate aggregation summing (no pre-rounding)
        row_data["_raw_time_hours"] = time_hours
        extracted_data.append(row_data)

    # Group
    def group_key_func(item):
        return tuple(item.get(k, "") for k in group_by_keys)

    extracted_data.sort(key=group_key_func, reverse=group_by_date)

    aggregated_results = []

    for _, group_iter in groupby(extracted_data, key=group_key_func):
        group_items = list(group_iter)

        if time_aggregation_method == "round_then_sum":
            # Round each individual log entry's time before summing
            agg_time = sum(
                _apply_rounding(
                    item.get("_raw_time_hours", 0.0), time_precision, time_rounding
                )
                for item in group_items
            )
            # Ensure the final sum also respects precision
            # (though it should already be a multiple of the precision)
            agg_time = _apply_rounding(agg_time, time_precision, time_rounding)
        else:
            # Traditional: sum all raw times, then round the total
            total_time = sum(item.get("_raw_time_hours", 0.0) for item in group_items)
            agg_time = _apply_rounding(total_time, time_precision, time_rounding)

        # Sub-group by all fields to aggregate times for identical notes
        sub_groups = {}
        for item in group_items:
            # Key excludes time-based fields
            sub_key = tuple(
                sorted(
                    (k, str(v))
                    for k, v in item.items()
                    if k not in (
                        "_raw_time_hours",
                        "time_hours",
                        "_sum_of_rounded_hours",
                    )
                )
            )
            if sub_key not in sub_groups:
                sub_groups[sub_key] = item.copy()
                sub_groups[sub_key]["_raw_time_hours"] = 0.0
                sub_groups[sub_key]["_sum_of_rounded_hours"] = 0.0
            sub_groups[sub_key]["_raw_time_hours"] += item["_raw_time_hours"]
            sub_groups[sub_key]["_sum_of_rounded_hours"] += _apply_rounding(
                item["_raw_time_hours"], time_precision, time_rounding
            )

        # Aggregate notes using Jinja2
        notes = []
        for sub_item in sub_groups.values():
            # Calc rounded time for this sub-item for use in template
            if time_aggregation_method == "round_then_sum":
                # Matches the total aggregation logic: sum of individually rounded times
                sub_item["time_hours"] = _apply_rounding(
                    sub_item["_sum_of_rounded_hours"], time_precision, time_rounding
                )
            else:
                # Matches sum_then_round logic: sum raw, then round
                sub_item["time_hours"] = _apply_rounding(
                    sub_item["_raw_time_hours"], time_precision, time_rounding
                )
            if note_item_template:
                rendered = _render(note_item_template, sub_item)
                if rendered:
                    notes.append(rendered)

        aggregated_notes = note_separator.join(notes)

        representative_item = group_items[0].copy()
        representative_item["aggregated_time"] = agg_time
        representative_item["aggregated_notes"] = aggregated_notes

        # Map to final columns using Jinja2
        final_row = render_columns(columns_config, representative_item)

        if group_by_date:
            final_row["_date"] = representative_item.get("_date", "")

        aggregated_results.append(final_row)

    return columns_config, aggregated_results


def export_logs(profile_path: str, output_path: str, target_date: str | None = None):
    """Export logs based on the provided TOML profile.

    Generates a default profile if the specified one is missing. The process
    involves:
    1. Reading logs from the database.
    2. Filtering by date if requested.
    3. Extracting metadata from job codes using regex.
    4. Grouping records based on profile settings.
    5. Aggregating times and notes.
    6. Rendering final columns via Jinja2.

    Args:
        profile_path (str): Path to the TOML profile file.
        output_path (str): Path for the output CSV file.
        target_date (str | None, optional): Date string in YYYY-MM-DD format.
            Defaults to None (all logs).

    Returns:
        int: The number of aggregated rows exported.
    """
    if not os.path.exists(profile_path):
        # Create default profile if it doesn't exist
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROFILE_TEMPLATE)

    columns_config, aggregated_results = aggregate_logs(profile_path, target_date)

    if not aggregated_results:
        print("No logs matches the extract configuration or logs are empty.")
        return 0

    csv_columns = list(columns_config.keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(aggregated_results)

    return len(aggregated_results)


def export_jobs(
    profile_path: str, output_path: str, project_name: str | None = None
) -> int:
    """Export jobs based on the provided TOML profile.

    This function produces a CSV file that is equivalent to the one used
    for importing jobs. It analyzes [import.mapping] to determine the
    columns and populates them by deconstructing the job name,
    description, and job_code.

    Args:
        profile_path (str): Path to the TOML profile file.
        output_path (str): Path for the output CSV file.
        project_name (str | None, optional): Project name to filter by.
            Defaults to None (all jobs).

    Returns:
        int: The number of jobs exported.
    """
    if not os.path.exists(profile_path):
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROFILE_TEMPLATE)

    profile = load_profile(profile_path)
    import_mapping = profile.get("import", {}).get("mapping", {})
    export_config = profile.get("export", {})

    # 1. Identify columns from import mapping
    def get_vars(template):
        if not template or not isinstance(template, str):
            return []
        return re.findall(r"\{\{\s*(\w+)\s*\}\}", template)

    name_vars = get_vars(import_mapping.get("name", ""))
    desc_vars = get_vars(import_mapping.get("description", ""))
    code_vars = get_vars(import_mapping.get("job_code", ""))

    # Order: name, then description, then job_code variables
    all_columns = []
    for v in name_vars + desc_vars + code_vars:
        if v not in all_columns:
            all_columns.append(v)

    if not all_columns:
        # Fallback to basic columns if no import mapping is defined
        all_columns = ["name", "description", "job_code"]

    # Prepare extraction tools
    compiled_regexes = get_extract_regexes(export_config)
    defaults_config = export_config.get("defaults", {})
    export_columns_config = export_config.get("columns", {})

    # Helper for job_code deconstruction (Attempt A: Reverse mapping)
    code_template = import_mapping.get("job_code", "")
    code_reverse_regex = None
    if code_template:
        # Convert {{ var }} to (?P<var>.*)
        regex_parts = []
        parts = re.split(r"(\{\{\s*\w+\s*\}\})", code_template)
        for p in parts:
            vm = re.match(r"\{\{\s*(\w+)\s*\}\}", p)
            if vm:
                regex_parts.append(f"(?P<{vm.group(1)}>.*)")
            else:
                regex_parts.append(re.escape(p))
        try:
            code_reverse_regex = re.compile("^" + "".join(regex_parts) + "$")
        except re.error:
            code_reverse_regex = None

    jobs = operations.list_jobs(project_name)
    job_results = []

    for job in jobs:
        job_code = job["code"] or ""
        # Context for extraction: first, base fields
        base_ctx = {
            "project_name": job["project_name"],
            "job_name": job["name"],
            "name": job["name"],
            "description": job["description"] or "",
            "job_code": job_code,
            "aggregated_time": "0.0",  # Default for compatibility
            "aggregated_notes": "",
        }

        # Context for regex-based fields (English names usually)
        regex_ctx = extract_fields(job_code, compiled_regexes, defaults_config)
        full_ctx = {**base_ctx, **regex_ctx}

        # Map each required column to a value
        row = {}
        # Potential values from deconstructing job_code template
        deconstructed_vars = {}
        if code_reverse_regex:
            m = code_reverse_regex.match(job_code)
            if m:
                deconstructed_vars = m.groupdict()

        for col in all_columns:
            val = ""
            if col in name_vars:
                val = job["name"]
            elif col in desc_vars:
                val = job["description"] or ""
            elif col in deconstructed_vars:
                val = deconstructed_vars[col]
            else:
                # Attempt B: Use [export.columns] if it maps this column name
                # or just look for a variable with this name in context
                if col in export_columns_config:
                    val = _render(export_columns_config[col], full_ctx)
                elif col in full_ctx:
                    val = str(full_ctx[col])
                else:
                    val = ""
            row[col] = val

        job_results.append(row)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=all_columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(job_results)

    return len(job_results)
