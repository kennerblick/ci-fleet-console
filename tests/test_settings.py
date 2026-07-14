from app import settings_store


def test_user_overrides_default(monkeypatch):
    monkeypatch.setattr(settings_store, "_settings", {
        "default": {"gitlab_url": "https://git", "private_token": "STD",
                    "group_path": "devops", "selected_groups": [],
                    "templates_project": "", "templates_dir": "standard"},
        "users": {"alice": {"private_token": "OWN",
                              "group_path": "devops/linux",
                              "selected_groups": []}},
    })
    default = settings_store.effective(None)
    assert default["private_token"] == "STD" and not default["_own_token"]

    own = settings_store.effective("Alice")           # case-insensitive
    assert own["private_token"] == "OWN"
    assert own["group_path"] == "devops/linux"
    assert own["_own_token"]
    # leere Auswahl des Nutzers gilt (= alle), ueberschreibt nicht mit Default
    assert own["selected_groups"] == []


def test_scope_differs_per_token(monkeypatch):
    base = {"gitlab_url": "u", "group_path": "g", "selected_groups": [],
            "templates_project": "", "templates_dir": "standard"}
    monkeypatch.setattr(settings_store, "_settings", {
        "default": {**base, "private_token": "A"},
        "users": {"b": {"private_token": "B"}},
    })
    settings_store.set_context(None)
    scope_default = settings_store.scope_key()
    settings_store.set_context("b")
    scope_b = settings_store.scope_key()
    assert scope_default != scope_b
