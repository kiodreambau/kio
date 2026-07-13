"""Collect project and owner review rules for local backend runs."""

from pathlib import Path

from .config import KioConfig


def collect_rules(config: KioConfig, *, checkout_dir: Path | None = None) -> list[tuple[Path, str]]:
    records: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    for raw_path in config.rules_files:
        for candidate in _candidate_paths(raw_path, checkout_dir=checkout_dir):
            if not candidate.exists() or not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            records.append((resolved, candidate.read_text(encoding="utf-8")))
            break
    return records


def write_rules_bundle(
    config: KioConfig,
    *,
    run_dir: Path,
    checkout_dir: Path | None = None,
) -> Path | None:
    records = collect_rules(config, checkout_dir=checkout_dir)
    if not records:
        return None
    out = run_dir / "rules.md"
    lines: list[str] = ["# kio review rules", ""]
    for path, content in records:
        lines.extend(
            [
                f"## {path}",
                "",
                content.rstrip(),
                "",
            ]
        )
    out.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out


def _candidate_paths(raw_path: str, *, checkout_dir: Path | None) -> list[Path]:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return [path]
    candidates = []
    if checkout_dir:
        candidates.append(checkout_dir / path)
    candidates.append(Path.cwd() / path)
    return candidates
