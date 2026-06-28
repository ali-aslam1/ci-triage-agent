import re

# Standard regex to strip ANSI escape codes (colors, text styling)
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# Standard regex to strip ISO-8601 UTC timestamp prefixes (e.g. 2026-06-27T23:39:16.5574521Z)
TIMESTAMP_REGEX = re.compile(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\s?')

# Keywords representing pip install logs spam
PIP_SPAM_KEYWORDS = [
    "Requirement already satisfied:",
    "Collecting ",
    "Downloading ",
    "Using cached ",
    "Installing collected packages:",
    "Successfully installed ",
]

# Keywords representing a failure or error boundary in logs (pre-uppercased for performance)
FAILURE_KEYWORDS = [
    "FAILED",
    "FAILURE",
    "ERROR",
    "PROCESS COMPLETED WITH EXIT CODE"
]

def is_failure_line(line: str) -> bool:
    """Helper to detect if a log line represents a failure or exit code warning."""
    line_upper = line.upper()
    if "EXIT CODE" in line_upper:
        if "EXIT CODE 0" not in line_upper:
            return True
    for kw in FAILURE_KEYWORDS:
        if kw in line_upper:
            return True
    return False

def clean_single_log_text(log_text: str) -> str:
    """
    Cleans a single continuous log flow by stripping ANSI/Timestamps, 
    pruning pip install spam, and isolating failure segments with context.
    """
    raw_lines = log_text.splitlines()
    processed_lines = []
    
    for line in raw_lines:
        # Strip ANSI escape codes
        clean_line = ANSI_ESCAPE.sub('', line)
        # Strip timestamp prefix
        clean_line = TIMESTAMP_REGEX.sub('', clean_line)
        
        # Filter pip install verbose spam unless it explicitly contains an error keyword
        if any(kw in clean_line for kw in PIP_SPAM_KEYWORDS) and not ("ERROR" in clean_line.upper() or "FAIL" in clean_line.upper()):
            continue
        # Filter pip download progress stats (e.g. 1.2/1.3 MB 1.4 MB/s)
        if "B/s" in clean_line and any(char.isdigit() for char in clean_line):
            continue
        # Filter terminal-based progress bars
        if "█" in clean_line:
            continue
            
        processed_lines.append(clean_line)
        
    N = len(processed_lines)
    if N <= 50:
        return "\n".join(processed_lines)
        
    # Mark indices to include
    included_indices = set()
    
    # 1. Always include first 20 lines (header context for environment/runner information)
    included_indices.update(range(20))
    
    # 2. Always include last 30 lines (test summary statistics/exit summaries)
    included_indices.update(range(N - 30, N))
        
    # 3. Include context windows around failures (40 lines before, 10 lines after)
    for idx, line in enumerate(processed_lines):
        if is_failure_line(line):
            start = max(0, idx - 40)
            end = min(N, idx + 10 + 1)
            included_indices.update(range(start, end))
            
    # Assemble final output using [snip] markers
    cleaned_parts = []
    last_idx = -1
    for idx in sorted(included_indices):
        if last_idx != -1 and idx > last_idx + 1:
            cleaned_parts.append("... [snip] ...")
        cleaned_parts.append(processed_lines[idx])
        last_idx = idx
        
    return "\n".join(cleaned_parts)

def clean_log(log_text: str) -> str:
    """
    Cleans log contents by identifying individual log file boundaries, 
    cleaning each log file separately, and reassembling them with their headers.
    """
    # Regex to find LOG FILE boundaries:
    # Matches the separator block and captures the filename
    header_pattern = re.compile(
        r'={80}\nLOG FILE: (.*?)\n={80}\n',
    )
    
    matches = list(header_pattern.finditer(log_text))
    
    if not matches:
        return clean_single_log_text(log_text)
        
    cleaned_sections = []
    
    for i, match in enumerate(matches):
        # Handle prefix text if any (e.g., preamble before first file indicator)
        if i == 0 and match.start() > 0:
            preamble = log_text[0:match.start()].strip()
            if preamble:
                cleaned_val = clean_single_log_text(preamble)
                if cleaned_val.strip():
                    cleaned_sections.append(cleaned_val)
                    
        file_name = match.group(1)
        start_pos = match.end()
        end_pos = matches[i + 1].start() if i + 1 < len(matches) else len(log_text)
        
        section_content = log_text[start_pos:end_pos]
        cleaned_content = clean_single_log_text(section_content)
        
        if cleaned_content.strip():
            header = (
                f"================================================================================\n"
                f"LOG FILE: {file_name}\n"
                f"================================================================================"
            )
            cleaned_sections.append(f"{header}\n{cleaned_content}")
            
    return "\n\n".join(cleaned_sections)
