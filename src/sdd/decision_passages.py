"""Find complementary decision evidence within the extracted source at one revision."""
from __future__ import annotations

from collections import defaultdict
import re
import subprocess

from .matching import match_any


# These cues locate candidate passages. The writer receives the actual text,
# including contradictions and exceptions, and must justify claims from it.
_PATTERNS = {
    "frame": r"(frame|buffer|image|metadata|payload).{0,30}(invalid|corrupt|cancel|valid data|not valid)",
    "stop": r"(stop|flush|abort).{0,75}(pending|cancel|complete|return|synchron)",
    "notification": r"(request|result).{0,36}(complete|cancel|callback).{0,40}(status|emit|signal|notify|queue)",
    "use": r"(buffer|request|resource).{0,50}(reused?|recycl|requeue|returned to)",
    "lifetime": r"(pointer|referenced|receiver|argument|object|signal|callback).{0,70}(remain valid|stay valid|lifetime|outlive|keep alive|destroyed|are copied)",
    "fence": r"(fence|sync_file).{0,65}(release|reuse|ownership|signal|timeout|wait)",
    "configure": r"(configure|configuration).{0,65}(stream|camera|device).{0,30}(start|valid|accept|support|return)",
    "submit": r"(submit|enqueue|queue|process).{0,20}(request|capture).{0,60}(return|error|start|valid|fail|complete)",
    "inputs": r"(invalid|missing|unsupported|requires?).{0,40}(format|stream|buffer|configuration|request)",
    "test": r"(assert|expect|verify|test).{0,45}(stop|flush|request|status|cancel|capture)",
}
_ROLES = {
    "completion": ("frame", "stop", "notification", "submit"),
    "ownership": ("lifetime", "use", "fence", "notification"),
    "integration": ("configure", "submit", "stop"),
    "inputs": ("inputs", "configure", "submit"),
    "failure": ("frame", "inputs", "stop", "fence"),
    "verification": ("test", "frame", "stop"),
    "outputs": ("frame", "notification"),
    "lifecycle": ("configure", "submit", "stop"),
    "constraints": ("inputs", "configure"),
}


def _matches(root, commit, paths):
    """Use the source root's relative paths, including for nested Git checkouts."""
    args = ["git", "--literal-pathspecs", "grep", "--no-color", "-n", "-I", "-z",
            "-i", "-E", "-e", "|".join(_PATTERNS.values()), commit, "--"]
    patterns = {role: re.compile(pattern, re.I) for role, pattern in _PATTERNS.items()}
    result = defaultdict(list)
    for offset in range(0, len(paths), 40):
        proc = subprocess.run([*args, *paths[offset:offset + 40]], cwd=root, capture_output=True)
        if proc.returncode not in (0, 1):
            raise ValueError(proc.stderr.decode("utf-8", "replace"))
        for row in proc.stdout.decode("utf-8", "replace").splitlines():
            fields = row.split("\0", 2)
            if len(fields) != 3 or not fields[0].startswith(commit + ":") or not fields[1].isdigit():
                continue
            file, line, content = fields[0][len(commit) + 1:], int(fields[1]), fields[2]
            for role, pattern in patterns.items():
                if pattern.search(content):
                    # An API comment spells out meaning, a branch or call site
                    # shows enforcement. Both compete alongside symbol definitions.
                    explains = bool(re.search(r"(?:[\\@](?:brief|enum|return|var)|\b(?:invalid|valid|must|until|pending|ownership)\b)", content, re.I))
                    delayed = role == "lifetime" and re.search(r"signal|callback|receiver|argument", content, re.I)
                    result[role].append((not delayed, not explains, file.count("/"), file, line))
    return {role: sorted(rows) for role, rows in result.items()}


def decision_locations(cfg, commit, files, section, topic, cache):
    roles = tuple(dict.fromkeys(role for aspect in topic["covers"] for role in _ROLES.get(aspect, ())))
    if not roles:
        return
    # The cache belongs to one prepare() operation and its pinned facts.
    key = ("decision-passages", commit)
    if key not in cache:
        cache[key] = _matches(cfg.source_root, commit, sorted(files))
    for depth in range(2):
        for role in roles:
            previous = []
            for _, _, _, file, line in cache[key].get(role, ()):
                if match_any(file, section.get("watch_exclude") or []):
                    continue
                if any(path == file and abs(row - line) < 30 for path, row in previous):
                    continue
                if len(previous) == depth:
                    yield file, line
                    break
                previous.append((file, line))
