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


def _stub_pipeline_and_jobs(monkeypatch, jobs_by_pid):
    """jobs_by_pid: project_id -> Liste von {'id','name'} der letzten Pipeline."""
    monkeypatch.setattr(maintenance.pipelines, "latest_pipeline",
                        lambda pid: {"id": pid * 100})
    monkeypatch.setattr(maintenance.pipelines, "pipeline_jobs",
                        lambda pid, pipeline_id: jobs_by_pid.get(pid, []))
    played = []
    monkeypatch.setattr(maintenance.pipelines, "job_action",
                        lambda pid, job_id, action: played.append((pid, job_id, action)))
    return played


def test_bulk_update_plays_apt_jobs_for_linux(monkeypatch):
    _tag(1, True, False, "linux-intern")     # nur Update
    _tag(2, True, True, "linux-intern")      # Update + Reboot
    _tag(3, True, False, "windows")          # andere Gruppe
    monkeypatch.setattr(maintenance, "_project_names",
                        lambda: {"1": "a", "2": "b", "3": "c"})
    jobs = {pid: [{"id": pid * 10 + 1, "name": "apt-update"},
                  {"id": pid * 10 + 2, "name": "apt-upgrade"},
                  {"id": pid * 10 + 3, "name": "system-reboot"}]
            for pid in (1, 2, 3)}
    played = _stub_pipeline_and_jobs(monkeypatch, jobs)

    update_result = maintenance.bulk_run("update", "linux-intern")
    assert {t["project_id"] for t in update_result["triggered"]} == {1, 2}
    assert all(t["jobs"] == ["apt-update", "apt-upgrade"] for t in update_result["triggered"])
    assert (1, 11, "play") in played and (1, 12, "play") in played

    played.clear()
    reboot_result = maintenance.bulk_run("reboot", "linux-intern")
    assert {t["project_id"] for t in reboot_result["triggered"]} == {2}
    assert played == [(2, 23, "play")]


def test_bulk_update_plays_windows_job(monkeypatch):
    _tag(1, True, False, "windows")
    monkeypatch.setattr(maintenance, "_project_names", lambda: {"1": "a"})
    jobs = {1: [{"id": 5, "name": "windows-updates-install"}]}
    _stub_pipeline_and_jobs(monkeypatch, jobs)

    result = maintenance.bulk_run("update", "windows")
    assert result["triggered"] == [{"project_id": 1, "name": "a",
                                    "jobs": ["windows-updates-install"]}]


def test_cron_stop_targets_update_tagged_projects(monkeypatch):
    _tag(1, True, False, "linux-extern")
    monkeypatch.setattr(maintenance, "_project_names", lambda: {"1": "a"})
    _stub_pipeline_and_jobs(monkeypatch, {1: [{"id": 9, "name": "cron-stop"}]})

    result = maintenance.bulk_run("cron-stop", "linux-extern")
    assert [t["project_id"] for t in result["triggered"]] == [1]


def test_cron_stop_not_available_for_windows():
    with pytest.raises(HTTPException) as exc:
        maintenance.bulk_run("cron-stop", "windows")
    assert exc.value.status_code == 400


def test_missing_job_in_latest_pipeline_is_reported_as_failure(monkeypatch):
    _tag(1, True, False, "windows")
    _tag(2, True, False, "windows")
    monkeypatch.setattr(maintenance, "_project_names", lambda: {"1": "a", "2": "b"})
    # Projekt 1 hat den erwarteten Job nicht (z.B. Template nicht eingebunden)
    _stub_pipeline_and_jobs(monkeypatch, {2: [{"id": 20, "name": "windows-updates-install"}]})

    result = maintenance.bulk_run("update", "windows")
    assert [f["project_id"] for f in result["failed"]] == [1]
    assert "windows-updates-install" in result["failed"][0]["error"]
    assert [t["project_id"] for t in result["triggered"]] == [2]


def test_no_pipeline_at_all_is_reported_as_failure(monkeypatch):
    _tag(1, True, False, "windows")
    monkeypatch.setattr(maintenance, "_project_names", lambda: {"1": "a"})
    monkeypatch.setattr(maintenance.pipelines, "latest_pipeline", lambda pid: None)

    result = maintenance.bulk_run("update", "windows")
    assert result["failed"][0]["project_id"] == 1
    assert "Keine Pipeline" in result["failed"][0]["error"]


def test_bulk_run_no_matching_projects_is_404():
    with pytest.raises(HTTPException) as exc:
        maintenance.bulk_run("update", "windows")
    assert exc.value.status_code == 404
