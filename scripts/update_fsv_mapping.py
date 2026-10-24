"""Extract all FSV codes from NASA.ptc, including commented definitions.

Usage: python scripts/update_fsv_mapping.py /path/to/NASA.ptc [mapping.json]
Every *IN_FSV_xxxx definition is included; absent codes are removed.
"""

import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def extract_definitions(source):
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    root = ET.parse(source, parser=parser).getroot()
    messages = [
        (element, False)
        for element in root.iter()
        if isinstance(element.tag, str) and element.tag.rsplit("}", 1)[-1] == "Message"
    ]
    for element in root.iter():
        if element.tag is ET.Comment and "<Message" in (element.text or ""):
            # Commented message definitions are data, not active XML nodes.
            for match in re.finditer(r"<Message\b.*?</Message\s*>", element.text, re.S):
                messages.append((ET.fromstring(match.group()), True))
    definitions = {}
    commented_codes = set()
    for message, commented in messages:
        match = re.fullmatch(r".*IN_FSV_(\d{4})", message.get("ProtocolID", ""))
        if not match:
            continue
        code = match[1]
        children = list(message)
        by_tag = {child.tag.rsplit("}", 1)[-1]: child for child in children}
        definition = {"messageId": int(message.attrib["Index"], 16)}
        if "Enum" in by_tag:
            options = [
                int(item.attrib["Value"], 0)
                for item in by_tag["Enum"]
                if item.tag.rsplit("}", 1)[-1] == "Item"
            ]
            bounds = by_tag.get("Range")
            if not options and bounds is not None:
                lower, upper = (
                    int(bounds.attrib["Min"], 0),
                    int(bounds.attrib["Max"], 0),
                )
                if not 0 <= lower <= upper <= 65535:
                    raise ValueError(f"FSV {code}: invalid enum range")
                options = list(range(lower, upper + 1))
            if any(not 0 <= value <= 65535 for value in options):
                raise ValueError(f"FSV {code}: enum option outside register range")
            # Use boolean options when the source specifies neither items nor a range.
            definition.update(
                scale=1, signed=False, options=sorted(set(options)) or [0, 1]
            )
        elif "Variable" in by_tag:
            signed = by_tag["Variable"].get("Signed")
            if signed not in ("true", "false"):
                raise ValueError(f"FSV {code}: missing/invalid Signed flag")
            scale = Decimal(1)
            for child in children:
                if child.tag.rsplit("}", 1)[-1] != "Arithmatic":
                    continue
                if child.get("Operation") != "Division":
                    raise ValueError(
                        f"FSV {code}: unsupported arithmetic {child.attrib}"
                    )
                divisor = Decimal(child.text.strip())
                if not divisor.is_finite() or divisor <= 0:
                    raise ValueError(f"FSV {code}: invalid divisor")
                scale /= divisor
            definition.update(
                scale=int(scale) if scale == int(scale) else float(scale),
                signed=signed == "true",
            )
        else:
            raise ValueError(f"FSV {code}: unsupported message definition")
        if code in definitions and definitions[code] != definition:
            raise ValueError(f"FSV {code}: conflicting definitions")
        definitions[code] = definition
        if commented:
            commented_codes.add(code)
    return definitions, commented_codes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "mapping",
        type=Path,
        nargs="?",
        default=Path(__file__).resolve().parents[1]
        / "custom_components/samsung_modbus_hp/fsv_mapping.json",
    )
    args = parser.parse_args()
    existing = json.loads(args.mapping.read_text()) if args.mapping.exists() else {}
    definitions, commented = extract_definitions(args.source)
    updated = {code: definitions[code] for code in sorted(definitions)}
    if not updated:
        raise ValueError("No matching FSV definitions found; mapping left unchanged")
    args.mapping.write_text(json.dumps(updated, indent=2) + "\n")
    print(f"Updated {len(updated)} FSV definitions from {args.source}")
    print(
        "Included commented definitions:",
        ", ".join(sorted(set(updated) & commented)) or "none",
    )
    print(
        "Removed absent codes:",
        ", ".join(sorted(set(existing) - set(updated))) or "none",
    )


if __name__ == "__main__":
    main()
