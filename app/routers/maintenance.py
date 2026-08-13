"""Wartungsmodus: Projekt-Tags (Update/Reboot je Servergruppe) und Bulk-Trigger."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import current_user
from ..schemas import MaintenanceBulkBody, MaintenanceTagBody
from ..services import maintenance

router = APIRouter(prefix="/api/maintenance", tags=["maintenance"],
                   dependencies=[Depends(current_user)])


@router.get("/tags")
def get_tags():
    return maintenance.list_tags()


@router.put("/tags/{project_id}")
def put_tag(project_id: int, body: MaintenanceTagBody):
    return maintenance.set_tag(project_id, body.update, body.reboot, body.server_group)


@router.post("/bulk/update")
def bulk_update(body: MaintenanceBulkBody):
    return maintenance.bulk_run("update", body.server_group, body.variables)


@router.post("/bulk/reboot")
def bulk_reboot(body: MaintenanceBulkBody):
    return maintenance.bulk_run("reboot", body.server_group, body.variables)
