"""Export module for Work Time Logger."""

import csv
import re
import tomllib
from itertools import groupby
from operator import itemgetter

from . import operations


def export_logs(profile_path: str, output_path: str):
    """Export logs based on the provided TOML profile."""
    
    with open(profile_path, "rb") as f:
        profile = tomllib.load(f)

    extract_config = profile.get("extract", {})
    defaults_config = profile.get("defaults", {})
    export_config = profile.get("export", {})

    group_by_keys = export_config.get("group_by", [])
    note_item_format = export_config.get("format", {}).get("note_item", "")
    note_separator = export_config.get("format", {}).get("note_separator", "/")
    columns_config = export_config.get("columns", {})

    job_code_regex = extract_config.get("job_code", "")
    
    # Compile regex if provided
    job_code_pattern = re.compile(job_code_regex) if job_code_regex else None

    logs = operations.list_logs()
    
    # First extract all variables into a flat list of dictionaries
    extracted_data = []

    for log in logs:
        # Base row populated with defaults
        row_data = defaults_config.copy()
        
        # Extract from job_code
        job_code = log["job_code"] or ""
        if job_code_pattern:
            match = job_code_pattern.search(job_code)
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
