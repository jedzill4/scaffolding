"""Engine/plan tests: clean-adds-only behavior, gating, deps, idempotency."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from scaffolding.components import AGENTS_MARKER, STANDARDS_MARKER
from scaffolding.engine import UnknownComponent, apply, build_plan, select_components
from scaffolding.facts import detect
from scaffolding.plan import Decisions, Disposition
from scaffolding.settings import Settings
from scaffolding.templates_registry import template_text

if TYPE_CHECKING:
    from pathlib import Path


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git_init(tmp_path)
    return tmp_path


def _facts(root: Path):
    return detect(root, probe_visibility=False)


def _targets(plan, disp: Disposition) -> list[str]:
    return [op.target for op in plan.by(disp)]


def test_nonpython_full_install_excludes_python_and_ci(repo: Path):
    plan = build_plan(repo, _facts(repo), Settings(skip_skills=True, skip_varlock=True))
    comps = {op.component for op in plan.ops}
    assert "ast-grep" not in comps
    assert "pyproject" not in comps
    assert "ci" not in comps
    assert ".gitignore" in _targets(plan, Disposition.ADD)
    assert "opencode.jsonc" in _targets(plan, Disposition.ADD)


def test_python_repo_includes_astgrep_and_pyproject(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(skip_skills=True, skip_varlock=True))
    targets = _targets(plan, Disposition.ADD)
    assert "sgconfig.yml" in targets
    assert "pyproject.toml" in targets
    keys = {d.key for d in plan.decisions}
    assert {"pyproject_name", "pyproject_description"} <= keys


def test_prek_pulls_astgrep_dependency_on_python(repo: Path):
    (repo / "pyproject.toml").write_text("[project]\nname='x'\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["prek"])
    comps = {op.component for op in plan.ops}
    assert "ast-grep" in comps
    assert any("required by prek" in n for n in plan.notices)


def test_no_deps_suppresses_dependency(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(no_deps=True), requested=["prek"])
    comps = {op.component for op in plan.ops}
    assert "ast-grep" not in comps


def test_explicit_selection_overrides_gate_with_notice(repo: Path):
    plan = build_plan(repo, _facts(repo), Settings(), requested=["pyproject"])
    assert any("gate not satisfied" in n for n in plan.notices)
    assert "pyproject.toml" in _targets(plan, Disposition.ADD)


def test_unknown_component_raises(repo: Path):
    with pytest.raises(UnknownComponent):
        build_plan(repo, _facts(repo), Settings(), requested=["nope"])


def test_apply_is_clean_adds_only_and_idempotent(repo: Path):
    settings = Settings(skip_skills=True, skip_varlock=True)
    plan = build_plan(repo, _facts(repo), settings)
    apply(plan, repo)
    assert (repo / ".gitignore").exists()
    assert (repo / "opencode.jsonc").exists()

    original = (repo / "opencode.jsonc").read_text()
    # Re-run: existing files must be deferred, not overwritten.
    plan2 = build_plan(repo, _facts(repo), settings)
    assert "opencode.jsonc" in _targets(plan2, Disposition.DEFER)
    apply(plan2, repo)
    assert (repo / "opencode.jsonc").read_text() == original


def test_pyproject_substitution(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    decisions = Decisions(pyproject_name="demo-pkg", pyproject_description="A demo")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["pyproject"], decisions=decisions)
    apply(plan, repo)
    body = (repo / "pyproject.toml").read_text()
    assert 'name = "demo-pkg"' in body
    assert 'description = "A demo"' in body
    assert "replace-me" not in body


def test_gitignore_partial_append(repo: Path):
    (repo / ".gitignore").write_text(".env\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["gitignore"])
    apply(plan, repo)
    lines = (repo / ".gitignore").read_text().splitlines()
    assert ".env" in lines
    assert ".journals/" in lines
    assert lines.count(".env") == 1


# test helper: a target->disposition lookup map is a legitimate dict boundary
# ast-grep-ignore: no-dict-return-annotation
def _standards_dispositions(plan) -> dict[str, Disposition]:
    return {op.target: op.disposition for op in plan.ops if op.component == "standards"}


def test_standards_clean_repo_adds_index_rules_snippets(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert "AGENTS.md" in adds
    assert ".agents/rules/no-dict.md" in adds
    assert ".agents/rules/file-size-guard.md" in adds
    assert "snippets/no-dict-boundary.py" in adds
    # the `agents` dependency is pulled in so AGENTS.md has a base to append to.
    assert any("required by standards" in n for n in plan.notices)


def test_standards_gated_out_on_nonpython(repo: Path):
    plan = build_plan(repo, _facts(repo), Settings(skip_skills=True, skip_varlock=True))
    comps = {op.component for op in plan.ops}
    assert "standards" not in comps


def test_standards_defers_and_skips_when_present(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    settings = Settings(skip_skills=True, skip_varlock=True)
    plan = build_plan(repo, _facts(repo), settings, requested=["standards"])
    apply(plan, repo)
    assert (repo / ".agents/rules/no-dict.md").exists()
    assert (repo / "snippets/no-dict-boundary.py").exists()
    body = (repo / "AGENTS.md").read_text()
    assert STANDARDS_MARKER in body
    assert AGENTS_MARKER in body

    plan2 = build_plan(repo, _facts(repo), settings, requested=["standards"])
    disp = _standards_dispositions(plan2)
    assert disp[".agents/rules/no-dict.md"] is Disposition.DEFER
    assert disp[".agents/rules/file-size-guard.md"] is Disposition.DEFER
    assert disp["snippets/no-dict-boundary.py"] is Disposition.DEFER
    assert disp["AGENTS.md"] is Disposition.SKIP

    # Re-apply must not duplicate the section or overwrite the workspace-defaults section.
    apply(plan2, repo)
    body2 = (repo / "AGENTS.md").read_text()
    assert body2.count(STANDARDS_MARKER) == 1
    assert AGENTS_MARKER in body2


def test_standards_logging_family_adds_details_and_snippet(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/log-get-logger.md" in adds
    assert ".agents/rules/log-no-print.md" in adds
    assert ".agents/rules/core-logger.md" in adds
    assert "snippets/core/logger.py" in adds


def test_astgrep_ships_logging_rules(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["ast-grep"])
    adds = {op.target for op in plan.by(Disposition.ADD) if op.component == "ast-grep"}
    assert "ast-grep/rules/log-get-logger.yml" in adds
    assert "ast-grep/rules/log-no-print.yml" in adds


def test_logging_rules_embed_ces_codes_and_warn_severity():
    for slug, code in (("log-get-logger", "CES-45"), ("log-no-print", "CES-46")):
        body = template_text(f"ast-grep-rules/{slug}.yml")
        assert f"{code} ({slug})" in body
        assert f"id: {slug}" in body
        assert "severity: warning" in body
        assert "severity: info" not in body
    # log-no-print exempts CLI entrypoints.
    no_print = template_text("ast-grep-rules/log-no-print.yml")
    assert "__main__" in no_print
    # core-logger snippet drop-in is present and structlog-based.
    snippet = template_text("snippets/core/logger.py")
    assert "structlog" in snippet
    assert "def get_logger" in snippet


def test_standards_api_schemas_rule_adds_detail_and_snippet(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/api-schemas-extra-forbid.md" in adds
    assert "snippets/api-schemas.py" in adds


def test_astgrep_ships_api_schemas_rule(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["ast-grep"])
    adds = {op.target for op in plan.by(Disposition.ADD) if op.component == "ast-grep"}
    assert "ast-grep/rules/api-schemas-extra-forbid.yml" in adds


def test_api_schemas_rule_is_ces_coded_and_placement_scoped():
    body = template_text("ast-grep-rules/api-schemas-extra-forbid.yml")
    assert "CES-4 (api-schemas-extra-forbid)" in body
    assert "id: api-schemas-extra-forbid" in body
    assert "severity: warning" in body
    assert "severity: info" not in body
    # placement-scoped via files: so it is inert outside api/ schema packages.
    assert "**/api/**/schemas/requests/**/*.py" in body
    assert "**/api/**/schemas/responses/**/*.py" in body


def test_standards_settings_module_rule_adds_detail_and_snippet(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/settings-module.md" in adds
    assert "snippets/settings.py" in adds


def test_astgrep_ships_settings_module_rule(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["ast-grep"])
    adds = {op.target for op in plan.by(Disposition.ADD) if op.component == "ast-grep"}
    assert "ast-grep/rules/settings-module.yml" in adds


def test_settings_module_rule_is_ces_coded_and_exempts_settings():
    body = template_text("ast-grep-rules/settings-module.yml")
    assert "CES-76 (settings-module)" in body
    assert "id: settings-module" in body
    assert "severity: warning" in body
    assert "severity: info" not in body
    # the settings module itself is exempt so it can read env.
    assert "**/settings.py" in body
    snippet = template_text("snippets/settings.py")
    assert "BaseSettings" in snippet
    assert "def get_settings" in snippet


def test_standards_cli_framework_rule_adds_detail(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/cli-typed-framework.md" in adds


def test_astgrep_ships_cli_framework_rule(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["ast-grep"])
    adds = {op.target for op in plan.by(Disposition.ADD) if op.component == "ast-grep"}
    assert "ast-grep/rules/cli-typed-framework.yml" in adds


def test_cli_framework_rule_is_ces_coded_and_warns():
    body = template_text("ast-grep-rules/cli-typed-framework.yml")
    assert "CES-67 (cli-typed-framework)" in body
    assert "id: cli-typed-framework" in body
    assert "severity: warning" in body  # encouraged, not mandated
    assert "severity: info" not in body
    assert "argparse" in body
    assert "sys.argv" in body


def test_standards_database_package_rule_adds_detail(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/arch-database-package.md" in adds


def test_astgrep_ships_database_package_rule(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["ast-grep"])
    adds = {op.target for op in plan.by(Disposition.ADD) if op.component == "ast-grep"}
    assert "ast-grep/rules/arch-database-package.yml" in adds


def test_database_package_rule_is_ces_coded_and_placement_scoped():
    body = template_text("ast-grep-rules/arch-database-package.yml")
    assert "CES-18 (arch-database-package)" in body
    assert "id: arch-database-package" in body
    assert "severity: warning" in body
    assert "severity: info" not in body
    # scoped to the common wrong homes; inert in a correct database/ package.
    assert "**/persistence/**/*.py" in body
    assert "**/core/**/*.py" in body


def test_standards_repo_hygiene_rules_add_details(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/no-utils.md" in adds
    assert ".agents/rules/repo-shape.md" in adds


def test_prek_plan_ships_repo_hygiene_hooks(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["prek"])
    prek_ops = [op for op in plan.by(Disposition.ADD) if op.target == "prek.toml"]
    assert prek_ops, "expected a prek.toml ADD op"
    content = prek_ops[0].content or ""
    assert 'id = "no-utils"' in content
    assert 'id = "repo-shape"' in content


def test_repo_hygiene_hooks_are_ces_coded():
    prek = template_text("prek-python.toml")
    assert "CES-63 (no-utils)" in prek
    assert 'id = "no-utils"' in prek
    assert "CES-32 (repo-shape)" in prek
    assert 'id = "repo-shape"' in prek
    # repo-shape carries the copier-style placeholder the agent fills at install time.
    assert "{{ import_package }}" in prek


def test_standards_conventional_commits_adds_detail(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/agents-conventional-commits.md" in adds


def test_prek_plan_ships_commit_msg_hook(repo: Path):
    plan = build_plan(repo, _facts(repo), Settings(), requested=["prek"])
    prek_ops = [op for op in plan.by(Disposition.ADD) if op.target == "prek.toml"]
    assert prek_ops, "expected a prek.toml ADD op"
    content = prek_ops[0].content or ""
    assert 'id = "agents-conventional-commits"' in content
    assert 'stages = ["commit-msg"]' in content


def test_ci_plan_ships_conventional_commits_workflow(repo: Path):
    plan = build_plan(repo, _facts(repo), Settings(), requested=["ci"])
    adds = {op.target for op in plan.by(Disposition.ADD) if op.component == "ci"}
    assert ".github/workflows/conventional-commits.yml" in adds


def test_conventional_commits_artifacts_are_ces_coded():
    prek = template_text("prek-generic.toml")
    assert "CES-75 (agents-conventional-commits)" in prek
    assert 'id = "agents-conventional-commits"' in prek
    wf = template_text("github/workflows/conventional-commits.yml")
    assert "CES-75 (agents-conventional-commits)" in wf
    # title read from env, never interpolated into the shell (injection-safe).
    assert "PR_TITLE: ${{ github.event.pull_request.title }}" in wf


def test_standards_pyproject_layer_rules_add_details(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["standards"])
    disp = _standards_dispositions(plan)
    adds = {t for t, d in disp.items() if d is Disposition.ADD}
    assert ".agents/rules/import-linter.md" in adds
    assert ".agents/rules/api-boundary-layout.md" in adds


def test_pyproject_plan_adds_on_clean_defers_on_existing(repo: Path):
    (repo / "app.py").write_text("x = 1\n")
    plan = build_plan(repo, _facts(repo), Settings(), requested=["pyproject"])
    assert "pyproject.toml" in _targets(plan, Disposition.ADD)
    apply(plan, repo)
    plan2 = build_plan(repo, _facts(repo), Settings(), requested=["pyproject"])
    assert "pyproject.toml" in _targets(plan2, Disposition.DEFER)


def test_pyproject_template_version_pin_and_importlinter_skeleton():
    body = template_text("pyproject-template.toml")
    # CES-77: requires-python is a non-enforced comment defaulting to 3.14.
    assert "CES-77 (version pin)" in body
    assert '# requires-python = ">=3.14"' in body
    # the active requires-python line is gone (commented only).
    active = [ln for ln in body.splitlines() if ln.strip().startswith("requires-python")]
    assert active == []
    # CES-5 / CES-17: commented import-linter skeleton present.
    assert "# [tool.importlinter]" in body
    assert "Layered architecture (CES-5)" in body
    assert "CES-17" in body


def test_ces_codes_embedded_in_as_built_rule_messages():
    for slug in (
        "no-dict-call-return",
        "no-dict-literal-return",
        "no-dict-return-annotation",
        "no-dict-alias",
    ):
        body = template_text(f"ast-grep-rules/{slug}.yml")
        assert f"CES-79 ({slug})" in body
        assert f"id: {slug}" in body  # slug / suppression key unchanged
    prek = template_text("prek-python.toml")
    assert "CES-71 (file-size-guard)" in prek
    assert 'id = "file-size-guard"' in prek  # prek hook id (suppression key) unchanged


def test_select_skip(repo: Path):
    comps, _ = select_components([], ["opencode"], _facts(repo), Settings(skip_skills=True))
    names = {c.name for c in comps}
    assert "opencode" not in names
    assert "gitignore" in names
