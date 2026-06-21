def calculate_display_precision(scale: float) -> int:
    """Calculate display precision from scale factor."""
    scale_str = str(scale)
    if "." not in scale_str:
        return 0
    decimals = scale_str.split(".")[1]
    return 0 if decimals == "0" else len(decimals)

def get_mapped_value(raw_val: int | None, mapping: dict, as_string: bool = True) -> str | bool | None:
    """Convert raw register value using mapping configuration."""
    if raw_val is None:
        return None
    
    if raw_val in mapping:
        val = mapping[raw_val]
        return str(val) if as_string else val
    
    fallback = mapping.get("fallback")
    if fallback:
        return fallback.format(value=raw_val) if as_string else True
    
    return None

def extract_options_from_mapping(mapping: dict) -> list[str]:
    """Extract selectable options from mapping, excluding fallback."""
    if not mapping:
        return []
    return list({str(v) for k, v in mapping.items() if k != "fallback"})
