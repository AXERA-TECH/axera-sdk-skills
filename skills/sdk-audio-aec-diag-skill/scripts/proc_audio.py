"""Parse AI/AO proc tables, preserving row evidence and excluding console logs."""
import re


def parse_proc(text, source):
    section = None
    header = None
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        title = re.match(r"^-+\s+((?:AI|AO) [A-Z0-9 ]+?)\s+-+$", line.strip())
        if title:
            section = title.group(1)
            header = None
            continue
        tokens = line.split()
        if section and tokens and tokens[0] in ("AiCardId", "AoCardId"):
            header = tokens
            continue
        if header and len(tokens) == len(header) and all(x.isdigit() for x in tokens[:2]):
            rows.append({"section": section, "source": source, "line": number,
                         "values": dict(zip(header, tokens))})
        elif tokens:
            header = None
    return rows
