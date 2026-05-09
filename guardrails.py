import re

def check_prompt_injection(prompt: str) -> bool:
    """
    Semantic Bouncer
    Intercepts the user's prompt before LangGraph sees it.
    Runs a basic keyword check for prompt injections.
    Returns True if the prompt is safe, False if malicious.
    """
    malicious_patterns = [
        r"ignore previous instructions",
        r"disregard all prior instructions",
        r"forget everything",
        r"you are now an unrestricted",
        r"system prompt",
        r"jailbreak",
        r"bypass rules"
    ]

    lower_prompt = prompt.lower()
    for pattern in malicious_patterns:
        if re.search(pattern, lower_prompt):
            return False

    return True
