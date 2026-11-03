from suite.common import REPO_ROOT
from suite.demo_accounts import (
    DEMO_USERS,
    USER_DETAILS_FILE,
    check_password,
    explain_login_failure,
    find_user,
    hash_password,
    reset_demo_password,
    seed_users,
)
import ast


def test_seed_creates_demo_users_once(tmp_path):
    db = tmp_path / "sl_planning.db"
    assert seed_users(db) == len(DEMO_USERS)
    assert seed_users(db) == 0
    import sqlite3
    names = {r[0] for r in sqlite3.connect(db).execute("SELECT username FROM users")}
    assert names == {u[0] for u in DEMO_USERS}


def test_password_verifier_is_not_wrapped_in_streamlit_dialog():
    hub_path = REPO_ROOT / "hub.py"
    tree = ast.parse(hub_path.read_text(encoding="utf-8"))
    fn = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_check_password")
    assert fn.decorator_list == []


def test_seed_does_not_overwrite_a_changed_password(tmp_path):
    db = tmp_path / "sl_planning.db"
    seed_users(db)
    import sqlite3
    con = sqlite3.connect(db)
    con.execute("UPDATE users SET password_hash=? WHERE username='admin'", (hash_password("factory-secret"),))
    con.commit()
    con.close()
    assert seed_users(db) == 0
    row = sqlite3.connect(db).execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
    assert check_password("factory-secret", row)
    assert not check_password("admin123", row)
    why = explain_login_failure(db, "admin", "admin123")
    assert "not the demo password" in why
    assert "admin123" not in why
    assert "user details.txt" in why
    assert reset_demo_password(db, "ADMIN") is True
    assert find_user(db, "admin")["username"] == "admin"
    row2 = __import__("sqlite3").connect(db).execute("SELECT password_hash FROM users WHERE username='admin'").fetchone()[0]
    assert check_password("admin123", row2)


def test_planning_demo_reset_restores_planning123(tmp_path):
    db = tmp_path / "sl_planning.db"
    seed_users(db)
    import sqlite3
    sqlite3.connect(db).execute(
        "UPDATE users SET password_hash=? WHERE username='planning'", (hash_password("old-planning"),)
    ).connection.commit()
    why = explain_login_failure(db, "Planning", "planning123")
    assert "planning" in why.lower() and "not the demo password" in why
    assert "planning123" not in why
    assert reset_demo_password(db, "planning")
    row = find_user(db, "PLANNING")
    assert check_password("planning123", row["password_hash"])


def test_user_details_file_lists_demo_logins_and_ui_does_not():
    text = (REPO_ROOT / USER_DETAILS_FILE).read_text(encoding="utf-8")
    assert USER_DETAILS_FILE == "user details.txt"
    for username, password, _role, _display in DEMO_USERS:
        assert f"{username} / {password}" in text
    hub = (REPO_ROOT / "hub.py").read_text(encoding="utf-8")
    login_html = (REPO_ROOT / "apps" / "mobile" / "templates" / "login.html").read_text(encoding="utf-8")
    for _username, password, _role, _display in DEMO_USERS:
        assert password not in hub
        assert password not in login_html
    assert "user details.txt" in hub
    assert "user details.txt" in login_html
    assert "DEMO_HINT" not in hub
