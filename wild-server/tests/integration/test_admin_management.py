"""管理权限、额度、审计和蓝图锁的真实 HTTP/仓储回归，不调用模型。"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select

from app.api.exception_handlers import install_exception_handlers
from app.api.http import admin, auth, blueprints, designs, sessions
from app.api.middleware import enforce_write_access
from app.application.accounts import hash_password, open_session, public_account
from app.application.administration import blueprint_metrics
from app.infrastructure.persistence.repositories.accounts import accounts
from app.infrastructure.persistence.repositories.activity import (
    charge_ai_request,
    charge_usage,
)
from app.infrastructure.persistence.repositories.blueprints import blueprint_repository
from app.infrastructure.persistence.repositories.conversations import conversations
from app.infrastructure.persistence.repositories.errors import (
    BlueprintLocked,
    OperationConflict,
    QuotaExceeded,
)
from app.infrastructure.persistence.repositories.jobs import JobRepository
from app.infrastructure.persistence.schema import (
    audit_logs,
    blueprints as blueprint_table,
    users,
)

PASSWORD = "Admin-feature-test-123"


@pytest.fixture
def management(storage):
    seeded = {}
    for name in ("admin", "designer", "other"):
        seeded[name] = accounts.create(
            name, name + "@example.com", hash_password(PASSWORD)
        )
    with storage.begin() as connection:
        connection.execute(
            users.update().where(users.c.id == seeded["admin"]["id"]).values(identity=2)
        )
    seeded["admin"].update(identity=2, role="editor")
    app = FastAPI()
    install_exception_handlers(app)
    app.middleware("http")(enforce_write_access)
    for route in (
        auth.router,
        admin.router,
        blueprints.router,
        sessions.router,
        designs.router,
    ):
        app.include_router(route)

    @app.api_route("/api/config/llm", methods=["GET", "POST"])
    def model_configuration():
        return {"api_key_set": True}

    @app.post("/api/config/llm/test")
    def model_test():
        return {"ok": True}

    with TestClient(app) as client:
        yield client, seeded, storage


def login(client, name="admin"):
    response = client.post(
        "/api/auth/login", json={"email": name + "@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    return response.json()


def scene(radius=0.5, revision=1):
    return {
        "meta": {"version": "1.0", "type": "building", "name": "管理测试蓝图"},
        "geometry": {
            "elements": [
                {
                    "id": "sphere",
                    "type": "primitive",
                    "shape": "sphere",
                    "position": [0, 0.5, 0],
                    "radius": radius,
                }
            ],
            "components": [],
        },
        "materials": {},
        "editor": {"revision": revision},
    }


def save_owned(seeded, filename="session_manage_scene.wild"):
    blueprint_repository.save(filename, scene(), owner_id=seeded["designer"]["id"])
    return filename


def test_admin_routes_and_model_configuration_require_admin(management):
    client, seeded, _ = management
    for path in (
        "/api/admin/stats",
        "/api/admin/users",
        "/api/admin/logs",
        "/api/admin/blueprints",
        "/api/admin/blueprints/missing.wild/metrics",
    ):
        assert client.get(path).status_code == 401
    user = login(client, "designer")
    assert user["usage"]["operations"]["remaining"] == 1000
    assert user["usage"]["modifications"]["remaining"] == 200
    assert user["usage"]["generations"]["remaining"] == 20
    for path in (
        "/api/admin/stats",
        "/api/admin/users",
        "/api/admin/logs",
        "/api/admin/blueprints",
        "/api/admin/blueprints/missing.wild/metrics",
        "/api/config/llm",
    ):
        assert client.get(path).status_code == 403
    assert (
        client.patch("/api/admin/users/" + user["id"], json={"identity": 2}).status_code
        == 403
    )
    assert client.post("/api/config/llm", json={"name": "blocked"}).status_code == 403
    assert client.post("/api/config/llm/test", json={}).status_code == 403
    login(client)
    result = client.get("/api/admin/users").json()
    assert result["total"] == 3
    assert "password_hash" not in json.dumps(result)
    assert client.get("/api/admin/stats").json()["users"] == 3


def test_role_quota_and_ban_changes_take_effect_for_existing_session(management):
    client, seeded, _ = management
    login(client, "designer")
    token = client.cookies.get("wild_session")
    user_id = seeded["designer"]["id"]
    login(client)
    token = open_session(public_account(accounts.get(user_id)))
    result = client.patch(
        "/api/admin/users/" + user_id,
        json={
            "identity": 2,
            "operations_remaining": 7,
            "modifications_remaining": 8,
            "generations_remaining": 9,
        },
    )
    assert result.status_code == 200
    admin_token = client.cookies.get("wild_session")
    client.cookies.set("wild_session", token)
    assert client.get("/api/auth/session").json()["is_admin"] is True
    assert (
        client.get("/api/auth/session").json()["usage"]["operations"]["remaining"]
        is None
    )
    assert client.get("/api/admin/stats").status_code == 200
    client.cookies.set("wild_session", admin_token)
    assert (
        client.patch(
            "/api/admin/users/" + user_id, json={"identity": 1, "status": "blocked"}
        ).status_code
        == 200
    )
    client.cookies.set("wild_session", token)
    assert client.get("/api/auth/session").json() is None
    assert client.put("/api/scenes/denied.wild", json=scene()).status_code == 401
    client.cookies.set("wild_session", admin_token)
    assert (
        client.patch(
            "/api/admin/users/" + user_id, json={"status": "active"}
        ).status_code
        == 200
    )
    client.cookies.set("wild_session", token)
    assert (
        client.get("/api/auth/session").json()["usage"]["generations"]["remaining"] == 9
    )
    assert client.get("/api/admin/stats").status_code == 403


def test_deleted_account_keeps_private_data_and_audit_ownership(management):
    client, seeded, _ = management
    filename = save_owned(seeded)
    login(client, "designer")
    token = client.cookies.get("wild_session")
    login(client)
    user_id = seeded["designer"]["id"]
    assert client.delete("/api/admin/users/" + user_id).status_code == 200
    assert blueprint_repository.get(filename)["owner_id"] == user_id
    result = client.get("/api/admin/logs", params={"user_id": user_id}).json()
    assert result["total"] > 0 and result["items"][0]["actor_name"] == "designer"
    assert (
        client.patch(
            "/api/admin/users/" + user_id, json={"status": "active"}
        ).status_code
        == 404
    )
    client.cookies.set("wild_session", token)
    assert client.get("/api/auth/session").json() is None
    client.post("/api/auth/guest")
    assert client.get("/api/scenes/" + filename).status_code == 404
    assert all(
        item["filename"] != filename for item in client.get("/api/scenes").json()
    )


@pytest.mark.parametrize("change", [{"identity": 1}, {"status": "blocked"}])
def test_current_admin_cannot_remove_own_access(management, change):
    client, seeded, _ = management
    login(client)
    path = "/api/admin/users/" + seeded["admin"]["id"]
    assert client.patch(path, json=change).status_code == 409
    assert client.delete(path).status_code == 409
    assert client.get("/api/admin/stats").json()["administrators"] == 1


def test_manual_edits_are_atomic_idempotent_and_audited(management):
    client, seeded, engine = management
    user_id = seeded["designer"]["id"]
    with engine.begin() as connection:
        connection.execute(
            users.update().where(users.c.id == user_id).values(operations_remaining=1)
        )
    login(client, "designer")
    filename = "session_editor_scene.wild"
    headers = {"X-Operation-Id": "drag_once", "X-Operation-Label": "%E7%A7%BB%E5%8A%A8"}
    assert (
        client.put("/api/scenes/" + filename, json=scene(), headers=headers).status_code
        == 200
    )
    assert (
        client.put("/api/scenes/" + filename, json=scene(), headers=headers).status_code
        == 200
    )
    assert accounts.get(user_id)["operations_remaining"] == 0
    assert accounts.get(user_id)["operations_used"] == 1
    assert (
        client.put(
            "/api/scenes/" + filename,
            json=scene(1, 2),
            headers={"X-Operation-Id": "different"},
        ).status_code
        == 429
    )
    assert blueprint_repository.get(filename)["blueprint_json"] == scene()
    with engine.connect() as connection:
        logs = (
            connection.execute(
                select(audit_logs).where(audit_logs.c.action == "blueprint.edit")
            )
            .mappings()
            .all()
        )
    assert len(logs) == 1 and logs[0]["details"]["label"] == "移动"
    assert logs[0]["details"]["entities"][0]["id"] == "sphere"
    assert (
        client.put(
            "/api/scenes/" + filename, json=scene(1), headers=headers
        ).status_code
        == 409
    )


def test_old_operation_replay_does_not_restore_old_content(management):
    client, seeded, _ = management
    login(client, "designer")
    filename = "session_replay_scene.wild"
    for operation, radius, revision in (("first", 0.5, 1), ("second", 1, 2)):
        assert (
            client.put(
                "/api/scenes/" + filename,
                json=scene(radius, revision),
                headers={"X-Operation-Id": operation},
            ).status_code
            == 200
        )
    assert (
        client.put(
            "/api/scenes/" + filename, json=scene(), headers={"X-Operation-Id": "first"}
        ).status_code
        == 200
    )
    assert blueprint_repository.get(filename)["blueprint_json"] == scene(1, 2)
    assert (
        client.put(
            "/api/scenes/" + filename,
            json=scene(2, 3),
            headers={"X-Base-Revision": "1"},
        ).status_code
        == 409
    )
    assert accounts.get(seeded["designer"]["id"])["operations_used"] == 2


def test_only_admin_can_delete_and_lock_blocks_every_identity(management):
    client, seeded, _ = management
    filename = save_owned(seeded)
    login(client, "designer")
    assert client.delete("/api/scenes/" + filename).status_code == 403
    assert client.delete("/api/sessions/session_manage").status_code == 403
    assert (
        client.patch(
            "/api/admin/blueprints/" + filename, json={"locked": True}
        ).status_code
        == 403
    )
    login(client)
    assert (
        client.patch(
            "/api/admin/blueprints/" + filename, json={"locked": True}
        ).status_code
        == 200
    )
    for account in ("designer", "admin"):
        login(client, account)
        assert client.get("/api/scenes/" + filename).status_code == 200
        assert client.put("/api/scenes/" + filename, json=scene(2)).status_code == 423
        assert client.delete("/api/sessions/session_manage").status_code == 423
        assert (
            client.put(
                "/api/scenes/session_manage_another.wild", json=scene(2)
            ).status_code
            == 423
        )
    assert client.delete("/api/scenes/" + filename).status_code == 423
    with pytest.raises(BlueprintLocked):
        blueprint_repository.save("session_manage_background.wild", scene())
    with pytest.raises(BlueprintLocked):
        conversations.write("session_manage", {"name": "绕过锁"})
    assert (
        client.patch(
            "/api/admin/blueprints/" + filename, json={"locked": False}
        ).status_code
        == 200
    )
    assert client.delete("/api/scenes/" + filename).status_code == 200


def test_ai_quota_is_separate_and_recovery_does_not_charge_again(management):
    _, seeded, engine = management
    user_id = seeded["designer"]["id"]
    with engine.begin() as connection:
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(
                operations_remaining=0,
                modifications_remaining=1,
                generations_remaining=1,
            )
        )
    conversations.ensure("session_ai", user_id)
    for _ in range(2):
        charge_ai_request(user_id, "request_generate", "session_ai", "generate")
    charge_ai_request(user_id, "request_edit", "session_ai", "edit")
    charge_ai_request(user_id, "request_chat", "session_ai", "chat")
    account = accounts.get(user_id)
    assert account["generations_used"] == account["modifications_used"] == 1
    assert account["operations_used"] == 0
    with pytest.raises(QuotaExceeded):
        charge_ai_request(user_id, "second_generate", "session_ai", "generate")
    with pytest.raises(OperationConflict):
        charge_ai_request(user_id, "request_generate", "session_ai", "edit")


def test_classifier_uses_verified_intent_for_quota(management, monkeypatch):
    from app.agent.workflows.intent import workflow
    from langgraph.graph import END, StateGraph

    _, seeded, engine = management
    account = seeded["designer"]
    conversations.ensure("session_classify", account["id"])

    async def decision(*args, **kwargs):
        return SimpleNamespace(
            intent="generate",
            target="architecture",
            target_kind="architecture",
            profile="villa",
            requires_scene=False,
            reason="fixture",
            source="fixture",
        )

    monkeypatch.setattr(workflow, "classify_intent_decision", decision)
    state = {
        "request_id": "classifier_test",
        "session_id": "session_classify",
        "user_message": "生成建筑",
    }
    graph = StateGraph(dict)
    graph.add_node("classifier", workflow.classifier_node)
    graph.set_entry_point("classifier")
    graph.add_edge("classifier", END)
    compiled = graph.compile()
    result = asyncio.run(
        compiled.ainvoke(state, config={"configurable": {"account_id": account["id"]}})
    )
    assert result["intent"] == "generate"
    assert accounts.get(account["id"])["generations_remaining"] == 19
    with engine.begin() as connection:
        connection.execute(
            users.update()
            .where(users.c.id == account["id"])
            .values(generations_remaining=0)
        )
    with pytest.raises(QuotaExceeded):
        asyncio.run(
            compiled.ainvoke(
                {**state, "request_id": "classifier_blocked"},
                config={"configurable": {"account_id": account["id"]}},
            )
        )


def test_applying_paid_ai_edit_does_not_consume_manual_quota(management):
    client, seeded, engine = management
    filename = save_owned(seeded, "session_aiapply_scene.wild")
    actor_id = seeded["designer"]["id"]
    with engine.begin() as connection:
        connection.execute(
            users.update().where(users.c.id == actor_id).values(operations_remaining=0)
        )
    request_id = "req_aiapply"
    charge_ai_request(actor_id, request_id, "session_aiapply", "edit")
    repository = JobRepository()
    repository.insert(
        request_id,
        "session_aiapply",
        {
            "_server_user_id": actor_id,
            "blueprint": scene(),
            "session_id": "session_aiapply",
        },
    )
    patch = {
        "patch_id": "patch_" + request_id,
        "operations": [
            {"op": "update_element", "id": "sphere", "changes": {"radius": 1}}
        ],
    }
    repository.append(
        request_id, {"type": "patch_proposal", "patch": patch}, "completed"
    )
    login(client, "designer")
    headers = {"X-Operation-Id": patch["patch_id"], "X-Base-Revision": "1"}
    assert (
        client.put(
            "/api/scenes/" + filename, json=scene(2, 2), headers=headers
        ).status_code
        == 409
    )
    assert blueprint_repository.get(filename)["blueprint_json"] == scene()
    assert (
        client.put(
            "/api/scenes/" + filename, json=scene(1, 2), headers=headers
        ).status_code
        == 200
    )
    assert accounts.get(actor_id)["operations_used"] == 0
    assert accounts.get(actor_id)["modifications_used"] == 1


def test_admin_is_unlimited_and_ai_reply_is_in_user_audit(management):
    client, seeded, engine = management
    user_id = seeded["admin"]["id"]
    with engine.begin() as connection:
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(
                operations_remaining=0,
                modifications_remaining=0,
                generations_remaining=0,
            )
        )
    login(client)
    assert (
        client.put("/api/scenes/session_unlimited_scene.wild", json=scene()).status_code
        == 200
    )
    charge_ai_request(user_id, "unlimited_ai", "session_unlimited", "generate")
    charge_ai_request(user_id, "unlimited_edit", "session_unlimited", "edit")
    repository = JobRepository()
    repository.insert(
        "audit_reply",
        "session_unlimited",
        {"_server_user_id": user_id, "session_id": "session_unlimited"},
    )
    repository.append(
        "audit_reply", {"type": "agent_reply", "content": "离线回复"}, "completed"
    )
    result = client.get(
        "/api/admin/logs", params={"user_id": user_id, "action": "ai.agent_reply"}
    ).json()
    assert result["items"][0]["details"]["content"] == "离线回复"
    assert (
        client.get("/api/auth/session").json()["usage"]["operations"]["remaining"]
        is None
    )


def test_quota_atomic_update_never_overdraws(management):
    _, seeded, engine = management
    actor = seeded["designer"]
    with engine.begin() as connection:
        connection.execute(
            users.update()
            .where(users.c.id == actor["id"])
            .values(operations_remaining=1)
        )

    def consume(_):
        try:
            with engine.begin() as connection:
                charge_usage(connection, actor, "operations")
            return True
        except QuotaExceeded:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(consume, range(2))) == [False, True]
    assert accounts.get(actor["id"])["operations_remaining"] == 0


@pytest.mark.parametrize("delete_account", [False, True])
def test_disabling_account_stops_its_existing_ai_jobs(
    management, monkeypatch, tmp_path, delete_account
):
    from app.application.generation import jobs as job_module

    client, seeded, _ = management
    service = job_module.GenerationJobService(tmp_path / "admin-stop.sqlite3")
    service.repository = JobRepository()
    service._initialized = True
    monkeypatch.setattr(job_module, "generation_job_service", service)
    service.repository.insert(
        "req_disabled",
        "session_disabled",
        {"_server_user_id": seeded["designer"]["id"], "session_id": "session_disabled"},
    )
    service.repository.insert(
        "req_unrelated",
        "session_other",
        {"_server_user_id": seeded["other"]["id"], "session_id": "session_other"},
    )
    login(client)
    path = "/api/admin/users/" + seeded["designer"]["id"]
    response = (
        client.delete(path)
        if delete_account
        else client.patch(path, json={"status": "blocked"})
    )
    assert response.status_code == 200
    assert service.repository.get("req_disabled").status == "stopped"
    assert service.repository.get("req_unrelated").status == "running"
    events = service.repository.events_after("req_disabled", 0)
    assert events[-1]["stop_reason"] == "account_disabled"
    assert service.repository.active_for_account(seeded["designer"]["id"]) == []


def test_scene_load_reads_body_once_and_revalidates_changed_content(management):
    client, seeded, storage = management
    filename = save_owned(seeded)
    login(client, "designer")
    body_queries = []

    def record_query(_connection, _cursor, statement, _parameters, _context, _many):
        if "blueprints.blueprint_json" in statement.lower():
            body_queries.append(statement)

    event.listen(storage, "before_cursor_execute", record_query)
    try:
        response = client.get("/api/scenes/" + filename)
    finally:
        event.remove(storage, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert len(body_queries) == 1
    etag = response.headers["etag"]
    cached = client.get("/api/scenes/" + filename, headers={"If-None-Match": etag})
    assert cached.status_code == 304 and cached.content == b""
    assert cached.headers["etag"] == etag
    assert "private" in cached.headers["cache-control"]
    weak_match = client.get(
        "/api/scenes/" + filename,
        headers={"If-None-Match": '"unrelated", W/' + etag},
    )
    assert weak_match.status_code == 304
    timestamp = blueprint_repository.get_metadata(filename)["updated_at"]
    blueprint_repository.save(
        filename, scene(radius=0.8), owner_id=seeded["designer"]["id"], timestamp=timestamp
    )
    changed = client.get("/api/scenes/" + filename, headers={"If-None-Match": etag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != etag
    assert changed.json()["geometry"]["elements"][0]["radius"] == 0.8


def test_scene_cache_never_bypasses_ownership_or_disabled_account(management):
    client, seeded, _ = management
    filename = save_owned(seeded)
    login(client, "designer")
    token = client.cookies.get("wild_session")
    etag = client.get("/api/scenes/" + filename).headers["etag"]
    login(client, "other")
    response = client.get("/api/scenes/" + filename, headers={"If-None-Match": etag})
    assert response.status_code == 404 and "etag" not in response.headers
    login(client)
    assert client.patch(
        "/api/admin/users/" + seeded["designer"]["id"], json={"status": "blocked"}
    ).status_code == 200
    client.cookies.set("wild_session", token)
    response = client.get("/api/scenes/" + filename, headers={"If-None-Match": etag})
    assert response.status_code == 404 and "etag" not in response.headers


def test_blueprint_pagination_never_reads_large_json(management):
    client, seeded, storage = management
    filenames = [f"session_large_{letter}.wild" for letter in ("a", "b", "c")]
    blueprint = scene()
    blueprint["meta"]["description"] = "large blueprint " * 2000
    for filename in filenames:
        blueprint_repository.save(
            filename, blueprint, owner_id=seeded["designer"]["id"]
        )
    with storage.begin() as connection:
        connection.execute(blueprint_table.update().values(updated_at=1))
        connection.execute(
            blueprint_table.update()
            .where(blueprint_table.c.filename.in_([filenames[0], filenames[2]]))
            .values(updated_at=2)
        )
    login(client)
    statements = []

    def record_query(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.lower())

    event.listen(storage, "before_cursor_execute", record_query)
    try:
        pages = []
        for page in (1, 2, 3):
            response = client.get(
                "/api/admin/blueprints",
                params={
                    "query": "designer",
                    "locked": False,
                    "page": page,
                    "page_size": 2,
                },
            )
            assert response.status_code == 200
            pages.append(response.json())
    finally:
        event.remove(storage, "before_cursor_execute", record_query)

    assert [item["filename"] for item in pages[0]["items"]] == [
        filenames[0],
        filenames[2],
    ]
    assert [item["filename"] for item in pages[1]["items"]] == [filenames[1]]
    assert pages[2]["items"] == []
    for page in pages:
        assert page["total"] == 3
        for item in page["items"]:
            assert item["owner_name"] == "designer"
            assert "blueprint_json" not in item
            assert "size_bytes" not in item
            assert "footprint_area" not in item
    blueprint_queries = [
        statement for statement in statements if "from blueprints" in statement
    ]
    assert len(blueprint_queries) == 6
    for statement in blueprint_queries:
        assert "blueprint_json" not in statement


@pytest.mark.parametrize(
    "filename", ["session_manage_scene.wild", "2026-11-16/session_manage_scene.wild"]
)
def test_blueprint_details_and_export_read_one_file(management, filename):
    client, seeded, storage = management
    save_owned(seeded, filename)
    login(client)
    queries = []

    def record_query(_connection, _cursor, statement, parameters, _context, _many):
        if "blueprint_json" in statement.lower():
            queries.append((statement, parameters))

    event.listen(storage, "before_cursor_execute", record_query)
    try:
        response = client.get(f"/api/admin/blueprints/{filename}/metrics")
    finally:
        event.remove(storage, "before_cursor_execute", record_query)
    assert response.status_code == 200
    assert response.json()["footprint_area"] is None
    assert len(queries) == 1
    assert "where blueprints.filename =" in queries[0][0].lower()
    parameters = queries[0][1]
    bound_values = parameters.values() if isinstance(parameters, dict) else parameters
    assert filename in bound_values
    exported = client.get("/api/scenes/" + filename)
    assert exported.status_code == 200
    assert exported.json()["geometry"] == scene()["geometry"]
    assert client.get("/api/admin/blueprints/missing.wild/metrics").status_code == 404
    assert client.get("/api/admin/blueprints/invalid.txt/metrics").status_code == 400


def test_stats_blueprint_metrics_pagination_and_secret_redaction(management):
    client, seeded, _ = management
    blueprint = scene()
    blueprint["geometry"]["elements"] = [
        {"id": "floor_a", "type": "floor", "from": [0, 0, 0], "to": [4, 0.2, 4]},
        {"id": "floor_b", "type": "floor", "from": [2, 0, 0], "to": [6, 0.2, 4]},
        {"id": "upper", "type": "floor", "from": [0, 3, 0], "to": [20, 3.2, 20]},
    ]
    metrics = blueprint_metrics(blueprint)
    assert metrics["footprint_area"] == 24
    assert metrics["footprint_width"] == 6 and metrics["footprint_depth"] == 4
    blueprint_repository.save(
        "session_metrics_scene.wild", blueprint, owner_id=seeded["designer"]["id"]
    )
    login(client)
    assert (
        client.get(
            "/api/admin/users", params={"query": "designer", "page_size": 1}
        ).json()["total"]
        == 1
    )
    row = client.get("/api/admin/blueprints").json()["items"][0]
    assert "footprint_area" not in row and "blueprint_json" not in row
    details = client.get(f"/api/admin/blueprints/{row['filename']}/metrics")
    assert details.status_code == 200
    assert details.json()["footprint_area"] == 24
    assert (
        client.post("/api/config/llm", json={"api_key": "DO-NOT-LOG-THIS"}).status_code
        == 200
    )
    assert "DO-NOT-LOG-THIS" not in json.dumps(client.get("/api/admin/logs").json())
    assert (
        client.patch(
            "/api/admin/users/" + seeded["designer"]["id"],
            json={"generations_remaining": -1},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/admin/users/" + seeded["designer"]["id"],
            json={"password_hash": "bad"},
        ).status_code
        == 422
    )
