# ruff: noqa: S101, S102, S311, E501  (offline dev tool: runs our own reference code)
# mypy: ignore-errors
"""Build app/modules/coding/seed_problems.json

    uv run python -m app.scripts.build_seed_problems app/modules/coding/seed_problems.json

Builds: statements, tests, and Python reference solutions.

Expected outputs come from running the reference solutions here (trusted code, written by
us), so tests and references always agree.
"""

import io
import json
import random
import sys
from contextlib import redirect_stdout
from pathlib import Path

OUT = Path(sys.argv[1])
rng = random.Random(42)

PROBLEMS = []


def add(slug, title, difficulty, topics, statement, reference, visible, hidden):
    tests = []
    for i, (stdin, is_hidden) in enumerate(
        [(x, False) for x in visible] + [(x, True) for x in hidden]
    ):
        namespace = {"__name__": "__main__"}
        buf = io.StringIO()
        old = sys.stdin
        sys.stdin = io.StringIO(stdin)
        try:
            with redirect_stdout(buf):
                exec(compile(reference, slug, "exec"), namespace)  # our own reference code
        finally:
            sys.stdin = old
        tests.append(
            {"position": i, "input": stdin, "expected_output": buf.getvalue(), "hidden": is_hidden}
        )
    PROBLEMS.append(
        {
            "slug": slug,
            "title": title,
            "difficulty": difficulty,
            "topics": topics,
            "statement": statement.strip() + "\n",
            "reference": {"python": reference.strip() + "\n"},
            "tests": tests,
        }
    )


# 1 ---------------------------------------------------------------- two sum
TWO_SUM = """
import sys
def main():
    data = sys.stdin.read().split()
    n, target = int(data[0]), int(data[1])
    nums = list(map(int, data[2:2 + n]))
    seen = {}
    for i, x in enumerate(nums):
        if target - x in seen:
            print(seen[target - x], i)
            return
        seen.setdefault(x, i)
main()
"""


def two_sum_case(n):
    nums = [rng.randint(-(10**6), 10**6) for _ in range(n)]
    i, j = sorted(rng.sample(range(n), 2))
    target = nums[i] + nums[j]
    # make the pair unique: nudge other values that would also sum to target
    seen = set()
    for k in range(n):
        if k not in (i, j):
            while (
                target - nums[k] in seen
                or nums[k] in (target - nums[i], target - nums[j])
                or target - nums[k] in (nums[i], nums[j])
            ):
                nums[k] += 7919
        seen.add(nums[k])
    counts = {}
    pairs = 0
    for x in nums:
        pairs += counts.get(target - x, 0)
        counts[x] = counts.get(x, 0) + 1
    assert pairs == 1, pairs  # exactly one valid answer
    return f"{n} {target}\n{' '.join(map(str, nums))}\n"


add(
    "two-sum",
    "Two Sum",
    "easy",
    ["arrays", "hashing"],
    """
Given `n` integers and a target, find the two positions `i < j` whose values add up to the target.
Exactly one such pair exists.

**Input**
- Line 1: `n` and `target`
- Line 2: `n` integers

**Output**
The two 0-based indices `i j`, separated by a space.

**Constraints:** 2 ≤ n ≤ 10^5, values and target fit in 32-bit signed integers.
""",
    TWO_SUM,
    ["4 9\n2 7 11 15\n", "3 6\n3 2 4\n"],
    ["2 6\n3 3\n", "5 -8\n-1 -3 -5 2 9\n", two_sum_case(2000), two_sum_case(20000)],
)

# 2 ---------------------------------------------------------------- brackets
BRACKETS = """
import sys
def main():
    s = sys.stdin.read().strip()
    pairs = {')': '(', ']': '[', '}': '{'}
    stack = []
    for ch in s:
        if ch in '([{':
            stack.append(ch)
        elif not stack or stack.pop() != pairs[ch]:
            print("NO")
            return
    print("NO" if stack else "YES")
main()
"""


def brackets_case(depth, broken):
    s = []
    for _ in range(depth):
        o, c = rng.choice(["()", "[]", "{}"])
        s.insert(rng.randint(0, len(s)), o + c)
    text = "".join(s)
    if broken:
        text = text[:-1] + ("(" if text[-1] != "(" else ")")
    return text + "\n"


