"""Tests for the read-only endpoints: meta, cases, and legal rules"""


class TestMeta:
    def test_root_says_what_this_is(self, client):
        body = client.get("/").json()
        assert body["docs"] == "/docs"
        assert "does not provide legal advice" in body["disclaimer"]

    def test_health(self, client):
        body = client.get("/health").json()
        assert body["status"] == "ok"
        assert (body["cases"], body["rules"], body["active_runs"]) == (1, 17, 0)

    def test_docs_and_openapi(self, client):
        assert client.get("/docs").status_code == 200
        paths = client.get("/openapi.json").json()["paths"]
        assert {
            "/api/cases",
            "/api/cases/{case_id}",
            "/api/cases/{case_id}/simulate",
            "/api/rules",
            "/api/runs",
            "/api/runs/{run_id}",
            "/api/runs/{run_id}/events",
            "/api/runs/{run_id}/stream",
            "/api/runs/{run_id}/audit",
        } <= set(paths)

    def test_cors_allows_the_frontend(self, client):
        response = client.get("/api/cases", headers={"Origin": "http://localhost:3000"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


class TestCases:
    def test_list(self, client):
        [case] = client.get("/api/cases").json()
        assert case["case_id"] == "CASE_001"
        assert case["charges"] == ["burglary", "assault"]
        assert (case["facts"], case["evidence"], case["witnesses"]) == (8, 8, 3)
        assert case["runnable"] is True

    def test_detail(self, client):
        body = client.get("/api/cases/CASE_001").json()
        assert body["case"]["defendant"] == "Alex Johnson"
        assert body["bindings"] == 18 and body["runnable"] is True
        statuses = {
            (r["rule_id"], r["subject"]): r["status"]
            for r in body["rule_evaluation"]["rule_evaluations"]
        }
        assert statuses[("LAW_104", "Alex Johnson")] == "indeterminate"
        assert len(body["evidence_provenance"]) == 8
        assert body["evidence_provenance"][0]["handled_by"] == "Officer Martinez"

    def test_unknown_case(self, client):
        response = client.get("/api/cases/CASE_404")
        assert response.status_code == 404
        assert response.json()["detail"] == "Unknown case 'CASE_404'"


class TestRules:
    def test_list(self, client):
        rules = client.get("/api/rules").json()
        assert len(rules) == 17
        assert {r["category"] for r in rules} == {
            "offense",
            "defense",
            "principle",
            "evidence_rule",
        }

    def test_detail(self, client):
        rule = client.get("/api/rules/LAW_104").json()
        assert rule["name"] == "Burglary"
        assert [c["id"] for c in rule["conditions"]] == ["C1", "C2"]
        assert rule["jurisdiction"] == "Republic of Arandia"

    def test_unknown_rule(self, client):
        assert client.get("/api/rules/LAW_999").status_code == 404
