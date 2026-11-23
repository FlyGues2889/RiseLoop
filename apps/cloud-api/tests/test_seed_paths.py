from app.db import seed


def test_candidate_paths_survive_flat_container_layout(monkeypatch):
    monkeypatch.setattr(seed, "__file__", "/app/app/db/seed.py")
    paths = [path.as_posix() for path in seed._candidate_paths()]
    assert any(path.endswith("/app/data/actions/actions.json") for path in paths)
    assert any(path.endswith("/data/actions/actions.json") for path in paths)
