"""Fail-closed AES-256 protection and independent verification."""

from __future__ import annotations

import io
from dataclasses import dataclass

from .models import EditingRestrictionSettings


class PDFSecurityError(RuntimeError):
    """Raised when protection cannot be applied and verified exactly."""


@dataclass(frozen=True)
class ProtectionVerification:
    encrypted: bool
    encryption_bits: int
    security_revision: int
    permissions_verified: bool
    independent_parser_verified: bool


def validate_export_passwords(
    owner_password: str | None,
    owner_password_confirm: str | None,
    open_password: str | None = None,
) -> None:
    if owner_password is None or len(owner_password) < 12:
        raise PDFSecurityError("Owner password must contain at least 12 characters")
    if owner_password != owner_password_confirm:
        raise PDFSecurityError("Owner-password entries do not match")
    if open_password is not None and open_password == owner_password:
        raise PDFSecurityError("Document-open and owner passwords must differ")


def _pike_permissions(settings: EditingRestrictionSettings):
    try:
        import pikepdf
    except ImportError as exc:
        raise PDFSecurityError(
            "Protected export requires the pinned pikepdf/QPDF runtime; no unrestricted PDF was produced"
        ) from exc
    return pikepdf.Permissions(
        accessibility=True,
        extract=settings.allow_copying,
        modify_annotation=settings.allow_annotations,
        modify_assembly=settings.allow_page_assembly,
        modify_form=settings.allow_form_filling,
        modify_other=settings.allow_document_changes,
        print_highres=settings.allow_printing,
        print_lowres=settings.allow_printing,
    )


def _verify_with_pikepdf(
    payload: bytes,
    owner_password: str,
    settings: EditingRestrictionSettings,
) -> ProtectionVerification:
    import pikepdf

    with pikepdf.Pdf.open(io.BytesIO(payload), password=owner_password) as verified:
        if not verified.is_encrypted:
            raise PDFSecurityError("Protection verification failed: output is not encrypted")
        if verified.encryption.bits != 256 or verified.encryption.R != 6:
            raise PDFSecurityError("Protection verification failed: output is not AES-256 revision 6")
        if "/AcroForm" in verified.Root:
            raise PDFSecurityError("Protection verification failed: output contains AcroForm fields")
        if "/OCProperties" in verified.Root:
            raise PDFSecurityError("Protection verification failed: optional-content layers are not allowed")

        allow = verified.allow
        expected = {
            "accessibility": True,
            "extract": settings.allow_copying,
            "modify_annotation": settings.allow_annotations,
            "modify_assembly": settings.allow_page_assembly,
            "modify_form": settings.allow_form_filling,
            "modify_other": settings.allow_document_changes,
            "print_highres": settings.allow_printing,
            "print_lowres": settings.allow_printing,
        }
        mismatches = [name for name, value in expected.items() if bool(getattr(allow, name)) != value]
        if mismatches:
            raise PDFSecurityError(
                "Protection verification failed for requested permission flags: "
                + ", ".join(mismatches)
            )

    _verify_with_pypdf(payload, owner_password, settings)
    return ProtectionVerification(True, 256, 6, True, True)


def _verify_with_pypdf(
    payload: bytes,
    owner_password: str,
    settings: EditingRestrictionSettings,
) -> None:
    """Independently reopen with pypdf and validate security dictionary flags."""

    try:
        from pypdf import PdfReader
        from pypdf.constants import UserAccessPermissions as UAP

        reader = PdfReader(io.BytesIO(payload))
        if not reader.is_encrypted or reader.decrypt(owner_password) == 0:
            raise PDFSecurityError("Independent protection verification could not decrypt the output")
        encryption = reader.trailer["/Encrypt"]
        if int(encryption.get("/R", 0)) != 6 or int(encryption.get("/Length", 0)) != 256:
            raise PDFSecurityError("Independent parser did not confirm AES-256 revision 6")
        if not reader.are_permissions_valid:
            raise PDFSecurityError("Independent parser rejected the AES-256 permissions integrity check")
        if "/AcroForm" in reader.trailer["/Root"]:
            raise PDFSecurityError("Independent parser found prohibited AcroForm fields")
        permissions = reader.user_access_permissions
        if permissions is None:
            raise PDFSecurityError("Independent parser did not expose permission flags")

        checks = {
            UAP.MODIFY: settings.allow_document_changes,
            UAP.ADD_OR_MODIFY: settings.allow_annotations,
            UAP.FILL_FORM_FIELDS: settings.allow_form_filling,
            UAP.ASSEMBLE_DOC: settings.allow_page_assembly,
            UAP.EXTRACT: settings.allow_copying,
            UAP.PRINT: settings.allow_printing,
            UAP.PRINT_TO_REPRESENTATION: settings.allow_printing,
            UAP.EXTRACT_TEXT_AND_GRAPHICS: True,
        }
        failed = [flag.name for flag, expected in checks.items() if bool(permissions & flag) != expected]
        if failed:
            raise PDFSecurityError(
                "Independent parser found unexpected permission flags: " + ", ".join(failed)
            )
    except PDFSecurityError:
        raise
    except Exception as exc:
        raise PDFSecurityError("Independent protection verification failed closed") from exc


def protect_pdf(
    unprotected_pdf: bytes,
    settings: EditingRestrictionSettings,
    *,
    owner_password: str | None,
    owner_password_confirm: str | None,
    open_password: str | None = None,
) -> tuple[bytes, ProtectionVerification]:
    """Encrypt only after all page content, links, identifiers, and metadata exist."""

    validate_export_passwords(owner_password, owner_password_confirm, open_password)
    permissions = _pike_permissions(settings)
    try:
        import pikepdf

        source = io.BytesIO(unprotected_pdf)
        destination = io.BytesIO()
        with pikepdf.Pdf.open(source) as pdf:
            if "/AcroForm" in pdf.Root:
                raise PDFSecurityError("Static export unexpectedly contains AcroForm fields")
            pdf.save(
                destination,
                encryption=pikepdf.Encryption(
                    owner=owner_password or "",
                    user=open_password or "",
                    R=6,
                    aes=True,
                    metadata=True,
                    allow=permissions,
                ),
            )
        protected = destination.getvalue()
        verification = _verify_with_pikepdf(protected, owner_password or "", settings)
        return protected, verification
    except PDFSecurityError:
        raise
    except Exception as exc:
        raise PDFSecurityError(
            "AES-256 protection failed; no unrestricted fallback was returned"
        ) from exc
