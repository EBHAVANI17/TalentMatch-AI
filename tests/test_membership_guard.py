"""Guard: organization access must come from memberships, not the users.organization_id / users.role mirror.

Fails when application code reads or writes User.organization_id / User.role outside
services/membership_service.py, unless the line is marked `# membership-guard: ok (<reason>)`
(platform roles, the default-organization fallback, admin display). Migrations live outside app/.
"""
import ast
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "backend" / "app"
ALLOWED_FILES = {APP / "services" / "membership_service.py"}
MARKER = "membership-guard: ok"
# A marker counts only with a reason: "# membership-guard: ok (platform role)"
MARKER_WITH_REASON = re.compile(r"#\s*membership-guard: ok \(\s*[^)\s][^)]*\)")
FIELDS = {"organization_id", "role"}
# Names that hold a User in this codebase (attribute access on anything else, e.g. job.organization_id, is fine)
USER_NAMES = {"user", "current_user", "target", "u", "existing", "actor", "invited_by", "person", "member", "User"}


def _user_attribute_accesses(tree: ast.AST):
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FIELDS:
            base = node.value
            if isinstance(base, ast.Name) and base.id in USER_NAMES:
                yield node
            elif isinstance(base, ast.Attribute) and base.attr == "user":  # ctx.user.role, m.user.organization_id
                yield node


def test_no_unmarked_reads_of_the_membership_mirror():
    offenders = []
    for path in APP.rglob("*.py"):
        if path in ALLOWED_FILES:
            continue
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for node in _user_attribute_accesses(ast.parse(source)):
            line = lines[node.lineno - 1]
            if not MARKER_WITH_REASON.search(line):
                reason = "marker without a reason" if MARKER in line else "unmarked"
                offenders.append(f"{path.relative_to(APP)}:{node.lineno} ({reason}): {line.strip()}")
    assert not offenders, (
        "Use memberships (TenantContext.org_id / .role, membership_service) instead of the users mirror:\n"
        + "\n".join(offenders)
    )


def test_guard_catches_a_violation():
    tree = ast.parse("if current_user.role == 'ORG_ADMIN' and ctx.user.organization_id == job.organization_id: pass")
    found = sorted((n.value.id if isinstance(n.value, ast.Name) else "ctx.user", n.attr) for n in _user_attribute_accesses(tree))
    assert found == [("ctx.user", "organization_id"), ("current_user", "role")]


def test_markers_need_a_reason():
    assert MARKER_WITH_REASON.search("x = user.role  # membership-guard: ok (platform role)")
    for bare in ("x = user.role  # membership-guard: ok", "x = user.role  # membership-guard: ok ()",
                 "x = user.role  # membership-guard: ok (   )"):
        assert not MARKER_WITH_REASON.search(bare), bare
