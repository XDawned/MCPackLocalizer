"""Pre/post-processing parity test (single process via TestClient).

We:
  1. Monkey-patch server.HOLDER.translate to return a deterministic string.
  2. Recompute the expected output using the original Translator.pre_process /
     Translator.post_process logic (re-implemented here verbatim from the
     legacy `common/util.py`).
  3. Hit the /translate endpoint and assert byte-for-byte equality.
"""
import re
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SVC_DIR = Path(__file__).resolve().parent.parent / "inference_service"
sys.path.insert(0, str(SVC_DIR))

import server  # noqa: E402

client = TestClient(server.app)

# ----- Original pre/post (copied verbatim from legacy common/util.py) -----
MAGIC_WORD = r"{xdawned}"


def bracket(m): return "[&" + m.group(0) + "]"


def debracket(m): return m.group(0)[2:-1]


def orig_pre(line: str):
    if line.find(".jpg") + line.find(".png") != -2:
        return None
    if line.find(r'{\"') != -1:
        return None
    line = line.replace("\\\\&", "PPP")
    pattern = re.compile(r"&([a-z,0-9]|#[0-9,A-F]{6})")
    line = pattern.sub(bracket, line)
    line = re.sub(r"#\w+:\w+\b", MAGIC_WORD, re.sub(r'\\"', '\"', line))
    pattern = re.compile(r"(http|https)://(?:[-\w.]|(?:%[\da-fA-F]{2}))+")
    if re.search(pattern, line):
        return None
    return line


def orig_post(text: str, translate: str, keep_original: bool = False):
    pattern = re.compile(r"\[&&([a-z,0-9]|#[0-9,A-F]{6})]")
    translate = pattern.sub(debracket, translate)
    text = pattern.sub(debracket, text)
    text = re.sub(r'(["\'])', r'\\\g<1>', text)
    quotes = re.findall(r"#\w+:\w+\b", text)
    if len(quotes) > 0:
        count = 0
        idx = translate.find(MAGIC_WORD)
        while idx != -1:
            translate = re.sub(MAGIC_WORD, quotes[count], translate, 1)
            count += 1
            idx = translate.find(MAGIC_WORD)
    return translate + "[--" + text + "--]" if keep_original else translate


# ----- Mock the model so translate() returns a deterministic value -----
def fake_translate(text: str) -> str:
    return "T:" + text


server.HOLDER.translate = fake_translate  # type: ignore[assignment]
server.HOLDER._model = object()  # type: ignore[attr-defined]
server.HOLDER._tokenizer = object()  # type: ignore[attr-defined]
server.HOLDER._load_error = None  # type: ignore[attr-defined]

cases = [
    "&aHello&b world",
    "see #minecraft:stone",
    "visit https://example.com",
    "look at foo.png",
    "plain text",
    "{\"escaped\":true}",
    "\\\\&raw ampersand",
]

failures = 0
for c in cases:
    expected_skip = orig_pre(c) is None
    r = client.post("/translate", json={"text": c})
    if expected_skip:
        ok = r.status_code == 200 and r.json().get("skipped") is True
        print(f"  SKIP  {c!r:40s}  -> {r.status_code} {r.json()}")
        if not ok:
            failures += 1
        continue
    if r.status_code != 200:
        print(f"  FAIL  {c!r:40s}  -> {r.status_code} {r.json()}")
        failures += 1
        continue
    expected = orig_post(c, fake_translate(orig_pre(c)))
    got = r.json()["translation"]
    if got == expected:
        print(f"  OK    {c!r:40s}  -> {got!r}")
    else:
        print(f"  FAIL  {c!r:40s}")
        print(f"        expected: {expected!r}")
        print(f"        got:      {got!r}")
        failures += 1

if failures:
    sys.exit(f"\n{failures} case(s) failed parity check")
print("\nAll cases pass parity check.")
