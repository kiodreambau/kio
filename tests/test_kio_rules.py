from kio.config import KioConfig
from kio.rules import collect_rules, write_rules_bundle


def test_collect_rules_prefers_checkout_rules(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "AGENTS.md").write_text("target repo rules\n", encoding="utf-8")

    records = collect_rules(KioConfig(rules_files=("AGENTS.md",)), checkout_dir=checkout)

    assert len(records) == 1
    assert records[0][1] == "target repo rules\n"


def test_write_rules_bundle(tmp_path):
    rules_file = tmp_path / "rules.md"
    rules_file.write_text("owner rules\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    out = write_rules_bundle(
        KioConfig(rules_files=(str(rules_file),)),
        run_dir=run_dir,
    )

    assert out == run_dir / "rules.md"
    assert "owner rules" in out.read_text(encoding="utf-8")