add(
    "balanced-brackets",
    "Balanced Brackets",
    "easy",
    ["stacks", "strings"],
    """
A string contains only the characters `()[]{}`. Print `YES` if every bracket is closed by the
same kind of bracket in the correct order, otherwise `NO`.

**Input**
One line with the string (length 1 to 10^5).

**Output**
`YES` or `NO`.
""",
    BRACKETS,
    ["([]{})\n", "([)]\n"],
    ["(\n", "}\n", "{[()()]}\n", brackets_case(3000, False), brackets_case(3000, True)],
)

# 3 ---------------------------------------------------------------- reverse words
REVERSE = """
import sys
def main():
    words = sys.stdin.read().split()
    print(" ".join(reversed(words)))
main()
"""
add(
    "reverse-words",
    "Reverse the Words",
    "easy",
    ["strings", "two pointers"],
    """
Reverse the order of the words in a sentence. Words are separated by one or more spaces;
the output uses single spaces with no leading or trailing space.

**Input**
One line of text (up to 10^5 characters).

**Output**
The words in reverse order.
""",
    REVERSE,
    ["the sky is blue\n", "  hello world  \n"],
    ["a\n", "a good   example\n", " ".join(f"w{i}" for i in range(20000)) + "\n"],
)

# 4 ---------------------------------------------------------------- longest unique substring
LONGEST = """
import sys
def main():
    s = sys.stdin.read().strip()
    last, start, best = {}, 0, 0
    for i, ch in enumerate(s):
        if ch in last and last[ch] >= start:
            start = last[ch] + 1
        last[ch] = i
        best = max(best, i - start + 1)
    print(best)
main()
"""
add(
    "longest-unique-substring",
    "Longest Substring Without Repeats",
    "medium",
    ["sliding window", "hashing"],
    """
Find the length of the longest substring that contains no repeated character.

**Input**
One line with a string of lowercase letters (length 1 to 10^5).

**Output**
The length of the longest substring without repeating characters.
""",
    LONGEST,
    ["abcabcbb\n", "bbbbb\n"],
    [
        "pwwkew\n",
        "a\n",
        "abcdefghijklmnopqrstuvwxyz\n",
        "".join(rng.choice("abcdefghij") for _ in range(50000)) + "\n",
    ],
)

# 5 ---------------------------------------------------------------- merge intervals
MERGE = """
import sys
def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    items = sorted((int(data[1 + 2 * i]), int(data[2 + 2 * i])) for i in range(n))
    merged = []
    for a, b in items:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    print("\\n".join(f"{a} {b}" for a, b in merged))
main()
"""


def merge_case(n):
    rows = []
    for _ in range(n):
        a = rng.randint(0, 10**6)
        rows.append(f"{a} {a + rng.randint(0, 500)}")
    return f"{n}\n" + "\n".join(rows) + "\n"


add(
    "merge-intervals",
    "Merge Intervals",
    "medium",
    ["sorting", "intervals"],
    """
Merge all overlapping intervals and print the result in increasing order of start.
Intervals that touch (`[1,3]` and `[3,5]`) overlap.

**Input**
- Line 1: `n`
- Next `n` lines: `start end` with start ≤ end

**Output**
One merged interval per line: `start end`.
""",
    MERGE,
    ["4\n1 3\n2 6\n8 10\n15 18\n", "2\n1 4\n4 5\n"],
    ["1\n5 5\n", "3\n1 10\n2 3\n4 5\n", merge_case(3000), merge_case(20000)],
)

# 6 ---------------------------------------------------------------- islands
ISLANDS = """
import sys
from collections import deque
def main():
    data = sys.stdin.read().split()
    rows, cols = int(data[0]), int(data[1])
    grid = [list(row) for row in data[2:2 + rows]]
    count = 0
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] == '1':
                count += 1
                grid[r][c] = '0'
                queue = deque([(r, c)])
                while queue:
                    y, x = queue.popleft()
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < rows and 0 <= nx < cols and grid[ny][nx] == '1':
                            grid[ny][nx] = '0'
                            queue.append((ny, nx))
    print(count)
main()
"""


