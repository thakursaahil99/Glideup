"""The six languages GlideUp ships with, and the starter code each problem begins from.

Problems are plain programs: read the input from stdin, print the answer to stdout. That
works identically in every sandbox and language, with no per-language test harness.
"""

from typing import Any

DEFAULT_LANGUAGES: list[dict[str, Any]] = [
    {
        "key": "python",
        "name": "Python 3",
        "time_limit_s": 3.0,
        "memory_limit_mb": 256,
        "sort_order": 1,
    },
    {
        "key": "javascript",
        "name": "JavaScript (Node.js)",
        "time_limit_s": 3.0,
        "memory_limit_mb": 256,
        "sort_order": 2,
    },
    {
        "key": "typescript",
        "name": "TypeScript",
        "time_limit_s": 5.0,
        "memory_limit_mb": 256,
        "sort_order": 3,
    },
    {"key": "java", "name": "Java", "time_limit_s": 4.0, "memory_limit_mb": 512, "sort_order": 4},
    {"key": "cpp", "name": "C++17", "time_limit_s": 2.0, "memory_limit_mb": 256, "sort_order": 5},
    {"key": "go", "name": "Go", "time_limit_s": 3.0, "memory_limit_mb": 256, "sort_order": 6},
]

STARTERS: dict[str, str] = {
    "python": """import sys


def main() -> None:
    data = sys.stdin.read().split()
    # Your solution here: read from `data`, print the answer.
    print()


if __name__ == "__main__":
    main()
""",
    "javascript": """const input = require("fs").readFileSync(0, "utf8").trim().split(/\\s+/);

function main() {
  // Your solution here: read from `input`, print the answer.
  console.log();
}

main();
""",
    "typescript": """declare function require(name: string): any;
const input: string[] = require("fs").readFileSync(0, "utf8").trim().split(/\\s+/);

function main(): void {
  // Your solution here: read from `input`, print the answer.
  console.log();
}

main();
""",
    "java": """import java.io.*;
import java.util.*;

public class Main {
    public static void main(String[] args) throws IOException {
        BufferedReader reader = new BufferedReader(new InputStreamReader(System.in));
        StreamTokenizer in = new StreamTokenizer(reader);
        // Your solution here: read with in.nextToken(), print the answer.
        System.out.println();
    }
}
""",
    "cpp": """#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    // Your solution here: read with cin, print the answer.
    cout << endl;
    return 0;
}
""",
    "go": """package main

import (
	"bufio"
	"fmt"
	"os"
)

func main() {
	reader := bufio.NewReader(os.Stdin)
	_ = reader // Your solution here: read with fmt.Fscan(reader, &x), print the answer.
	fmt.Println()
}
""",
}
