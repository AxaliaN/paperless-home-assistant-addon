#!/usr/bin/env python3
import re
import subprocess
import sys

IMAGE = "debian:trixie"
PIN = re.compile(r'^(\s+)([a-z0-9][a-z0-9.+-]*)=([^\s"\\]+)(\s*"?\s*\\?)$')
BLOCK = re.compile(r'^ARG [A-Z0-9_]+_PACKAGES="')
ENV = re.compile(r'^ENV ([A-Z0-9_]+)="([^"]*)"$')
VAR = re.compile(r"^\$\{([A-Z0-9_]+)\}$")


def candidates(packages):
    script = "apt-get update -qq >/dev/null && apt-cache policy " + " ".join(packages)
    out = subprocess.run(
        ["docker", "run", "--rm", IMAGE, "sh", "-c", script],
        check=True, capture_output=True, text=True,
    ).stdout
    result, current = {}, None
    for line in out.splitlines():
        if line and not line.startswith(" ") and line.endswith(":"):
            current = line[:-1]
        elif current and line.strip().startswith("Candidate:"):
            value = line.split(":", 1)[1].strip()
            if value != "(none)":
                result[current] = value
    return result


def main(path):
    lines = open(path).read().split("\n")
    env = {m[1]: m[2] for m in map(ENV.match, lines) if m}
    pins, inside = [], False
    for i, line in enumerate(lines):
        if BLOCK.match(line):
            inside = True
            continue
        if inside:
            m = PIN.match(line)
            if m:
                pins.append((i, m))
            if line.rstrip().endswith('"'):
                inside = False
    found = candidates(sorted({m[2] for _, m in pins}))
    changes, env_updates = [], {}

    for i, m in pins:
        indent, package, value, tail = m.groups()
        candidate = found.get(package)
        if candidate is None:
            print(f"warning: no candidate for {package}", file=sys.stderr)
            continue
        var = VAR.match(value)
        if var:
            name = var[1]
            if env.get(name) != candidate:
                previous = env_updates.setdefault(name, candidate)
                if previous != candidate:
                    print(f"warning: {name} conflicts ({previous} vs {candidate})", file=sys.stderr)
        elif value != candidate:
            lines[i] = f"{indent}{package}={candidate}{tail}"
            changes.append(f"{package}: {value} -> {candidate}")

    for i, line in enumerate(lines):
        m = ENV.match(line)
        if m and m[1] in env_updates:
            lines[i] = f'ENV {m[1]}="{env_updates[m[1]]}"'
            changes.append(f"{m[1]}: {m[2]} -> {env_updates[m[1]]}")

    open(path, "w").write("\n".join(lines))
    print("\n".join(changes) if changes else "pins up to date")


if __name__ == "__main__":
    main(sys.argv[1])
