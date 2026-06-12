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


def test_persistence_ignores_old_across_agents_workspace_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ACROSS_AGENTS_HOME", raising=False)
    db_path = tmp_path / "assistant.db"
    service = PersistenceService(str(db_path))
    old_project = tmp_path / ".across_agents" / "workspace" / "readme-demo"
    old_project.mkdir(parents=True)

    project = service.create_project(
        name="readme-demo",
        path=str(old_project),
        kind="blank",
        project_id="readme-demo-project",
    )
    service.get_or_create_session("session-1")
    with service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE sessions SET project_id = ?, project_dir = ? WHERE id = ?",
            (project["id"], project["path"], "session-1"),
        )
        cursor.execute(
            """INSERT INTO tasks
               (task_id, description, status, project_dir)
               VALUES (?, ?, ?, ?)""",
            ("task-1", "legacy workspace task", "created", project["path"]),
        )

    PersistenceService(str(db_path))

    with service.db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT path FROM projects WHERE id = ?", ("readme-demo-project",))
        assert cursor.fetchone()["path"] == str(old_project.resolve())
        cursor.execute("SELECT project_dir FROM sessions WHERE id = ?", ("session-1",))
        assert cursor.fetchone()["project_dir"] == str(old_project.resolve())
        cursor.execute("SELECT project_dir FROM tasks WHERE task_id = ?", ("task-1",))
        assert cursor.fetchone()["project_dir"] == str(old_project.resolve())
