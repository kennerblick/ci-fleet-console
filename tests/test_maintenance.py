import pytest
from fastapi import HTTPException

from app import maintenance_store
from app.services import maintenance


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(maintenance_store, "_tags", {})
    monkeypatch.setattr(maintenance_store.config, "MAINTENANCE_TAGS_FILE",
                        tmp_path / "maintenance_tags.json")


def test_reboot_implies_update():
    entry = maintenance_store.set_tag(1, update=False, reboot=True,
                                      server_group="linux-intern")
    assert entry == {"update": True, "reboot": True, "server_group": "linux-intern"}


def test_invalid_server_group_rejected():
    with pytest.raises(HTTPException) as exc:
        maintenance_store.set_tag(1, update=True, reboot=False, server_group="mainframe")
    assert exc.value.status_code == 400


def test_both_false_removes_entry():
    maintenance_store.set_tag(1, update=True, reboot=False, server_group="windows")
    assert "1" in maintenance_store.get_all()
    result = maintenance_store.set_tag(1, update=False, reboot=False, server_group=None)
    assert result is None
    assert "1" not in maintenance_store.get_all()


def _tag(pid, update, reboot, group):
    maintenance_store.set_tag(pid, update=update, reboot=reboot, server_group=group)


def test_bulk_run_filters_by_group_and_action(monkeypatch):
    _tag(1, True, False, "linux-intern")     # update only
    _tag(2, True, True, "linux-intern")      # update + reboot
    _tag(3, True, False, "windows")          # andere Gruppe

    monkeypatch.setattr(maintenance, "_project_names",
                        lambda: {"1": "a", "2": "b", "3": "c"})
    monkeypatch.setattr(maintenance.pipelines, "run_pipeline",
                        lambda pid, ref, variables: {"id": pid, "status": "created"})

    update_result = maintenance.bulk_run("update", "linux-intern", [])
    assert {t["project_id"] for t in update_result["triggered"]} == {1, 2}

    reboot_result = maintenance.bulk_run("reboot", "linux-intern", [])
    assert {t["project_id"] for t in reboot_result["triggered"]} == {2}


def test_bulk_run_collects_failures_without_aborting(monkeypatch):
    _tag(1, True, False, "windows")
    _tag(2, True, False, "windows")
    monkeypatch.setattr(maintenance, "_project_names",
                        lambda: {"1": "a", "2": "b"})

    def fake_run(pid, ref, variables):
        if pid == 1:
            raise HTTPException(400, "GitLab-Fehler")
        return {"id": pid, "status": "created"}

    monkeypatch.setattr(maintenance.pipelines, "run_pipeline", fake_run)
    result = maintenance.bulk_run("update", "windows", [])
    assert [f["project_id"] for f in result["failed"]] == [1]
    assert [t["project_id"] for t in result["triggered"]] == [2]


def test_bulk_run_no_matching_projects_is_404(monkeypatch):
    monkeypatch.setattr(maintenance, "_project_names", lambda: {})
    with pytest.raises(HTTPException) as exc:
        maintenance.bulk_run("update", "windows", [])
    assert exc.value.status_code == 404
