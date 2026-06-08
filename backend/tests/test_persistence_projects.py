from across_agents_assistant.persistence.service import PersistenceService


def test_create_project_updates_existing_explicit_id_when_path_changes(tmp_path):
    service = PersistenceService(str(tmp_path / "assistant.db"))
    old_path = tmp_path / "old-home" / "workspace"
    new_path = tmp_path / "new-home" / "workspace"

    created = service.create_project(
        name="workspace",
        path=str(old_path),
        kind="blank",
        project_id="default-workspace",
    )
    assert created["id"] == "default-workspace"

    migrated = service.create_project(
        name="workspace",
        path=str(new_path),
        kind="blank",
        project_id="default-workspace",
        assign_unscoped_sessions=True,
    )
    assert migrated["id"] == "default-workspace"
    assert migrated["path"] == str(new_path.resolve())

    with service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, path FROM projects WHERE id = ?", ("default-workspace",))
        rows = [dict(row) for row in cursor.fetchall()]

    assert rows == [{"id": "default-workspace", "path": str(new_path.resolve())}]
