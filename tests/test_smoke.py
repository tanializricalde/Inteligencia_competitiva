def test_public_health(client):
    response = client.get("/public/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