def grid_case(rows, cols, p):
    return (
        f"{rows} {cols}\n"
        + "\n".join(
            "".join("1" if rng.random() < p else "0" for _ in range(cols)) for _ in range(rows)
        )
        + "\n"
    )


add(
    "number-of-islands",
    "Number of Islands",
    "medium",
    ["graphs", "bfs", "dfs"],
    """
A grid has land (`1`) and water (`0`). An island is land connected horizontally or
vertically. Count the islands.

**Input**
- Line 1: `rows cols`
- Next `rows` lines: a string of `cols` characters, each `0` or `1`

**Output**
The number of islands.

**Constraints:** 1 ≤ rows, cols ≤ 1000. Deep recursion may overflow; an iterative search is safest.
""",
    ISLANDS,
    ["4 5\n11110\n11010\n11000\n00000\n", "4 5\n11000\n11000\n00100\n00011\n"],
    [
        "1 1\n0\n",
        "1 1\n1\n",
        grid_case(60, 80, 0.45),
        "150 150\n" + "\n".join("1" * 150 for _ in range(150)) + "\n",
        grid_case(200, 200, 0.4),
    ],
)

# 7 ---------------------------------------------------------------- running median
MEDIAN = """
import sys
import heapq
def main():
    data = sys.stdin.read().split()
    n = int(data[0])
    low, high, out = [], [], []
    for x in map(int, data[1:1 + n]):
        if not low or x <= -low[0]:
            heapq.heappush(low, -x)
        else:
            heapq.heappush(high, x)
        if len(low) > len(high) + 1:
            heapq.heappush(high, -heapq.heappop(low))
        elif len(high) > len(low):
            heapq.heappush(low, -heapq.heappop(high))
        out.append(str(-low[0]))
    print("\\n".join(out))
main()
"""
add(
    "running-median",
    "Running Median",
    "hard",
    ["heaps", "design"],
    """
Numbers arrive one at a time. After each one, print the **lower median** of everything seen
so far: with `k` numbers sorted, the element at 1-based position `ceil(k / 2)`.

**Input**
- Line 1: `n`
- Line 2: `n` integers

**Output**
`n` lines: the lower median after each number.

**Constraints:** 1 ≤ n ≤ 10^5. An O(n²) approach will time out.
""",
    MEDIAN,
    ["5\n5 15 1 3 8\n", "3\n2 2 2\n"],
    [
        "1\n-7\n",
        "6\n1 2 3 4 5 6\n",
        f"20000\n{' '.join(str(rng.randint(-(10**6), 10**6)) for _ in range(20000))}\n",
        f"30000\n{' '.join(str(rng.randint(-(10**9), 10**9)) for _ in range(30000))}\n",
    ],
)

# 8 ---------------------------------------------------------------- edit distance
EDIT = """
import sys
def main():
    lines = sys.stdin.read().split("\\n")
    a, b = lines[0].strip(), lines[1].strip() if len(lines) > 1 else ""
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = prev[j - 1] if a[i - 1] == b[j - 1] else 1 + min(prev[j - 1], prev[j], cur[j - 1])
        prev = cur
    print(prev[len(b)])
main()
"""


def word(n):
    return "".join(rng.choice("abcd") for _ in range(n))


add(
    "edit-distance",
    "Edit Distance",
    "hard",
    ["dynamic programming", "strings"],
    """
Find the minimum number of single-character insertions, deletions and substitutions that
turn the first word into the second.

**Input**
Two lines, one word each (lowercase letters, length 0 to 2000).

**Output**
The edit distance.
""",
    EDIT,
    ["horse\nros\n", "intention\nexecution\n"],
    [
        "abc\nabc\n",
        "a\n\n",
        "kitten\nsitting\n",
        f"{word(300)}\n{word(280)}\n",
        f"{word(2000)}\n{word(1900)}\n",
    ],
)

OUT.write_text(json.dumps(PROBLEMS, indent=1), encoding="utf-8")
print(
    len(PROBLEMS),
    "problems,",
    sum(len(p["tests"]) for p in PROBLEMS),
    "tests,",
    OUT.stat().st_size // 1024,
    "KB",
)
for p in PROBLEMS:
    print(p["slug"], [t["expected_output"][:20] for t in p["tests"][:2]])
