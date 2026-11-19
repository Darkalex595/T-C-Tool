from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx


def assert_status(resp: httpx.Response, expected: int, step: str) -> None:
    if resp.status_code != expected:
        print(f"[FAIL] {step}: esperaba HTTP {expected}, obtuvo {resp.status_code}")
        print(f"       Body: {resp.text}")
        sys.exit(1)
    print(f"[ OK ] {step} (HTTP {resp.status_code})")


def login(client: httpx.Client, email: str, password: str, label: str) -> dict[str, Any]:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert_status(resp, 200, f"Login {label} ({email})")
    return resp.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def run_flow(
    base_url: str,
    admin_email: str,
    analyst_email: str,
    buyer_email: str,
    password: str,
) -> None:
    print(f"\n=== Validación E2E contra {base_url} ===\n")

    with httpx.Client(base_url=base_url, timeout=15.0) as client:
        # 1. Healthcheck y conexión PostgreSQL
        health = client.get("/health")
        assert_status(health, 200, "1. Healthcheck /health")
        health_data = health.json()
        assert health_data["status"] == "ok", f"Health inesperado: {health_data}"
        print(f"       BD: {health_data['database_name']} | Tablas: {health_data['public_tables']}")

        # 2. Login Buyer
        buyer_auth = login(client, buyer_email, password, "buyer")
        buyer_headers = auth_headers(buyer_auth["access_token"])

        # 3. Consultar taxonomía jerárquica (Department > Category > Subcategory) y rutas
        tax_resp = client.get("/api/v1/catalogs/taxonomy", headers=buyer_headers)
        assert_status(tax_resp, 200, "2. GET /catalogs/taxonomy")
        taxonomy = tax_resp.json()
        assert taxonomy and taxonomy[0]["categories"], "La taxonomía no tiene categorías."
        first_category = taxonomy[0]["categories"][0]
        assert "classification" in first_category, "Category debe incluir 'classification'."
        subcategory_id = first_category["subcategories"][0]["id"]
        print(
            f"       Jerarquía verificada: {taxonomy[0]['name']} > "
            f"{first_category['name']} ({first_category['classification']}) > "
            f"{first_category['subcategories'][0]['name']}"
        )

        routes_resp = client.get("/api/v1/routes", headers=buyer_headers)
        assert_status(routes_resp, 200, "3. GET /routes")
        routes = routes_resp.json()
        assert len(routes) >= 10, f"Se esperaban al menos 10 rutas, se hallaron {len(routes)}"
        route_id = routes[0]["id"]

        # 4. Validar rechazo Pydantic (422) cuando branch_type no coincide con el detalle 1:1
        bad_req = client.post(
            "/api/v1/requests",
            headers=buyer_headers,
            json={
                "request_type": "new_item",
                "branch_type": "food",
                "subcategory_id": subcategory_id,
                "item_description": "Invalid Mismatched Detail Test",
                "vendor_name": "QA Vendor",
                "vendor_country_code": "US",
                "origin_country_code": "US",
                "destination_country_codes": ["CR"],
                "no_food_detail": {"material_composition": "Plastic"},
            },
        )
        assert_status(bad_req, 422, "4. Validación 1:1 Pydantic (branch_type vs detalle)")

        # 5. Crear solicitud válida (atómica: ReqGeneral + ReqFood + destinos M2M)
        create_resp = client.post(
            "/api/v1/requests",
            headers=buyer_headers,
            json={
                "request_type": "new_item",
                "branch_type": "food",
                "is_urgent": False,
                "subcategory_id": subcategory_id,
                "import_route_id": route_id,
                "item_code": "E2E-FOOD-01",
                "item_description": "SelectHarvest Roasted Almonds E2E Validation Pack",
                "brand_name": "SelectHarvest",
                "vendor_name": "Pacific Coast Confectionery LLC",
                "vendor_country_code": "US",
                "origin_country_code": "US",
                "hs_code_proposed": "2008.19.00",
                "destination_country_codes": ["CR", "CO"],
                "food_detail": {
                    "ingredients_summary": "Roasted almonds, sea salt.",
                    "allergens": ["Tree Nuts (Almonds)"],
                    "storage_condition": "Ambient Dry",
                    "shelf_life_days": 365,
                    "requires_cold_chain": False,
                },
            },
        )
        assert_status(create_resp, 201, "5. POST /requests (creación atómica 1:1)")
        created_req = create_resp.json()
        req_id = created_req["id"]
        assert created_req["status"] == "pending"
        assert created_req["food_detail"] is not None
        assert created_req["category"] is not None and created_req["department"] is not None
        print(f"       Ticket creado: #{created_req['ticket_number']} ({req_id})")

        # 6. Verificar bloqueo RBAC del buyer (403 en certificaciones, dictámenes y cambio de estado)
        for label, method, path, body in [
            (
                "6a. RBAC Buyer bloqueado en POST /certifications",
                "POST",
                f"/api/v1/requests/{req_id}/certifications",
                {"certificate_name": "Should Fail", "country_code": "CR"},
            ),
            (
                "6b. RBAC Buyer bloqueado en PUT /assessments",
                "PUT",
                f"/api/v1/requests/{req_id}/assessments",
                {"country_code": "CR", "decision": "approved"},
            ),
            (
                "6c. RBAC Buyer bloqueado en PATCH /status",
                "PATCH",
                f"/api/v1/requests/{req_id}/status",
                {"status": "completed"},
            ),
        ]:
            blocked = client.request(method, path, headers=buyer_headers, json=body)
            assert_status(blocked, 403, label)

        # 7. Login Compliance Analyst
        analyst_auth = login(client, analyst_email, password, "compliance_analyst")
        analyst_headers = auth_headers(analyst_auth["access_token"])

        # 8. Agregar, actualizar y consultar certificación ligada al ítem
        cert_resp = client.post(
            f"/api/v1/requests/{req_id}/certifications",
            headers=analyst_headers,
            json={
                "country_code": "CR",
                "origin_scope": "us_origin",
                "certificate_name": "Certificate of Free Sale (E2E)",
                "issuing_body": "FDA",
                "is_mandatory": True,
                "requires_apostille": False,
                "validity_days": 365,
            },
        )
        assert_status(cert_resp, 201, "7. POST /requests/{id}/certifications")
        cert_id = cert_resp.json()["id"]

        cert_patch = client.patch(
            f"/api/v1/certifications/{cert_id}",
            headers=analyst_headers,
            json={"requires_apostille": True},
        )
        assert_status(cert_patch, 200, "8. PATCH /certifications/{id}")
        assert cert_patch.json()["requires_apostille"] is True

        # 9. Dictamen técnico por país (primero país inválido -> 400, luego CR -> 200)
        bad_assess = client.put(
            f"/api/v1/requests/{req_id}/assessments",
            headers=analyst_headers,
            json={"country_code": "TT", "decision": "approved"},
        )
        assert_status(bad_assess, 400, "9a. PUT /assessments rechaza país fuera de destinos")

        assess_resp = client.put(
            f"/api/v1/requests/{req_id}/assessments",
            headers=analyst_headers,
            json={
                "country_code": "CR",
                "decision": "approved_with_conditions",
                "hs_tariff_confirmed": "2008.19.90.00",
                "import_duty_rate": "0.00",
                "estimated_lead_time_days": 12,
                "requires_import_permit": True,
                "requires_sanitary_registration": True,
                "required_certificates": ["Certificate of Free Sale (E2E)"],
                "category_checklist": {"spanish_label": True, "allergens_bold": True},
                "technical_notes": "Validado en prueba E2E.",
            },
        )
        assert_status(assess_resp, 200, "9b. PUT /assessments para CR")
        assert assess_resp.json()["assessed_at"] is not None

        # Confirmar transición automática pending -> in_progress
        detail_mid = client.get(f"/api/v1/requests/{req_id}", headers=analyst_headers)
        assert_status(detail_mid, 200, "10. GET /requests/{id} verifica auto-transición")
        mid_data = detail_mid.json()
        assert mid_data["status"] == "in_progress", f"Esperaba in_progress, obtuvo {mid_data['status']}"
        assert len(mid_data["certifications"]) == 1
        assert len(mid_data["assessments"]) == 1

        # 10. Analista aprueba/cierra la solicitud (permiso requests:approve)
        close_resp = client.patch(
            f"/api/v1/requests/{req_id}/status",
            headers=analyst_headers,
            json={"status": "completed", "comments": "Aprobado por Compliance Analyst (E2E)."},
        )
        assert_status(close_resp, 200, "11. PATCH /requests/{id}/status -> completed")
        assert close_resp.json()["closed_at"] is not None

        # 11. Analista NO puede crear departamentos (solo users:admin)
        analyst_admin_block = client.post(
            "/api/v1/catalogs/departments",
            headers=analyst_headers,
            json={"code": "D-TMP", "name": "Temp Unauthorized"},
        )
        assert_status(analyst_admin_block, 403, "12. RBAC Analyst bloqueado en POST /departments")

        # 12. Login Admin + consulta de regulaciones paginadas
        admin_auth = login(client, admin_email, password, "admin")
        admin_headers = auth_headers(admin_auth["access_token"])
        assert "users:admin" in admin_auth["user"]["permissions"]

        regs_resp = client.get("/api/v1/regulations?limit=10&offset=0", headers=admin_headers)
        assert_status(regs_resp, 200, "13. GET /regulations (paginado)")
        print(f"       Regulaciones totales en BD: {regs_resp.json()['total']}")

        # 13. Eliminar certificación de prueba para validar DELETE 204
        del_cert = client.delete(f"/api/v1/certifications/{cert_id}", headers=analyst_headers)
        assert_status(del_cert, 204, "14. DELETE /certifications/{id}")

    print("\n=== TODAS LAS VALIDACIONES E2E PASARON CORRECTAMENTE ===\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prueba E2E de la API FastAPI.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--admin-email", default="nmartinez@globaltrade-corp.com")
    parser.add_argument("--analyst-email", default="cnavarro@globaltrade-corp.com")
    parser.add_argument("--buyer-email", default="esolis@globaltrade-corp.com")
    parser.add_argument("--password", default="TradeDemo2026!")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_flow(
        base_url=args.base_url,
        admin_email=args.admin_email,
        analyst_email=args.analyst_email,
        buyer_email=args.buyer_email,
        password=args.password,
    )
