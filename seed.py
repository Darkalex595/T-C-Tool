from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from backend.database import AsyncSessionLocal, Base, async_engine
from backend.models import (
    AssessmentDecision,
    Category,
    CertificationRequirement,
    Country,
    Department,
    FiscalYear,
    ImportAssessment,
    ImportRoute,
    LogisticsRouteCode,
    OriginScope,
    Permission,
    ProductClassification,
    Regulation,
    RegulationStatus,
    ReqFood,
    ReqGeneral,
    ReqNoFood,
    ReqPlantApproval,
    ReqProduce,
    RequestBranchType,
    RequestStatus,
    RequestType,
    Role,
    Subcategory,
    User,
    UserAuditLog,
)
from backend.security import hash_password


async def seed_database() -> None:
    """Inicializa el esquema en PostgreSQL y puebla datos de forma idempotente."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        existing_country = await session.scalar(select(Country.code).limit(1))
        if existing_country is not None:
            print("La base de datos ya contiene datos iniciales; seed omitido.")
            return

        now = datetime.now(timezone.utc)

        # 1. Países (ISO 3166-1 alpha-2)
        countries = [
            Country(
                code="CR",
                name="Costa Rica",
                region="Central America",
                currency_code="CRC",
                regulatory_agency="Ministerio de Salud / SENASA / SFE",
            ),
            Country(
                code="PA",
                name="Panama",
                region="Central America",
                currency_code="USD",
                regulatory_agency="APA / MINSA / MIDA",
            ),
            Country(
                code="CO",
                name="Colombia",
                region="South America",
                currency_code="COP",
                regulatory_agency="INVIMA / ICA / DIAN",
            ),
            Country(
                code="DO",
                name="Dominican Republic",
                region="Caribbean",
                currency_code="DOP",
                regulatory_agency="DIGEMAPS / DGA / Agricultura",
            ),
            Country(
                code="SV",
                name="El Salvador",
                region="Central America",
                currency_code="SVC",
                regulatory_agency="DIGESA / MAG / Hacienda",
            ),
            Country(
                code="GT",
                name="Guatemala",
                region="Central America",
                currency_code="GTQ",
                regulatory_agency="MSPAS / MAGA / SAT",
            ),
            Country(
                code="TT",
                name="Trinidad & Tobago",
                region="Caribbean",
                currency_code="TTD",
                regulatory_agency="Chemistry, Food & Drugs Division / Customs",
            ),
            Country(
                code="US",
                name="United States",
                region="North America",
                currency_code="USD",
                regulatory_agency="FDA / USDA-FSIS / CBP",
            ),
        ]
        session.add_all(countries)

        # 2. Años Fiscales
        fy26 = FiscalYear(
            code="FY2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 8, 31),
            is_current=True,
        )
        fy25 = FiscalYear(
            code="FY2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 8, 31),
            is_current=False,
        )
        session.add_all([fy25, fy26])

        # 3. Taxonomía Comercial (Departments -> Categories -> Subcategories)
        dept_food = Department(
            code="D-FOOD",
            name="Food & Sundries",
        )
        dept_non_food = Department(
            code="D-HARD",
            name="Hardlines & Appliances",
        )
        dept_produce = Department(
            code="D-PROD",
            name="Fresh Produce & Cold Chain",
        )
        session.add_all([dept_food, dept_non_food, dept_produce])
        await session.flush()

        cat_snacks = Category(
            department_id=dept_food.id,
            code="C-SNK",
            name="Snacks & Confectionery",
            classification=ProductClassification.FOOD,
        )
        cat_dairy = Category(
            department_id=dept_food.id,
            code="C-DRY",
            name="Dairy & Refrigerated",
            classification=ProductClassification.FOOD,
        )
        cat_electronics = Category(
            department_id=dept_non_food.id,
            code="C-ELC",
            name="Consumer Electronics & Batteries",
            classification=ProductClassification.NON_FOOD,
        )
        cat_fruits = Category(
            department_id=dept_produce.id,
            code="C-FRT",
            name="Imported Temperate Fruits",
            classification=ProductClassification.PRODUCE,
        )
        session.add_all([cat_snacks, cat_dairy, cat_electronics, cat_fruits])
        await session.flush()

        sub_chocolate = Subcategory(
            category_id=cat_snacks.id,
            code="SC-CHOC",
            name="Chocolate & Cocoa Bars",
            hs_chapter_hint="1806.32",
            requires_sanitary_reg=True,
        )
        sub_cheese = Subcategory(
            category_id=cat_dairy.id,
            code="SC-CHSE",
            name="Aged Artisanal Cheeses",
            hs_chapter_hint="0406.90",
            requires_sanitary_reg=True,
        )
        sub_lithium = Subcategory(
            category_id=cat_electronics.id,
            code="SC-PWR",
            name="Portable Power Stations (LiFePO4)",
            hs_chapter_hint="8507.60",
            requires_sanitary_reg=False,
        )
        sub_apples = Subcategory(
            category_id=cat_fruits.id,
            code="SC-APPL",
            name="Fresh Apples & Pears",
            hs_chapter_hint="0808.10",
            requires_sanitary_reg=False,
        )
        session.add_all([sub_chocolate, sub_cheese, sub_lithium, sub_apples])
        await session.flush()

        # 4. Permisos, Roles y Usuarios RBAC
        perms = [
            Permission(
                module="requests",
                action="create",
                code="requests:create",
                description="Crear nuevas solicitudes de evaluación de importación",
            ),
            Permission(
                module="requests",
                action="assess",
                code="requests:assess",
                description="Emitir dictámenes técnicos por país destino",
            ),
            Permission(
                module="requests",
                action="approve",
                code="requests:approve",
                description="Cambiar estado global de solicitudes y aprobar excepciones",
            ),
            Permission(
                module="regulations",
                action="manage",
                code="regulations:manage",
                description="Crear y publicar regulaciones en la matriz multinacional",
            ),
            Permission(
                module="routes",
                action="manage",
                code="routes:manage",
                description="Configurar rutas logísticas y centros de distribución",
            ),
            Permission(
                module="users",
                action="admin",
                code="users:admin",
                description="Administrar usuarios, roles y logs de auditoría",
            ),
        ]
        session.add_all(perms)
        await session.flush()

        role_admin = Role(
            name="admin",
            description="Administrador global de cumplimiento comercial y arquitectura",
            is_system=True,
            permissions=perms,
        )
        role_analyst = Role(
            name="compliance_analyst",
            description="Especialista regulatorio regional por país",
            is_system=True,
            permissions=[perms[0], perms[1], perms[3]],
        )
        role_buyer = Role(
            name="buyer",
            description="Comprador internacional y abastecimiento estratégico",
            is_system=True,
            permissions=[perms[0]],
        )
        session.add_all([role_admin, role_analyst, role_buyer])
        await session.flush()

        demo_password_hash = hash_password("TradeDemo2026!")

        admin_user = User(
            full_name="Nestor Martinez",
            email="nmartinez@globaltrade-corp.com",
            password_hash=demo_password_hash,
            role_id=role_admin.id,
            primary_country_code="SV",
            department_code="COMPLIANCE-HQ",
        )
        analyst_user = User(
            full_name="Carlos Navarro",
            email="cnavarro@globaltrade-corp.com",
            password_hash=demo_password_hash,
            role_id=role_analyst.id,
            primary_country_code="CO",
            department_code="REGULATORY-LATAM",
        )
        buyer_user = User(
            full_name="Elena Solís",
            email="esolis@globaltrade-corp.com",
            password_hash=demo_password_hash,
            role_id=role_buyer.id,
            primary_country_code="PA",
            department_code="GLOBAL-SOURCING",
        )
        session.add_all([admin_user, analyst_user, buyer_user])
        await session.flush()

        # 5. Catálogo Predefinido de Rutas Logísticas Genéricas (ImportRoute)
        route_central_hub = ImportRoute(
            route_code=LogisticsRouteCode.CENTRAL_HUB,
            route_name="Central Consolidation Hub - HUB-01",
            dc_code="HUB-01",
            country_code=None,
            classification=ProductClassification.ALL,
            required_document="Consolidated Commercial Invoice + Packing List + Master B/L",
            description="Consolidación en centro de distribución central para despacho multiregional.",
            us_origin_rules="Certificado de Libre Venta (CFS) FDA/Estatal y declaración de origen USMCA/CAFTA-DR.",
            non_us_origin_rules="Verificación de tránsito en zona franca y certificado de origen no preferencial.",
            is_direct_to_destination=False,
        )
        route_supplier_hub = ImportRoute(
            route_code=LogisticsRouteCode.SUPPLIER_TO_HUB,
            route_name="Supplier to Regional Terminal - TERM-10",
            dc_code="TERM-10",
            country_code=None,
            classification=ProductClassification.ALL,
            required_document="Direct Bill of Lading + Country-Specific Sanitary Permit",
            description="Despacho coordinado por proveedor hacia terminal regional TERM-10 con destino asignado por país.",
            us_origin_rules="Validación previa de registro sanitario antes de liberación de embarque.",
            non_us_origin_rules="Documentación apostillada en idioma español/inglés según país final.",
            is_direct_to_destination=False,
        )
        route_direct_intl = ImportRoute(
            route_code=LogisticsRouteCode.DIRECT_PORT_TO_PORT,
            route_name="Direct Origin-to-Port - DIRECT-INTL",
            dc_code="DIRECT-INTL",
            country_code=None,
            classification=ProductClassification.ALL,
            required_document="Original B/L + Origin Phytosanitary / Zoosanitary Certificate",
            description="Embarque directo desde puerto de origen del proveedor hasta puerto del país destino sin consolidación.",
            us_origin_rules="Inspección previa en origen y pre-aviso aduanero 72h antes del arribo.",
            non_us_origin_rules="Requiere validación estricta de sellos de contenedor y trazabilidad de planta.",
            is_direct_to_destination=True,
        )
        route_dry_hub = ImportRoute(
            route_code=LogisticsRouteCode.REGIONAL_DRY_HUB,
            route_name="Regional Dry Cargo Hub - HUB-20",
            dc_code="HUB-20",
            country_code=None,
            classification=ProductClassification.NON_FOOD,
            required_document="Commercial Invoice + Packing List + Safety Compliance Dossier",
            description="Hub logístico regional HUB-20 especializado en mercancía general y carga seca.",
            us_origin_rules="Declaración de conformidad FCC/UL y hojas de seguridad MSDS cuando aplique.",
            non_us_origin_rules="Certificado de origen y fichas técnicas de materiales en español.",
            is_direct_to_destination=False,
        )
        route_cold_hub = ImportRoute(
            route_code=LogisticsRouteCode.REGIONAL_COLD_HUB,
            route_name="Regional Cold-Chain Hub - HUB-30",
            dc_code="HUB-30",
            country_code=None,
            classification=ProductClassification.FOOD,
            required_document="Cold Chain Manifest + Reefer Temperature Log + Sanitary Clearance",
            description="Centro de distribución regional HUB-30 con capacidad multitemperatura para alimentos.",
            us_origin_rules="Consolidación de alimentos refrigerados y secos con pre-etiquetado regional.",
            non_us_origin_rules="Requiere re-inspección documental antes de despacho secundario a destino final.",
            is_direct_to_destination=False,
        )
        route_co_dc = ImportRoute(
            route_code=LogisticsRouteCode.CO_NATIONAL_DC,
            route_name="Colombia National Hub - CO-DC1",
            dc_code="CO-DC1",
            country_code="CO",
            classification=ProductClassification.ALL,
            required_document="Registro Sanitario INVIMA + Licencia VUCE + Declaración de Importación DIAN",
            description="Centro de distribución nacional Colombia (CO-DC1).",
            us_origin_rules="Aplica preferencia arancelaria TLC Colombia-EE.UU. con certificado de origen firmado.",
            non_us_origin_rules="Arancel NMF aplicable; etiquetado nutricional Resolución 810/2492 obligatorio.",
            is_direct_to_destination=True,
        )
        route_pa_dc = ImportRoute(
            route_code=LogisticsRouteCode.PA_NATIONAL_DC,
            route_name="Panama National Hub - PA-DC1",
            dc_code="PA-DC1",
            country_code="PA",
            classification=ProductClassification.ALL,
            required_document="Notificación Sanitaria APA + Factura Comercial Consular/Digital + B/L",
            description="Centro de distribución nacional Panamá (PA-DC1).",
            us_origin_rules="Plantas USDA/FDA elegibles mediante sistema simplificado APA.",
            non_us_origin_rules="Requiere pre-registro de establecimiento productor ante APA.",
            is_direct_to_destination=True,
        )
        route_cr_direct = ImportRoute(
            route_code=LogisticsRouteCode.CR_DIRECT_PORT,
            route_name="Costa Rica Direct Port - CR-DIR1",
            dc_code="CR-DIR1",
            country_code="CR",
            classification=ProductClassification.ALL,
            required_document="Registro Sanitario MS + Nota Técnica VUCE / PROCOMER + DUA",
            description="Ingreso directo a Costa Rica hacia puerto y centro receptor CR-DIR1.",
            us_origin_rules="Beneficio CAFTA-DR sujeto a certificado de origen válido y registro vigente.",
            non_us_origin_rules="Aplica RTCA de etiquetado nutricional y notas técnicas SENASA/SFE.",
            is_direct_to_destination=True,
        )
        route_do_dc = ImportRoute(
            route_code=LogisticsRouteCode.DO_NATIONAL_DC,
            route_name="Dominican Republic Hub - DO-DC1",
            dc_code="DO-DC1",
            country_code="DO",
            classification=ProductClassification.ALL,
            required_document="Registro DIGEMAPS + Permiso No Objeción Agricultura + VUCE RD",
            description="Centro de distribución República Dominicana (DO-DC1).",
            us_origin_rules="Aplica DR-CAFTA con verificación de origen y registro DIGEMAPS previo.",
            non_us_origin_rules="Requiere legalización/apostilla de Certificado de Libre Venta.",
            is_direct_to_destination=True,
        )
        route_tt_dc = ImportRoute(
            route_code=LogisticsRouteCode.TT_NATIONAL_DC,
            route_name="Trinidad & Tobago Hub - TT-DC1",
            dc_code="TT-DC1",
            country_code="TT",
            classification=ProductClassification.ALL,
            required_document="CFDD Import Permit + CARICOM / MFN Origin Certificate + Health Cert",
            description="Centro de distribución Trinidad y Tobago (TT-DC1).",
            us_origin_rules="Etiquetado obligatorio en inglés conforme a Trinidad & Tobago Bureau of Standards (TTBS).",
            non_us_origin_rules="Inspección sanitaria portuaria y permiso previo para productos de origen animal.",
            is_direct_to_destination=True,
        )
        session.add_all(
            [
                route_central_hub,
                route_supplier_hub,
                route_direct_intl,
                route_dry_hub,
                route_cold_hub,
                route_co_dc,
                route_pa_dc,
                route_cr_direct,
                route_do_dc,
                route_tt_dc,
            ]
        )
        await session.flush()

        # 6. Regulaciones Multinacionales
        reg_rtca = Regulation(
            country_code="CR",
            department_id=dept_food.id,
            regulation_code="RTCA-67.01.07:10",
            title="Etiquetado General y Nutricional de Alimentos Preenvasados",
            issuing_authority="COMIECO / Ministerio de Salud Costa Rica",
            status=RegulationStatus.ENFORCED,
            summary="Exige etiqueta complementaria en español con número de registro sanitario, lista de ingredientes, alérgenos destacados y tabla nutricional por 100g/porción.",
            effective_date=date(2023, 1, 15),
            subcategories=[sub_chocolate, sub_cheese],
            created_by_id=admin_user.id,
        )
        reg_invima = Regulation(
            country_code="CO",
            department_id=dept_food.id,
            regulation_code="RES-810-2021",
            title="Sellos Frontales de Advertencia Nutricional (Exceso en Azúcares / Grasas / Sodio)",
            issuing_authority="Ministerio de Salud y Protección Social / INVIMA",
            status=RegulationStatus.ENFORCED,
            summary="Obliga octágonos negros frontales de advertencia cuando el perfil nutricional excede umbrales establecidos para azúcares añadidos, grasas saturadas o sodio.",
            effective_date=date(2024, 6, 14),
            subcategories=[sub_chocolate, sub_cheese],
            created_by_id=analyst_user.id,
        )
        reg_tt_labels = Regulation(
            country_code="TT",
            department_id=dept_non_food.id,
            regulation_code="TTBS-TTS-76",
            title="Compulsory Labelling Standard for Electrical Appliances & Lithium Storage",
            issuing_authority="Trinidad & Tobago Bureau of Standards (TTBS)",
            status=RegulationStatus.TO_BE_ENFORCED,
            summary="Requiere marcado CE/UL verificable, instrucciones de seguridad en inglés, clasificación IP y ficha UN38.3 para baterías de litio.",
            effective_date=date(2026, 12, 1),
            subcategories=[sub_lithium],
            created_by_id=admin_user.id,
        )
        session.add_all([reg_rtca, reg_invima, reg_tt_labels])
        await session.flush()

        # 7. Solicitudes Core (1:1 Branching) + Certificaciones por Ítem + Dictámenes por País
        req_1 = ReqGeneral(
            request_type=RequestType.NEW_ITEM,
            branch_type=RequestBranchType.FOOD,
            status=RequestStatus.IN_PROGRESS,
            is_urgent=False,
            fiscal_year_id=fy26.id,
            subcategory_id=sub_chocolate.id,
            import_route_id=route_central_hub.id,
            item_code="SH-88412",
            item_description="SelectHarvest Organic Dark Chocolate Almonds 72% Cacao (907g)",
            brand_name="SelectHarvest",
            vendor_name="Pacific Coast Confectionery LLC",
            vendor_country_code="US",
            origin_country_code="US",
            hs_code_proposed="1806.32.00",
            comments="Lanzamiento regional Q3; verificar etiquetado frontal en Colombia y registro sanitario CR/PA.",
            created_by_id=buyer_user.id,
            assigned_to_id=analyst_user.id,
            sla_due_at=now + timedelta(days=5),
            destination_countries=[countries[0], countries[1], countries[2]],
        )
        req_1.food_detail = ReqFood(
            ingredients_summary="Organic dark chocolate (cacao liquor, cane sugar, cocoa butter), roasted almonds, sea salt.",
            allergens=["Tree Nuts (Almonds)", "May contain Milk and Soy"],
            storage_condition="Ambient Cool (15°C - 20°C)",
            shelf_life_days=365,
            requires_cold_chain=False,
            contains_animal_origin=False,
            has_gmo_ingredients=False,
            net_weight_value=Decimal("0.907"),
            net_weight_unit="kg",
            nutrition_panel_verified=True,
        )

        req_2 = ReqGeneral(
            request_type=RequestType.URGENT_CUSTOMS,
            branch_type=RequestBranchType.NO_FOOD,
            status=RequestStatus.PENDING,
            is_urgent=True,
            fiscal_year_id=fy26.id,
            subcategory_id=sub_lithium.id,
            import_route_id=route_dry_hub.id,
            item_code="VT-30910",
            item_description="VoltEdge 1200W Portable LiFePO4 Power Station Dual AC/USB-C",
            brand_name="VoltEdge",
            vendor_name="Shenzhen PowerGrid Technology Co.",
            vendor_country_code="US",
            origin_country_code="US",
            hs_code_proposed="8507.60.00",
            comments="Contenedor próximo a embarque; requiere validación UN3480 y MSDS para tránsito marítimo hacia Caribe.",
            created_by_id=buyer_user.id,
            assigned_to_id=admin_user.id,
            sla_due_at=now + timedelta(days=2),
            destination_countries=[countries[3], countries[5]],
        )
        req_2.no_food_detail = ReqNoFood(
            material_composition="ABS/PC flame-retardant enclosure, LiFePO4 battery cells (1024Wh), copper inverter.",
            is_hazmat_or_flammable=True,
            un_hazmat_code="UN3480",
            contains_lithium_battery=True,
            voltage_specs="110-120V / 60Hz · 1200W Continuous",
            safety_standards=["UL 2743", "UN 38.3", "FCC Part 15"],
            requires_msds=True,
            target_age_group="Adult / Household Backup",
        )

        req_3 = ReqGeneral(
            request_type=RequestType.NEW_ITEM,
            branch_type=RequestBranchType.PRODUCE,
            status=RequestStatus.PARTIALLY_FINISHED,
            is_urgent=False,
            fiscal_year_id=fy26.id,
            subcategory_id=sub_apples.id,
            import_route_id=route_direct_intl.id,
            item_code="PR-10244",
            item_description="Fresh Honeycrisp Apples Bulk Case 18kg (Extra Fancy Grade)",
            brand_name="Cascade Orchards",
            vendor_name="Yakima Valley Growers Coop",
            vendor_country_code="US",
            origin_country_code="US",
            hs_code_proposed="0808.10.00",
            comments="Embarque directo desde Seattle a puertos de Centroamérica; requiere protocolo fitosanitario.",
            created_by_id=buyer_user.id,
            assigned_to_id=analyst_user.id,
            sla_due_at=now + timedelta(days=4),
            destination_countries=[countries[0], countries[1], countries[4]],
        )
        req_3.produce_detail = ReqProduce(
            botanical_name="Malus domestica",
            variety_cultivar="Honeycrisp",
            grower_region="Washington State, USA",
            is_organic=False,
            cold_treatment_required=True,
            fumigation_protocol="USDA-APHIS Systems Approach / Post-harvest Waxing",
            transit_temp_min_c=Decimal("0.50"),
            transit_temp_max_c=Decimal("2.00"),
            packaging_material="Ventilated Corrugated Carton with Food-Grade Trays",
        )

        req_4 = ReqGeneral(
            request_type=RequestType.PLANT_AUDIT,
            branch_type=RequestBranchType.PLANT_APPROVAL,
            status=RequestStatus.COMPLETED,
            is_urgent=False,
            fiscal_year_id=fy26.id,
            subcategory_id=sub_cheese.id,
            import_route_id=route_pa_dc.id,
            item_code="PA-77001",
            item_description="Habilitación Sanitaria Planta Quesos Madurados — Wisconsin Creamery #44",
            brand_name="SelectHarvest",
            vendor_name="Northern Meadows Dairy Corp.",
            vendor_country_code="US",
            origin_country_code="US",
            hs_code_proposed="0406.90.90",
            comments="Auditoría documental aprobada para exportación hacia Panamá (PA-DC1) y Costa Rica.",
            created_by_id=analyst_user.id,
            assigned_to_id=admin_user.id,
            sla_due_at=now - timedelta(days=1),
            closed_at=now - timedelta(hours=12),
            destination_countries=[countries[0], countries[1]],
        )
        req_4.plant_approval_detail = ReqPlantApproval(
            plant_legal_name="Northern Meadows Dairy Processing Facility #44",
            plant_registration_number="WI-DAIRY-44091",
            plant_address="1420 Creamery Rd, Green Bay, WI 54304, USA",
            species_or_product_scope="Pasteurized Cow Milk Aged Cheeses",
            haccp_certified=True,
            gfsi_scheme="SQF Edition 9 (Score 97/100)",
            last_audit_date=date(2026, 2, 18),
            audit_expiration_date=date(2027, 2, 18),
            fda_or_usda_establishment_id="FDA-FFR-1928374650",
        )

        session.add_all([req_1, req_2, req_3, req_4])
        await session.flush()

        # 8. Certificaciones Requeridas por Ítem (ligadas a req_general)
        certs = [
            CertificationRequirement(
                req_general_id=req_1.id,
                country_code="CR",
                origin_scope=OriginScope.US_ORIGIN,
                certificate_name="Certificate of Free Sale (FDA / State Dept.)",
                issuing_body="U.S. FDA or State Chamber",
                is_mandatory=True,
                requires_apostille=True,
                validity_days=365,
                notes="Requerido para el ítem SH-88412 en registro sanitario de Costa Rica.",
            ),
            CertificationRequirement(
                req_general_id=req_1.id,
                country_code="CO",
                origin_scope=OriginScope.ALL,
                certificate_name="Registro Sanitario INVIMA",
                issuing_body="INVIMA Colombia",
                is_mandatory=True,
                requires_apostille=False,
                validity_days=1825,
                notes="Registro sanitario específico para barras y almendras cubiertas de cacao SH-88412.",
            ),
            CertificationRequirement(
                req_general_id=req_2.id,
                country_code=None,
                origin_scope=OriginScope.ALL,
                certificate_name="UN 38.3 Lithium Battery Test Summary & MSDS",
                issuing_body="Certified UN Testing Lab",
                is_mandatory=True,
                requires_apostille=False,
                validity_days=None,
                notes="Aplica de forma global al ítem VT-30910 por contener celdas LiFePO4 (UN3480).",
            ),
            CertificationRequirement(
                req_general_id=req_3.id,
                country_code="PA",
                origin_scope=OriginScope.US_ORIGIN,
                certificate_name="USDA Phytosanitary Certificate",
                issuing_body="USDA-APHIS",
                is_mandatory=True,
                requires_apostille=False,
                validity_days=30,
                notes="Certificado fitosanitario obligatorio por embarque del ítem PR-10244.",
            ),
        ]
        session.add_all(certs)

        # 9. Dictámenes Unificados de Importación (ImportAssessment)
        assessments = [
            ImportAssessment(
                req_general_id=req_1.id,
                country_code="CR",
                reviewer_id=analyst_user.id,
                decision=AssessmentDecision.APPROVED_WITH_CONDITIONS,
                hs_tariff_confirmed="1806.32.00.00",
                import_duty_rate=Decimal("0.00"),
                estimated_lead_time_days=14,
                requires_import_permit=True,
                requires_sanitary_registration=True,
                required_certificates=["Certificate of Free Sale (Apostilled)", "CAFTA-DR Origin Cert"],
                category_checklist={
                    "spanish_complement_label": True,
                    "allergen_declaration_bold": True,
                    "nutritional_table_100g": True,
                },
                technical_notes="Exento bajo CAFTA-DR. Requiere adhesivo complementario RTCA antes de nacionalización.",
                assessed_at=now - timedelta(days=1),
            ),
            ImportAssessment(
                req_general_id=req_1.id,
                country_code="CO",
                reviewer_id=analyst_user.id,
                decision=AssessmentDecision.RESTRICTED,
                hs_tariff_confirmed="1806.32.00.10",
                import_duty_rate=Decimal("0.00"),
                estimated_lead_time_days=21,
                requires_import_permit=True,
                requires_sanitary_registration=True,
                required_certificates=["Registro Sanitario INVIMA", "Certificado de Origen TLC US-CO"],
                category_checklist={
                    "front_warning_octagons": ["EXCESO EN AZÚCARES", "EXCESO EN GRASAS SATURADAS"],
                    "invima_code_printed": False,
                },
                technical_notes="Aplica Resolución 810/2492: proveedor debe incorporar 2 sellos octagonales frontales.",
                assessed_at=now - timedelta(hours=8),
            ),
            ImportAssessment(
                req_general_id=req_2.id,
                country_code="TT",
                reviewer_id=admin_user.id,
                decision=AssessmentDecision.PENDING,
                hs_tariff_confirmed="8507.60.00.00",
                import_duty_rate=Decimal("20.00"),
                estimated_lead_time_days=18,
                requires_import_permit=True,
                requires_sanitary_registration=False,
                required_certificates=["UN 38.3 Lithium Test Summary", "MSDS", "UL 2743 Certificate"],
                category_checklist={
                    "hazmat_class_9_placard": True,
                    "english_safety_manual": True,
                },
                technical_notes="En espera de validación del resumen de pruebas UN38.3 actualizado.",
            ),
            ImportAssessment(
                req_general_id=req_3.id,
                country_code="PA",
                reviewer_id=analyst_user.id,
                decision=AssessmentDecision.APPROVED,
                hs_tariff_confirmed="0808.10.00.00",
                import_duty_rate=Decimal("0.00"),
                estimated_lead_time_days=7,
                requires_import_permit=True,
                requires_sanitary_registration=False,
                required_certificates=["USDA Phytosanitary Certificate", "APA Pre-Notification"],
                category_checklist={
                    "cold_chain_logger_required": True,
                    "pest_free_declaration": True,
                },
                technical_notes="Aprobado para embarque directo con certificado fitosanitario original a bordo.",
                assessed_at=now - timedelta(days=2),
            ),
        ]
        session.add_all(assessments)

        # 9. Auditoría inicial
        audit = UserAuditLog(
            actor_user_id=admin_user.id,
            action="seed.bootstrap",
            entity_type="system",
            entity_id="trade_compliance_v2",
            changes_payload={
                "models_initialized": 18,
                "predefined_routes": 10,
                "excluded_modules": ["ffe", "forum", "inquiries"],
            },
            ip_address="127.0.0.1",
        )
        session.add(audit)

        await session.commit()
        print("Esquema y datos iniciales cargados correctamente.")


async def main() -> None:
    try:
        await seed_database()
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
