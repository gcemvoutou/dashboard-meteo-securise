from src import manage_users

PASSWORD = "Tr0ub4dor&Meteo!"


def test_add_list_unlock_delete(monkeypatch, capsys):
    monkeypatch.setattr(manage_users.getpass, "getpass", lambda prompt="": PASSWORD)
    assert manage_users.main(["add", "cli-user"]) == 0
    assert manage_users.main(["list"]) == 0
    assert "cli-user" in capsys.readouterr().out
    assert manage_users.main(["unlock", "cli-user"]) == 0
    assert manage_users.main(["delete", "cli-user"]) == 0


def test_add_rejects_weak_password(monkeypatch):
    monkeypatch.setattr(manage_users.getpass, "getpass", lambda prompt="": "faible")
    assert manage_users.main(["add", "weak-user"]) == 1


def test_add_rejects_mismatch(monkeypatch):
    answers = iter([PASSWORD, "autre"])
    monkeypatch.setattr(manage_users.getpass, "getpass", lambda prompt="": next(answers))
    assert manage_users.main(["add", "mismatch"]) == 1
