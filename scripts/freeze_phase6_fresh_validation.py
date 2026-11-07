from __future__ import annotations

import argparse
import json
from pathlib import Path

from dualrag.benchmark.fresh_validation import freeze_fresh_validation_inputs


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze Phase 6 predictions and models before revealing validation gold."
    )
    parser.add_argument("--input", action="append", required=True, metavar="NAME=PATH")
    parser.add_argument("--code-root", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    inputs: dict[str, Path] = {}
    for value in args.input:
        name, separator, path = value.partition("=")
        if not separator or not name or not path:
            parser.error(f"invalid --input {value!r}; expected NAME=PATH")
        inputs[name] = Path(path)
    manifest = freeze_fresh_validation_inputs(
        inputs=inputs,
        code_roots=args.code_root,
        output_path=args.output,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
