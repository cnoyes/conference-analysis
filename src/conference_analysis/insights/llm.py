"""The only LLM path: the `claude` CLI in -p mode, with an on-disk cache.

Words come from here; numbers never do. Every answer is cached under data/llm_cache/
keyed by the prompt, so nothing is re-asked implicitly.
"""
import hashlib
import json
import re
import subprocess

from .config import CLAUDE_BIN, LLM_CACHE


def ask(prompt, timeout=600, parse=None):
    """Answer for prompt (cached). An answer that parse() rejects is not cached."""
    LLM_CACHE.mkdir(parents=True, exist_ok=True)
    path = LLM_CACHE / (hashlib.sha1(prompt.encode()).hexdigest() + ".txt")
    if path.exists():
        return path.read_text()
    result = subprocess.run([CLAUDE_BIN, "-p", "--output-format", "text"], input=prompt,
                            capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"claude -p failed: {result.stderr[:500]}")
    if parse:
        parse(result.stdout)  # raises on a malformed answer, before anything is cached
    path.write_text(result.stdout)
    return result.stdout


def ask_json(prompt, timeout=600):
    """Like ask(), for prompts that request JSON; tolerates code fences and stray prose."""
    def parse(answer):
        match = re.search(r"(\[.*\]|\{.*\})", answer, re.S)
        return json.loads(match.group(1) if match else answer)
    return parse(ask(prompt, timeout, parse))
