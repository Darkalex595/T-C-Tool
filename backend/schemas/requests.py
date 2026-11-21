from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.models import (
    AssessmentDecision,
    RequestBranchType,
    RequestStatus,
    RequestType,
)
from backend.schemas.auth import UserSummary
from backend.schemas.catalogs import (
    CategoryRead,
    CountryRead,
    DepartmentRead,
    SubcategoryRead,
)
from backend.schemas.compliance import CertificationRead, ImportRouteRead

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Contenedor estándar para listados paginados en toda la API."""

    items: list[T]
    total: int
    limit: int
    offset: int


# --- Extensiones 1:1 de ReqGeneral (Shared Primary Key) ---


class ReqFoodDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ingredients_summary: str = Field(..., min_length=3)
    allergens: list[str] | None = None
    storage_condition: str = Field(..., min_length=2, max_length=60)
    shelf_life_days: int | None = Field(default=None, gt=0)
    requires_cold_chain: bool = False
    contains_animal_origin: bool = False
    has_gmo_ingredients: bool = False
    net_weight_value: Decimal | None = Field(default=None, gt=0)
    net_weight_unit: str | None = Field(default=None, max_length=15)
    nutrition_panel_verified: bool = False


class ReqNoFoodDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    material_composition: str = Field(..., min_length=3)
    is_hazmat_or_flammable: bool = False
    un_hazmat_code: str | None = Field(default=None, max_length=20)
    contains_lithium_battery: bool = False
    voltage_specs: str | None = Field(default=None, max_length=80)
    safety_standards: list[str] | None = None
    requires_msds: bool = False
    target_age_group: str | None = Field(default=None, max_length=60)


class ReqProduceDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    botanical_name: str = Field(..., min_length=2, max_length=160)
    variety_cultivar: str | None = Field(default=None, max_length=120)
    grower_region: str = Field(..., min_length=2, max_length=120)
    is_organic: bool = False
    cold_treatment_required: bool = False
    fumigation_protocol: str | None = Field(default=None, max_length=140)
    transit_temp_min_c: Decimal | None = None
    transit_temp_max_c: Decimal | None = None
    packaging_material: str | None = Field(default=None, max_length=120)


class ReqPlantApprovalDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    plant_legal_name: str = Field(..., min_length=2, max_length=180)
    plant_registration_number: str = Field(..., min_length=2, max_length=80)
    plant_address: str = Field(..., min_length=5)
    species_or_product_scope: str = Field(..., min_length=2, max_length=200)
    haccp_certified: bool = False
    gfsi_scheme: str | None = Field(default=None, max_length=80)
    last_audit_date: date | None = None
    audit_expiration_date: date | None = None
    fda_or_usda_establishment_id: str | None = Field(default=None, max_length=60)


# --- Dictámenes por País (ImportAssessment) ---


class ImportAssessmentUpsert(BaseModel):
    """Permite crear o actualizar el dictamen técnico de un país destino para un ítem."""

    country_code: str = Field(..., min_length=2, max_length=2)
    decision: AssessmentDecision = AssessmentDecision.PENDING
    hs_tariff_confirmed: str | None = Field(default=None, max_length=20)
    import_duty_rate: Decimal | None = Field(default=None, ge=0, le=100)
    estimated_lead_time_days: int | None = Field(default=None, ge=0)
    requires_import_permit: bool = False
    requires_sanitary_registration: bool = False
    required_certificates: list[str] | None = None
    category_checklist: dict[str, Any] | None = None
    technical_notes: str | None = None

    @field_validator("country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.strip().upper()


class ImportAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    req_general_id: UUID
    country_code: str
    reviewer: UserSummary | None = None
    decision: AssessmentDecision
    hs_tariff_confirmed: str | None
    import_duty_rate: Decimal | None
    estimated_lead_time_days: int | None
    requires_import_permit: bool
    requires_sanitary_registration: bool
    required_certificates: list[str] | None
    category_checklist: dict[str, Any] | None
    technical_notes: str | None
    assessed_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- Solicitud Principal (ReqGeneral) ---


class ReqGeneralCreate(BaseModel):
    """
    Contrato de creación atómica: crea ReqGeneral + su tabla 1:1 correspondiente
    validando que el detalle enviado coincida exactamente con `branch_type`.
    """

    request_type: RequestType = RequestType.NEW_ITEM
    branch_type: RequestBranchType
    is_urgent: bool = False
    fiscal_year_id: UUID | None = None
    subcategory_id: UUID
    import_route_id: UUID | None = None

    item_code: str | None = Field(default=None, max_length=40)
    item_description: str = Field(..., min_length=3, max_length=255)
    brand_name: str | None = Field(default=None, max_length=120)
    vendor_name: str = Field(..., min_length=2, max_length=160)
    vendor_country_code: str = Field(..., min_length=2, max_length=2)
    origin_country_code: str = Field(..., min_length=2, max_length=2)
    hs_code_proposed: str | None = Field(default=None, max_length=20)
    comments: str | None = None
    assigned_to_id: UUID | None = None
    sla_due_at: datetime | None = None

    destination_country_codes: list[str] = Field(..., min_length=1)

    food_detail: ReqFoodDetail | None = None
    no_food_detail: ReqNoFoodDetail | None = None
    produce_detail: ReqProduceDetail | None = None
    plant_approval_detail: ReqPlantApprovalDetail | None = None

    @field_validator("vendor_country_code", "origin_country_code")
    @classmethod
    def normalize_iso_country(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("destination_country_codes")
    @classmethod
    def normalize_destinations(cls, values: list[str]) -> list[str]:
        normalized = list(dict.fromkeys(v.strip().upper() for v in values if v.strip()))
        if not normalized or any(len(code) != 2 for code in normalized):
            raise ValueError(
                "destination_country_codes debe incluir al menos un código ISO-2 válido."
            )
        return normalized

    @model_validator(mode="after")
    def validate_branch_detail_consistency(self) -> ReqGeneralCreate:
        branch_map = {
            RequestBranchType.FOOD: ("food_detail", self.food_detail),
            RequestBranchType.NO_FOOD: ("no_food_detail", self.no_food_detail),
            RequestBranchType.PRODUCE: ("produce_detail", self.produce_detail),
            RequestBranchType.PLANT_APPROVAL: (
                "plant_approval_detail",
                self.plant_approval_detail,
            ),
        }
        expected_field, expected_value = branch_map[self.branch_type]
        if expected_value is None:
            raise ValueError(
                f"Para branch_type='{self.branch_type.value}' debes enviar '{expected_field}'."
            )

        extra_fields = [
            name
            for branch, (name, val) in branch_map.items()
            if branch != self.branch_type and val is not None
        ]
        if extra_fields:
            raise ValueError(
                f"Campos incompatibles con branch_type='{self.branch_type.value}': "
                f"{', '.join(extra_fields)}."
            )
        return self


class ReqFoodUpdate(BaseModel):
    ingredients_summary: str | None = Field(default=None, min_length=3)
    allergens: list[str] | None = None
    storage_condition: str | None = Field(default=None, min_length=2, max_length=60)
    shelf_life_days: int | None = Field(default=None, gt=0)
    requires_cold_chain: bool | None = None
    contains_animal_origin: bool | None = None
    has_gmo_ingredients: bool | None = None
    net_weight_value: Decimal | None = Field(default=None, gt=0)
    net_weight_unit: str | None = Field(default=None, max_length=15)
    nutrition_panel_verified: bool | None = None


class ReqNoFoodUpdate(BaseModel):
    material_composition: str | None = Field(default=None, min_length=3)
    is_hazmat_or_flammable: bool | None = None
    un_hazmat_code: str | None = Field(default=None, max_length=20)
    contains_lithium_battery: bool | None = None
    voltage_specs: str | None = Field(default=None, max_length=80)
    safety_standards: list[str] | None = None
    requires_msds: bool | None = None
    target_age_group: str | None = Field(default=None, max_length=60)


class ReqProduceUpdate(BaseModel):
    botanical_name: str | None = Field(default=None, min_length=2, max_length=160)
    variety_cultivar: str | None = Field(default=None, max_length=120)
    grower_region: str | None = Field(default=None, min_length=2, max_length=120)
    is_organic: bool | None = None
    cold_treatment_required: bool | None = None
    fumigation_protocol: str | None = Field(default=None, max_length=140)
    transit_temp_min_c: Decimal | None = None
    transit_temp_max_c: Decimal | None = None
    packaging_material: str | None = Field(default=None, max_length=120)


class ReqPlantApprovalUpdate(BaseModel):
    plant_legal_name: str | None = Field(default=None, min_length=2, max_length=180)
    plant_registration_number: str | None = Field(default=None, min_length=2, max_length=80)
    plant_address: str | None = Field(default=None, min_length=5)
    species_or_product_scope: str | None = Field(default=None, min_length=2, max_length=200)
    haccp_certified: bool | None = None
    gfsi_scheme: str | None = Field(default=None, max_length=80)
    last_audit_date: date | None = None
    audit_expiration_date: date | None = None
    fda_or_usda_establishment_id: str | None = Field(default=None, max_length=60)


class ReqGeneralUpdate(BaseModel):
    is_urgent: bool | None = None
    fiscal_year_id: UUID | None = None
    subcategory_id: UUID | None = None
    import_route_id: UUID | None = None
    item_code: str | None = Field(default=None, max_length=40)
    item_description: str | None = Field(default=None, min_length=3, max_length=255)
    brand_name: str | None = Field(default=None, max_length=120)
    hs_code_proposed: str | None = Field(default=None, max_length=20)
    comments: str | None = None
    assigned_to_id: UUID | None = None
    sla_due_at: datetime | None = None
    destination_country_codes: list[str] | None = Field(default=None, min_length=1)

    food_detail: ReqFoodUpdate | None = None
    no_food_detail: ReqNoFoodUpdate | None = None
    produce_detail: ReqProduceUpdate | None = None
    plant_approval_detail: ReqPlantApprovalUpdate | None = None

    @field_validator("destination_country_codes")
    @classmethod
    def normalize_destinations(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = list(dict.fromkeys(v.strip().upper() for v in values if v.strip()))
        if not normalized or any(len(code) != 2 for code in normalized):
            raise ValueError(
                "destination_country_codes debe incluir al menos un código ISO-2 válido."
            )
        return normalized


class ReqGeneralStatusUpdate(BaseModel):
    """Cambio explícito de estado global (protegido por `requests:approve`)."""

    status: RequestStatus
    comments: str | None = None


class DashboardMetricsRead(BaseModel):
    """Métricas agregadas en tiempo real desde PostgreSQL para el panel operativo."""

    total_requests: int
    urgent_open_requests: int
    overdue_sla_requests: int
    requests_by_status: dict[str, int]
    requests_by_branch: dict[str, int]
    assessments_by_decision: dict[str, int]
    regulations_by_status: dict[str, int]


class ReqGeneralSummaryRead(BaseModel):
    """Vista compacta de solicitud para tablas y listados."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ticket_number: int
    request_type: RequestType
    branch_type: RequestBranchType
    status: RequestStatus
    is_urgent: bool
    item_code: str | None
    item_description: str
    brand_name: str | None
    vendor_name: str
    origin_country_code: str
    hs_code_proposed: str | None
    subcategory: SubcategoryRead
    category: CategoryRead | None = None
    department: DepartmentRead | None = None
    destination_countries: list[CountryRead] = Field(default_factory=list)
    created_by: UserSummary
    assigned_to: UserSummary | None = None
    sla_due_at: datetime | None
    closed_at: datetime | None
    created_at: datetime


class ReqGeneralDetailRead(ReqGeneralSummaryRead):
    """Vista completa de solicitud con su extensión 1:1, certificaciones y dictámenes."""

    vendor_country_code: str
    comments: str | None
    import_route: ImportRouteRead | None = None
    food_detail: ReqFoodDetail | None = None
    no_food_detail: ReqNoFoodDetail | None = None
    produce_detail: ReqProduceDetail | None = None
    plant_approval_detail: ReqPlantApprovalDetail | None = None
    certifications: list[CertificationRead] = Field(default_factory=list)
    assessments: list[ImportAssessmentRead] = Field(default_factory=list)
    updated_at: datetime
