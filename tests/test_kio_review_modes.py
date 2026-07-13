import pytest

from kio.backends import _write_gito_profile_config, _write_review_comment
from kio.config import KioConfig
from kio.models import PullRequestContext, WorkItem
from kio.review_modes import resolve_review_profiles


def test_level_four_uses_four_independent_review_passes():
    profiles = resolve_review_profiles("level-4")

    assert [profile.name for profile in profiles] == [
        "correctness",
        "test-density",
        "stability",
        "performance",
    ]


def test_default_profiles_require_evidence_or_a_not_verified_marker():
    profiles = {
        profile.name: profile.instructions for profile in resolve_review_profiles("level-4")
    }

    assert "Not verified" in profiles["correctness"]
    assert "Not verified" in profiles["test-density"]
    assert "Not verified" in profiles["stability"]
    assert "Not verified" in profiles["performance"]


def test_local_templates_can_override_a_profile_and_level():
    config = KioConfig(
        review_levels={
            "1": ("project-basics",),
            "2": ("project-basics",),
            "3": ("project-basics",),
            "4": ("project-basics",),
        },
        review_templates={"project-basics": "Check the DreamBau domain rule."},
    )

    profiles = resolve_review_profiles(
        "level-1",
        level_profiles=config.review_levels,
        profile_templates=config.review_templates,
    )

    assert profiles[0].name == "project-basics"
    assert profiles[0].instructions == "Check the DreamBau domain rule."


def test_review_level_cannot_exceed_agent_limit():
    with pytest.raises(ValueError, match="above max_agents"):
        KioConfig(max_agents=3).validate()


def test_review_comment_exposes_scope_and_profile_evidence(tmp_path):
    report = tmp_path / "report.md"
    report.write_text(
        "Finding: cache invalidation can lose updates.\n<!-- marker -->\n", encoding="utf-8"
    )
    item = WorkItem(
        pull_request=PullRequestContext(
            repo_full_name="owner/repo",
            number=9,
            head_sha="abc123",
            head_ref="feature",
            base_ref="main",
            clone_url="https://github.com/owner/repo.git",
        ),
        source="comment",
        mode="level-1",
        raw_text="@kiocheck review 1",
    )
    profile = resolve_review_profiles("level-1")[0]

    out = _write_review_comment(
        item, run_dir=tmp_path, reports=[(profile, report)], rules_file=None
    )

    content = out.read_text(encoding="utf-8")
    assert "## kiocheck review: Level 1" in content
    assert "### Scope" in content
    assert "### Basic" in content
    assert "cache invalidation" in content
    assert "<!-- marker -->" not in content


def test_gito_profile_overlay_preserves_project_rules_and_template(tmp_path):
    config_path = tmp_path / ".gito" / "config.toml"
    config_path.parent.mkdir()
    original_config = '[prompt_vars]\nrequirements = "existing project rule"\n'
    config_path.write_text(original_config, encoding="utf-8")
    rules_file = tmp_path / "rules.md"
    rules_file.write_text("AGENTS.md rule", encoding="utf-8")

    _write_gito_profile_config(
        config_path,
        original_config=original_config,
        profile=resolve_review_profiles("level-4")[2],
        rules_file=rules_file,
    )

    content = config_path.read_text(encoding="utf-8")
    assert "existing project rule" in content
    assert "AGENTS.md rule" in content
    assert "Profile: Stability" in content
