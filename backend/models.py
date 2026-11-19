from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


# =============================================================================
# ENUMS NATIVOS DE POSTGRESQL
# =============================================================================


class RequestBranchType(str, enum.Enum):
    FOOD = "food"
    NO_FOOD = "no_food"
    PRODUCE = "produce"
    PLANT_APPROVAL = "plant_approval"


class RequestType(str, enum.Enum):
    NEW_ITEM = "new_item"
    RE_EVALUATION = "re_evaluation"
    URGENT_CUSTOMS = "urgent_customs"
    PLANT_AUDIT = "plant_audit"


class RequestStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    PARTIALLY_FINISHED = "partially_finished"
    COMPLETED = "completed"
    CANCELED = "canceled"


class RegulationStatus(str, enum.Enum):
    ENFORCED = "enforced"
    TO_BE_ENFORCED = "to_be_enforced"
    DRAFT = "draft"
    DORMANT = "dormant"


class ProductClassification(str, enum.Enum):
    FOOD = "food"
    NON_FOOD = "non_food"
    PRODUCE = "produce"
    ALL = "all"


class OriginScope(str, enum.Enum):
    US_ORIGIN = "us_origin"
    NON_US_ORIGIN = "non_us_origin"
    ALL = "all"


class AssessmentDecision(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    APPROVED_WITH_CONDITIONS = "approved_with_conditions"
    RESTRICTED = "restricted"
    PROHIBITED = "prohibited"


class LogisticsRouteCode(str, enum.Enum):
    CENTRAL_HUB = "central_hub"
    SUPPLIER_TO_HUB = "supplier_to_hub"
    DIRECT_PORT_TO_PORT = "direct_port_to_port"
    REGIONAL_DRY_HUB = "regional_dry_hub"
    REGIONAL_COLD_HUB = "regional_cold_hub"
    CO_NATIONAL_DC = "co_national_dc"
    PA_NATIONAL_DC = "pa_national_dc"
    CR_DIRECT_PORT = "cr_direct_port"
    DO_NATIONAL_DC = "do_national_dc"
    TT_NATIONAL_DC = "tt_national_dc"


# =============================================================================
# TABLAS PUENTE MANY-TO-MANY (M2M)
# =============================================================================

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

req_general_countries = Table(
    "req_general_countries",
    Base.metadata,
    Column(
        "req_general_id",
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "country_code",
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

regulation_subcategories = Table(
    "regulation_subcategories",
    Base.metadata,
    Column(
        "regulation_id",
        UUID(as_uuid=True),
        ForeignKey("regulations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "subcategory_id",
        UUID(as_uuid=True),
        ForeignKey("subcategories.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# =============================================================================
# 1. MÓDULO DE SEGURIDAD, RBAC Y AUDITORÍA
# =============================================================================


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )
    users: Mapped[list[User]] = relationship("User", back_populates="role")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    code: Mapped[str] = mapped_column(String(90), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(255))

    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary=role_permissions,
        back_populates="permissions",
    )

    __table_args__ = (
        UniqueConstraint("module", "action", name="uq_permissions_module_action"),
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    primary_country_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="SET NULL"),
        index=True,
    )
    department_code: Mapped[str | None] = mapped_column(String(40))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    role: Mapped[Role] = relationship("Role", back_populates="users", lazy="joined")
    primary_country: Mapped[Country | None] = relationship("Country", lazy="joined")
    created_requests: Mapped[list[ReqGeneral]] = relationship(
        "ReqGeneral",
        back_populates="created_by",
        foreign_keys="ReqGeneral.created_by_id",
    )
    assigned_requests: Mapped[list[ReqGeneral]] = relationship(
        "ReqGeneral",
        back_populates="assigned_to",
        foreign_keys="ReqGeneral.assigned_to_id",
    )
    audit_logs: Mapped[list[UserAuditLog]] = relationship(
        "UserAuditLog",
        back_populates="actor_user",
        foreign_keys="UserAuditLog.actor_user_id",
    )


class UserAuditLog(Base):
    """Trazabilidad inmutable de eventos críticos (reemplaza user_logs)."""

    __tablename__ = "user_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    changes_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    actor_user: Mapped[User | None] = relationship(
        "User", back_populates="audit_logs", foreign_keys=[actor_user_id]
    )


# =============================================================================
# 2. CATÁLOGOS GEOGRÁFICOS Y TAXONOMÍA COMERCIAL
# =============================================================================


class Country(Base):
    """Unifica `countries` y `paises` con código ISO 3166-1 alpha-2 como PK."""

    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(String(2), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    regulatory_agency: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    regulations: Mapped[list[Regulation]] = relationship(
        "Regulation", back_populates="country"
    )
    import_routes: Mapped[list[ImportRoute]] = relationship(
        "ImportRoute", back_populates="country"
    )
    certifications: Mapped[list[CertificationRequirement]] = relationship(
        "CertificationRequirement", back_populates="country"
    )
    requests: Mapped[list[ReqGeneral]] = relationship(
        "ReqGeneral",
        secondary=req_general_countries,
        back_populates="destination_countries",
    )

    __table_args__ = (
        CheckConstraint("char_length(code) = 2", name="country_iso_alpha2_len"),
    )


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    categories: Mapped[list[Category]] = relationship(
        "Category", back_populates="department", cascade="all, delete-orphan"
    )


class Category(Base):
    """Unifica las tablas duplicadas `categories` y `category`."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    department_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    classification: Mapped[ProductClassification] = mapped_column(
        SAEnum(ProductClassification, name="product_classification_enum"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    department: Mapped[Department] = relationship(
        "Department", back_populates="categories", lazy="joined"
    )
    subcategories: Mapped[list[Subcategory]] = relationship(
        "Subcategory", back_populates="category", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("department_id", "code", name="uq_categories_dept_code"),
    )


class Subcategory(Base):
    """Unifica las tablas duplicadas `subcategories` y `subcategory`."""

    __tablename__ = "subcategories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    hs_chapter_hint: Mapped[str | None] = mapped_column(String(10))
    requires_sanitary_reg: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped[Category] = relationship(
        "Category", back_populates="subcategories", lazy="joined"
    )
    regulations: Mapped[list[Regulation]] = relationship(
        "Regulation",
        secondary=regulation_subcategories,
        back_populates="subcategories",
    )
    requests: Mapped[list[ReqGeneral]] = relationship(
        "ReqGeneral", back_populates="subcategory"
    )

    __table_args__ = (
        UniqueConstraint("category_id", "code", name="uq_subcategories_cat_code"),
    )


class FiscalYear(Base):
    __tablename__ = "fiscal_years"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("end_date > start_date", name="fiscal_year_valid_range"),
    )


# =============================================================================
# 3. MOTOR REGULATORIO MULTINACIONAL Y RUTAS LOGÍSTICAS
# =============================================================================


class Regulation(Base):
    """Unifica `regulations` y `regulaciones` eliminando el texto libre desnormalizado."""

    __tablename__ = "regulations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    country_code: Mapped[str] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        index=True,
    )
    regulation_code: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    issuing_authority: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[RegulationStatus] = mapped_column(
        SAEnum(RegulationStatus, name="regulation_status_enum"),
        default=RegulationStatus.ENFORCED,
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    requirements_detail: Mapped[str | None] = mapped_column(Text)
    effective_date: Mapped[date | None] = mapped_column(Date)
    expiration_date: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(500))
    metadata_extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    country: Mapped[Country] = relationship("Country", back_populates="regulations")
    department: Mapped[Department | None] = relationship("Department")
    subcategories: Mapped[list[Subcategory]] = relationship(
        "Subcategory",
        secondary=regulation_subcategories,
        back_populates="regulations",
    )

    __table_args__ = (
        UniqueConstraint(
            "country_code", "regulation_code", name="uq_regulations_country_code"
        ),
    )


class CertificationRequirement(Base):
    """Normaliza `eq_certifications` ligando cada certificado requerido al ítem/solicitud (`req_general`)."""

    __tablename__ = "certification_requirements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    req_general_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    origin_scope: Mapped[OriginScope] = mapped_column(
        SAEnum(OriginScope, name="origin_scope_enum"),
        nullable=False,
        default=OriginScope.ALL,
    )
    certificate_name: Mapped[str] = mapped_column(String(160), nullable=False)
    issuing_body: Mapped[str | None] = mapped_column(String(160))
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_apostille: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validity_days: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    req_general: Mapped[ReqGeneral] = relationship(
        "ReqGeneral", back_populates="certifications"
    )
    country: Mapped[Country | None] = relationship("Country", back_populates="certifications")


class ImportRoute(Base):
    """Catálogo normalizado de rutas logísticas predefinidas y Centros de Distribución (DC)."""

    __tablename__ = "import_routes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    route_code: Mapped[LogisticsRouteCode] = mapped_column(
        SAEnum(LogisticsRouteCode, name="logistics_route_code_enum"),
        nullable=False,
        index=True,
    )
    route_name: Mapped[str] = mapped_column(String(120), nullable=False)
    dc_code: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    country_code: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    classification: Mapped[ProductClassification | None] = mapped_column(
        SAEnum(ProductClassification, name="product_classification_enum"),
        nullable=True,
    )
    required_document: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    us_origin_rules: Mapped[str | None] = mapped_column(Text)
    non_us_origin_rules: Mapped[str | None] = mapped_column(Text)
    is_direct_to_destination: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    country: Mapped[Country | None] = relationship("Country", back_populates="import_routes")
    requests: Mapped[list[ReqGeneral]] = relationship(
        "ReqGeneral", back_populates="import_route"
    )

    __table_args__ = (
        UniqueConstraint("route_code", "dc_code", name="uq_import_routes_code_dc"),
    )


# =============================================================================
# 4. NÚCLEO DE SOLICITUDES (PATRÓN SUPERTIPO / SUBTIPO 1:1)
# =============================================================================

class ReqGeneral(Base):
    """
    Entidad raíz única de requerimientos.
    Consolida `req_general`, `requirement` y `req_rf_nf`, eliminando las 17 columnas
    duplicadas que el esquema legado copiaba en cada tabla hija.
    """

    __tablename__ = "req_general"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_number: Mapped[int] = mapped_column(
        Integer,
        Identity(start=0, minvalue=0),
        unique=True,
        nullable=False,
        index=True,
    )
    request_type: Mapped[RequestType] = mapped_column(
        SAEnum(RequestType, name="request_type_enum"),
        nullable=False,
        default=RequestType.NEW_ITEM,
    )
    branch_type: Mapped[RequestBranchType] = mapped_column(
        SAEnum(RequestBranchType, name="request_branch_type_enum"),
        nullable=False,
        index=True,
    )
    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus, name="request_status_enum"),
        nullable=False,
        default=RequestStatus.PENDING,
        index=True,
    )
    is_urgent: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="Absorbe la antigua bandera req_rf_nf",
    )

    # Relaciones de catálogo (jerarquía estricta: Subcategory -> Category -> Department)
    fiscal_year_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fiscal_years.id", ondelete="SET NULL"), index=True
    )
    subcategory_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subcategories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    import_route_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("import_routes.id", ondelete="SET NULL"), index=True
    )

    # Datos maestros de artículo / proveedor
    item_code: Mapped[str | None] = mapped_column(String(40), index=True)
    item_description: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_name: Mapped[str | None] = mapped_column(String(120))
    vendor_name: Mapped[str] = mapped_column(String(160), nullable=False)
    vendor_country_code: Mapped[str] = mapped_column(
        String(2), ForeignKey("countries.code", ondelete="RESTRICT"), nullable=False
    )
    origin_country_code: Mapped[str] = mapped_column(
        String(2), ForeignKey("countries.code", ondelete="RESTRICT"), nullable=False
    )
    hs_code_proposed: Mapped[str | None] = mapped_column(String(20), index=True)
    comments: Mapped[str | None] = mapped_column(Text)

    # Propiedad y ciclo de vida
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relaciones ORM
    fiscal_year: Mapped[FiscalYear | None] = relationship("FiscalYear")
    subcategory: Mapped[Subcategory] = relationship(
        "Subcategory", back_populates="requests", lazy="joined"
    )
    import_route: Mapped[ImportRoute | None] = relationship(
        "ImportRoute", back_populates="requests"
    )
    vendor_country: Mapped[Country] = relationship(
        "Country", foreign_keys=[vendor_country_code]
    )
    origin_country: Mapped[Country] = relationship(
        "Country", foreign_keys=[origin_country_code]
    )
    created_by: Mapped[User] = relationship(
        "User", back_populates="created_requests", foreign_keys=[created_by_id]
    )
    assigned_to: Mapped[User | None] = relationship(
        "User", back_populates="assigned_requests", foreign_keys=[assigned_to_id]
    )
    destination_countries: Mapped[list[Country]] = relationship(
        "Country",
        secondary=req_general_countries,
        back_populates="requests",
        lazy="selectin",
    )
    certifications: Mapped[list[CertificationRequirement]] = relationship(
        "CertificationRequirement",
        back_populates="req_general",
        cascade="all, delete-orphan",
    )

    @property
    def category(self) -> Category | None:
        return self.subcategory.category if self.subcategory else None

    @property
    def department(self) -> Department | None:
        return (
            self.subcategory.category.department
            if self.subcategory and self.subcategory.category
            else None
        )

    # Ramificación estricta 1:1 (Shared Primary Key)
    food_detail: Mapped[ReqFood | None] = relationship(
        "ReqFood", back_populates="req_general", uselist=False, cascade="all, delete-orphan"
    )
    no_food_detail: Mapped[ReqNoFood | None] = relationship(
        "ReqNoFood", back_populates="req_general", uselist=False, cascade="all, delete-orphan"
    )
    produce_detail: Mapped[ReqProduce | None] = relationship(
        "ReqProduce", back_populates="req_general", uselist=False, cascade="all, delete-orphan"
    )
    plant_approval_detail: Mapped[ReqPlantApproval | None] = relationship(
        "ReqPlantApproval",
        back_populates="req_general",
        uselist=False,
        cascade="all, delete-orphan",
    )

    assessments: Mapped[list[ImportAssessment]] = relationship(
        "ImportAssessment", back_populates="req_general", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_req_general_status_branch", "status", "branch_type"),
    )


class ReqFood(Base):
    """Extensión 1:1 exclusiva para alimentos procesados, bebidas y suplementos."""

    __tablename__ = "req_food"

    req_general_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        primary_key=True,
    )
    ingredients_summary: Mapped[str] = mapped_column(Text, nullable=False)
    allergens: Mapped[list[str] | None] = mapped_column(JSONB)
    storage_condition: Mapped[str] = mapped_column(String(60), nullable=False)
    shelf_life_days: Mapped[int | None] = mapped_column(Integer)
    requires_cold_chain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contains_animal_origin: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    has_gmo_ingredients: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    net_weight_value: Mapped[Decimal | None] = mapped_column(Numeric(10, 3))
    net_weight_unit: Mapped[str | None] = mapped_column(String(15))
    nutrition_panel_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    req_general: Mapped[ReqGeneral] = relationship("ReqGeneral", back_populates="food_detail")

    __table_args__ = (
        CheckConstraint("shelf_life_days IS NULL OR shelf_life_days > 0", name="positive_shelf_life"),
    )


class ReqNoFood(Base):
    """Extensión 1:1 para electrónica, químicos, cosméticos, textiles y mercancía general."""

    __tablename__ = "req_no_food"

    req_general_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        primary_key=True,
    )
    material_composition: Mapped[str] = mapped_column(Text, nullable=False)
    is_hazmat_or_flammable: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    un_hazmat_code: Mapped[str | None] = mapped_column(String(20))
    contains_lithium_battery: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    voltage_specs: Mapped[str | None] = mapped_column(String(80))
    safety_standards: Mapped[list[str] | None] = mapped_column(JSONB)
    requires_msds: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    target_age_group: Mapped[str | None] = mapped_column(String(60))

    req_general: Mapped[ReqGeneral] = relationship(
        "ReqGeneral", back_populates="no_food_detail"
    )


class ReqProduce(Base):
    """Extensión 1:1 para productos frescos, agrícolas y fitosanitarios."""

    __tablename__ = "req_produce"

    req_general_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        primary_key=True,
    )
    botanical_name: Mapped[str] = mapped_column(String(160), nullable=False)
    variety_cultivar: Mapped[str | None] = mapped_column(String(120))
    grower_region: Mapped[str] = mapped_column(String(120), nullable=False)
    is_organic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cold_treatment_required: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    fumigation_protocol: Mapped[str | None] = mapped_column(String(140))
    transit_temp_min_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    transit_temp_max_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    packaging_material: Mapped[str | None] = mapped_column(String(120))

    req_general: Mapped[ReqGeneral] = relationship(
        "ReqGeneral", back_populates="produce_detail"
    )


class ReqPlantApproval(Base):
    """Extensión 1:1 para habilitación y auditoría sanitaria de plantas procesadoras."""

    __tablename__ = "req_plant_approval"

    req_general_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        primary_key=True,
    )
    plant_legal_name: Mapped[str] = mapped_column(String(180), nullable=False)
    plant_registration_number: Mapped[str] = mapped_column(String(80), nullable=False)
    plant_address: Mapped[str] = mapped_column(Text, nullable=False)
    species_or_product_scope: Mapped[str] = mapped_column(String(200), nullable=False)
    haccp_certified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gfsi_scheme: Mapped[str | None] = mapped_column(String(80))
    last_audit_date: Mapped[date | None] = mapped_column(Date)
    audit_expiration_date: Mapped[date | None] = mapped_column(Date)
    fda_or_usda_establishment_id: Mapped[str | None] = mapped_column(String(60))

    req_general: Mapped[ReqGeneral] = relationship(
        "ReqGeneral", back_populates="plant_approval_detail"
    )


# =============================================================================
# 5. DICTAMEN UNIFICADO DE IMPORTACIÓN (CONSOLIDA LAS 5 TABLAS `ans_*`)
# =============================================================================


class ImportAssessment(Base):
    """
    Unifica las tablas redundantes del legado (`ans_general`, `ans_food`,
    `ans_no_food`, `ans_produce`, `ans_plant_approval`) en una única tabla de
    dictamen por país destino, aprovechando JSONB para listas de chequeo dinámicas.
    """

    __tablename__ = "import_assessments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    req_general_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("req_general.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    country_code: Mapped[str] = mapped_column(
        String(2),
        ForeignKey("countries.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    decision: Mapped[AssessmentDecision] = mapped_column(
        SAEnum(AssessmentDecision, name="assessment_decision_enum"),
        default=AssessmentDecision.PENDING,
        nullable=False,
        index=True,
    )
    hs_tariff_confirmed: Mapped[str | None] = mapped_column(String(20))
    import_duty_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    estimated_lead_time_days: Mapped[int | None] = mapped_column(Integer)
    requires_import_permit: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    requires_sanitary_registration: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    required_certificates: Mapped[list[str] | None] = mapped_column(JSONB)
    category_checklist: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        comment="Respuestas específicas según branch_type (etiquetado, cold-chain, MSDS, etc.)",
    )
    technical_notes: Mapped[str | None] = mapped_column(Text)
    assessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    req_general: Mapped[ReqGeneral] = relationship(
        "ReqGeneral", back_populates="assessments"
    )
    country: Mapped[Country] = relationship("Country")
    reviewer: Mapped[User | None] = relationship("User")

    __table_args__ = (
        UniqueConstraint(
            "req_general_id", "country_code", name="uq_import_assessments_req_country"
        ),
        CheckConstraint(
            "import_duty_rate IS NULL OR (import_duty_rate >= 0 AND import_duty_rate <= 100)",
            name="valid_duty_rate_pct",
        ),
    )
