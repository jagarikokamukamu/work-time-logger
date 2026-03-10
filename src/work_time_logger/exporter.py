"""Export module for Work Time Logger."""

import os
import csv
import re
import tomllib
from itertools import groupby
from operator import itemgetter

from . import operations

DEFAULT_PROFILE_TEMPLATE = """[export.extract]
# Extract attributes from job_code using regex named groups
job_code = "^(?P<type>[A-Za-z]+)-(?P<ticket>\\\\d+)$"

[export.defaults]
# Default values if regex extraction doesn't match or is empty
type = "General"
ticket = "None"

[export]
# Which keys from the extracted attributes to use to group notes and time together
group_by = ["type", "ticket"]

[export.format]
# How to format notes for a single item and how to separate multiple items
note_item = "[{project_name}/{job_name}] {time_hours}h: {memo}"
note_separator = " / "

[export.columns]
# Mapping of final CSV column headers to the string template
"Type" = "{type}"
"Ticket" = "{ticket}"
"Duration (Hours)" = "{aggregated_time}"
"Details" = "{aggregated_notes}"

[import.mapping]
# How to map CSV columns to job attributes during import
name = "{name}"
description = "{description}"
job_code = "{type}-{ticket}"
"""

def export_logs(profile_path: str, output_path: str):
    """Export logs based on the provided TOML profile. Generates a default profile if missing."""
    
    if not os.path.exists(profile_path):
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_PROFILE_TEMPLATE)
            
    with open(profile_path, "rb") as f:
        profile = tomllib.load(f)

    # We now look for extract and defaults underneath the 'export' section if available.
    # For backwards compatibility with older files involving [extract] / [defaults]:
    export_config = profile.get("export", {})
    
    extract_rules = export_config.get("extract", profile.get("extract", {}))
    defaults_config = export_config.get("defaults", profile.get("defaults", {}))

    # Compile regexes safely
    compiled_regexes = {}
    for var, pattern in extract_rules.items():
        try:
            compiled_regexes[var] = re.compile(pattern)
        except re.error as e:
            print(f"Warning: Could not compile regex for '{var}': {e}")
            compiled_regexes[var] = None # Store None for invalid regexes

    group_by_keys = export_config.get("group_by", [])
    note_item_format = export_config.get("format", {}).get("note_item", "")
    note_separator = export_config.get("format", {}).get("note_separator", "/")
    columns_config = export_config.get("columns", {})

    logs = operations.list_logs()
    
    # First extract all variables into a flat list of dictionaries
    extracted_data = []

    for log in logs:
        # Base row populated with defaults
        row_data = defaults_config.copy()
        
        # Extract from job_code
        job_code = log["job_code"] or ""
        
        # Apply all valid regexes for extractions (including job_code)
        for var, pattern in compiled_regexes.items():
            if pattern:
                match = pattern.search(job_code if var == "job_code" else row_data.get(var, ""))
                if match:
                    row_data.update(match.groupdict())
                
        # Get standard database fields
        row_data["memo"] = log["memo"] or ""
        row_data["project_name"] = log["project_name"] or ""
        row_data["job_name"] = log["job_name"] or ""
        
        # Calculate time in hours
        start_time = log["start_time"]
        end_time = log["end_time"]
        
        time_hours = 0.0
        if start_time and end_time:
            from datetime import datetime
            start_dt = datetime.fromisoformat(start_time)
            end_dt = datetime.fromisoformat(end_time)
            duration = end_dt - start_dt
            time_hours = duration.total_seconds() / 3600.0
            
        row_data["time_hours"] = round(time_hours, 2)
        extracted_data.append(row_data)

    # Grouping
    # Sort data by group_by keys first, required by itertools.groupby
    def group_key_func(item):
        return tuple(item.get(k, "") for k in group_by_keys)

    extracted_data.sort(key=group_key_func)
    
    aggregated_results = []
    
    for key_tuple, group_iter in groupby(extracted_data, key=group_key_func):
        group_items = list(group_iter)
        
        # Sum time
        total_time = sum(item.get("time_hours", 0.0) for item in group_items)
        
        # Aggregate notes
        notes = []
        for item in group_items:
            if note_item_format:
                try:
                    formatted_note = note_item_format.format(**item)
                    notes.append(formatted_note)
                except KeyError:
                    pass
        
        aggregated_notes = note_separator.join(notes)
        
        # Take the first item to represent the grouped data
        representative_item = group_items[0].copy()
        representative_item["aggregated_time"] = round(total_time, 2)
        representative_item["aggregated_notes"] = aggregated_notes
        
        # Map to final columns
        final_row = {}
        for col_name, value_template in columns_config.items():
            try:
                final_row[col_name] = value_template.format(**representative_item)
            except KeyError:
                final_row[col_name] = ""
                
        aggregated_results.append(final_row)

    # Write CSV
    if not aggregated_results:
        print("No logs matches the extract configuration or logs are empty.")
        return 0

    csv_columns = list(columns_config.keys())
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=csv_columns)
        writer.writeheader()
        writer.writerows(aggregated_results)

    return len(aggregated_results)
