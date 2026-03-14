import re

ACTION_PATTERN = re.compile(
    r"\[ACTION:\s*(post_to_board|send_message|remember|recall|update_soul)"
    r"(?:\s+(?:to|query)=(\S+))?\]"
    r"\s*(.*?)\s*"
    r"(?:\[/ACTION\]|\]\s*$|\]\s*\n)",
    re.DOTALL | re.MULTILINE,
)


def parse(response: str) -> list[tuple[str, str, str]]:
    """Returns list of (action_type, target, content) tuples."""
    return [
        (action_type, target.strip() if target else "", content.strip())
        for action_type, target, content in ACTION_PATTERN.findall(response)
    ]
