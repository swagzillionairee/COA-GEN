"""Streamlit interface for the desktop and hosted COA Generator."""

from __future__ import annotations

import hashlib
import hmac
import io
import os
from datetime import datetime

import streamlit as st
from pydantic import ValidationError

from coa.batch import generate_batch_archive, validate_batch_upload
from coa.calculations import build_analytical_result
from coa.image_processing import ImageValidationError, process_image_upload
from coa.instrument_metadata import (
    derive_data_file_name,
    derive_instrument_sample_identifier,
    identifier_warnings,
    randomized_acquisition_time,
)
from coa.lifecycle import (
    clear_cache_and_history,
    recent_report_numbers,
    record_recent_export,
    request_application_exit,
)
from coa.models import COAConfig, PortableImage
from coa.numbering import reserve_report_numbers
from coa.pdf_generator import PDFGenerationResult, generate_pdf
from coa.pdf_security import PDFSecurityError
from coa.scenarios import ScenarioError, load_scenario_json, scenario_json
from coa.templates import (
    BUILTIN_TEMPLATE_NAME,
    TemplateError,
    list_template_names,
    load_template,
    save_template,
)
from coa.validation import resolve_watermark_text, validate_for_export


st.set_page_config(
    page_title="COA Generator",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

WEB_MODE = os.environ.get("COA_DEPLOYMENT_MODE", "desktop").casefold() == "web"


def _configured_password() -> str | None:
    """Read an optional access password without requiring a local secrets file."""

    environment_value = os.environ.get("COA_APP_PASSWORD")
    if environment_value:
        return environment_value
    try:
        value = st.secrets["APP_PASSWORD"]
    except (FileNotFoundError, KeyError):
        return None
    return str(value) if value else None


def _require_access_password() -> None:
    configured = _configured_password()
    if not configured or st.session_state.get("coa_authenticated"):
        return
    st.title("COA Generator")
    st.caption("Enter the access password to open this hosted workspace.")
    with st.form("coa_access_form"):
        supplied = st.text_input("Access password", type="password")
        submitted = st.form_submit_button("Open generator", type="primary", width="stretch")
    if submitted:
        if hmac.compare_digest(supplied.encode("utf-8"), configured.encode("utf-8")):
            st.session_state.coa_authenticated = True
            st.rerun()
        else:
            st.error("Incorrect access password.")
    st.stop()


_require_access_password()

st.markdown(
    """
    <style>
      .stApp { background: #f5f7f8; }
      [data-testid="stSidebar"] { background: #173f4f; }
      [data-testid="stSidebar"] h1,
      [data-testid="stSidebar"] h2,
      [data-testid="stSidebar"] h3,
      [data-testid="stSidebar"] p,
      [data-testid="stSidebar"] label,
      [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #f8fafc; }
      [data-testid="stSidebar"] .stButton button,
      [data-testid="stSidebar"] .stDownloadButton button {
        background: #f8fafc !important;
        border: 1px solid #b7c5cc !important;
        color: #173f4f !important;
        font-weight: 700 !important;
      }
      [data-testid="stSidebar"] .stButton button:hover,
      [data-testid="stSidebar"] .stDownloadButton button:hover {
        background: #e8f0f3 !important;
        border-color: #d8a43b !important;
        color: #102f3b !important;
      }
      [data-testid="stSidebar"] .stButton button:disabled,
      [data-testid="stSidebar"] .stDownloadButton button:disabled {
        background: #d9e1e5 !important;
        color: #4b606a !important;
        opacity: 1 !important;
      }
      [data-testid="stSidebar"] .stButton button *,
      [data-testid="stSidebar"] .stDownloadButton button * { color: inherit !important; }
      [data-testid="stSidebar"] [data-baseweb="select"] > div,
      [data-testid="stSidebar"] input,
      [data-testid="stSidebar"] textarea {
        background: #ffffff !important;
        color: #17242b !important;
        -webkit-text-fill-color: #17242b !important;
      }
      [data-testid="stSidebar"] [data-baseweb="select"] * { color: #17242b !important; }
      [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p { color: #f8fafc !important; }
      .coa-guardrail { border-left: 4px solid #d8a43b; background: #fff8df;
                       padding: .75rem 1rem; border-radius: .35rem; }
      .coa-card { background: white; border: 1px solid #d9e1e5; border-radius: .6rem;
                  padding: 1rem; margin-bottom: .8rem; }
      .small-muted { color: #52616b; font-size: .84rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _revision_key(name: str) -> str:
    return f"{name}_{st.session_state.get('config_revision', 0)}"


def _replace_config(config: COAConfig) -> None:
    st.session_state.config = config
    st.session_state.config_revision = st.session_state.get("config_revision", 0) + 1
    for key in (
        "preview_pdf",
        "preview_png",
        "preview_digest",
        "standard_export",
        "protected_export",
        "batch_archive",
    ):
        st.session_state.pop(key, None)


def _config_digest(config: COAConfig) -> str:
    return hashlib.sha256(scenario_json(config, indent=0)).hexdigest()


def _batch_digest(
    content: bytes,
    filename: str,
    config: COAConfig,
    partial_success: bool,
) -> str:
    digest = hashlib.sha256()
    digest.update(content)
    digest.update(b"\0")
    digest.update(filename.casefold().encode("utf-8"))
    digest.update(b"\0")
    digest.update(scenario_json(config, indent=0))
    digest.update(b"\0partial=" + str(partial_success).encode("ascii"))
    return digest.hexdigest()


def _select_index(options: list[str], value: str) -> int:
    try:
        return options.index(value)
    except ValueError:
        return 0


def _parse_float_list(value: str) -> list[float]:
    if not value.strip():
        return []
    return [float(item.strip()) for item in value.replace(",", ";").split(";") if item.strip()]


def _processed_upload(
    uploaded,
    current: PortableImage | None,
    purpose: str,
    *,
    caption: str | None = None,
    crop_position: str = "center",
) -> PortableImage | None:
    if uploaded is None:
        return current
    content = uploaded.getvalue()
    source_digest = hashlib.sha256(content).hexdigest()
    cache_key = f"upload_cache_{purpose}"
    cached = st.session_state.get(cache_key)
    if cached and cached.get("source_digest") == source_digest:
        image = PortableImage.model_validate(cached["image"])
        return image.model_copy(update={"caption": caption, "crop_position": crop_position})
    image = process_image_upload(
        content,
        uploaded.name,
        purpose,  # type: ignore[arg-type]
        caption=caption,
        crop_position=crop_position,  # type: ignore[arg-type]
    )
    st.session_state[cache_key] = {
        "source_digest": source_digest,
        "image": image.model_dump(mode="json"),
    }
    return image


def _render_preview(pdf_bytes: bytes) -> bytes | None:
    try:
        import fitz

        document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = document.load_page(0)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(1.55, 1.55), alpha=False)
        payload = pixmap.tobytes("png")
        document.close()
        return payload
    except Exception:
        return None


if "config" not in st.session_state:
    st.session_state.config = load_template(BUILTIN_TEMPLATE_NAME)
    st.session_state.config_revision = 0

current: COAConfig = st.session_state.config
draft = current.model_dump(mode="python")

with st.sidebar:
    st.markdown("## COA Generator")
    st.caption("Hosted web edition" if WEB_MODE else "Offline report workstation")
    if WEB_MODE:
        st.caption(
            "PDFs and uploaded images are processed in memory. Download anything you want to keep."
        )
        if _configured_password() and st.button("Sign out", width="stretch"):
            st.session_state.pop("coa_authenticated", None)
            st.rerun()
    if template_message := st.session_state.pop("template_message", None):
        st.success(template_message)
    st.markdown("### Templates")
    available_templates = list_template_names()
    selected_template = st.selectbox(
        "Template",
        available_templates,
        index=0,
        key="selected_template",
        help="Apply a built-in or locally saved set of reusable report values.",
    )
    if st.button("Apply selected template", width="stretch"):
        try:
            _replace_config(load_template(selected_template))
            st.session_state.template_message = f"Applied {selected_template}."
            st.rerun()
        except TemplateError as exc:
            st.error(str(exc))
    template_name = st.text_input(
        "Save current values as",
        placeholder="e.g. Vitum Lab - Retatrutide",
        key="new_template_name",
    )
    if st.button("Save current as template", width="stretch", disabled=not template_name.strip()):
        try:
            saved_name = save_template(template_name, current)
            st.session_state.template_message = f"Saved {saved_name}."
            st.rerun()
        except TemplateError as exc:
            st.error(str(exc))
    st.markdown("---")
    preset_options = ["Reference COA", "Reference COA with Sample Image"]
    draft["template"]["preset"] = st.selectbox(
        "PDF layout",
        preset_options,
        index=_select_index(preset_options, current.template.preset),
        key=_revision_key("preset"),
    )
    strict = st.toggle(
        "Strict identifier matching",
        value=current.strict_identifier_matching,
        key=_revision_key("strict_matching"),
        help="Reject detectable sample, lot, data-file, and instrument-ID mismatches.",
    )
    draft["strict_identifier_matching"] = strict
    st.markdown("---")
    if st.button("Reserve next report number", width="stretch"):
        try:
            draft["report_no"] = reserve_report_numbers(
                1, existing_numbers=recent_report_numbers()
            )[0]
            _replace_config(COAConfig.model_validate(draft))
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if not WEB_MODE:
        if st.button("Clear caches and recent history", width="stretch"):
            clear_cache_and_history()
            st.success("Caches and recent-file history cleared. Reports and scenarios were not touched.")
        if st.button("Exit application", width="stretch"):
            request_application_exit()
            st.info("Exit requested. This browser tab can be closed.")

st.title("Certificate of Analysis Generator")
st.markdown(
    '<div class="coa-guardrail"><strong>Release check</strong> — Verify analytical values against '
    "the original instrument source data before issuing a report. Branding and signature assets "
    "must be yours or authorized for use.</div>",
    unsafe_allow_html=True,
)

left, right = st.columns([1.05, 0.95], gap="large")

with left:
    with st.expander("1. Branding", expanded=True):
        brand = draft["branding"]
        brand["organization_display_name"] = st.text_input(
            "Organization display name *", current.branding.organization_display_name, key=_revision_key("org")
        )
        brand["address"] = st.text_input("Address", current.branding.address, key=_revision_key("address"))
        contact_a, contact_b = st.columns(2)
        brand["website"] = contact_a.text_input("Website", current.branding.website, key=_revision_key("website"))
        brand["email"] = contact_b.text_input("Email", current.branding.email, key=_revision_key("email"))
        brand["phone"] = st.text_input("Phone", current.branding.phone, key=_revision_key("phone"))
        color_cols = st.columns(4)
        brand["primary_color"] = color_cols[0].color_picker(
            "Primary", current.branding.primary_color, key=_revision_key("primary_color")
        )
        brand["accent_color"] = color_cols[1].color_picker(
            "Accent", current.branding.accent_color, key=_revision_key("accent_color")
        )
        brand["title_color"] = color_cols[2].color_picker(
            "Title", current.branding.title_color, key=_revision_key("title_color")
        )
        brand["purity_highlight_color"] = color_cols[3].color_picker(
            "Purity highlight", current.branding.purity_highlight_color, key=_revision_key("highlight_color")
        )
        chart_colors = st.columns(2)
        brand["trace_color"] = chart_colors[0].color_picker(
            "Chromatogram trace", current.branding.trace_color, key=_revision_key("trace_color")
        )
        brand["peak_fill_color"] = chart_colors[1].color_picker(
            "Peak fill", current.branding.peak_fill_color, key=_revision_key("peak_color")
        )
        font_options = ["DejaVu Sans", "DejaVu Serif"]
        fonts = st.columns(3)
        brand["title_font"] = fonts[0].selectbox(
            "Title font", font_options, _select_index(font_options, current.branding.title_font), key=_revision_key("title_font")
        )
        brand["body_font"] = fonts[1].selectbox(
            "Body font", font_options, _select_index(font_options, current.branding.body_font), key=_revision_key("body_font")
        )
        brand["table_font"] = fonts[2].selectbox(
            "Table font", font_options, _select_index(font_options, current.branding.table_font), key=_revision_key("table_font")
        )
        underline_options = ["none", "single", "double"]
        brand["certificate_underline"] = st.selectbox(
            "Certificate-title underline",
            underline_options,
            _select_index(underline_options, current.branding.certificate_underline),
            key=_revision_key("certificate_underline"),
        )
        logo_upload = st.file_uploader(
            "Optional authorized logo (PNG, JPEG, or WebP; 10 MB maximum)",
            type=["png", "jpg", "jpeg", "webp"],
            key=_revision_key("logo_upload"),
        )
        remove_logo = st.button("Remove logo", key=_revision_key("remove_logo"))
        if remove_logo:
            updated = current.model_copy(deep=True)
            updated.branding.logo = None
            updated.branding.logo_use_authorized = False
            st.session_state.pop("upload_cache_logo", None)
            _replace_config(updated)
            st.rerun()
        try:
            logo = _processed_upload(logo_upload, current.branding.logo, "logo")
            brand["logo"] = logo.model_dump(mode="python") if logo else None
            logo_still_same = bool(
                logo
                and current.branding.logo
                and logo.sha256 == current.branding.logo.sha256
            )
            brand["logo_use_authorized"] = st.checkbox(
                "I own this logo or am authorized to use it",
                value=current.branding.logo_use_authorized if logo_still_same else False,
                disabled=logo is None,
                key=_revision_key("logo_auth"),
            )
            if logo and brand["logo_use_authorized"]:
                st.image(logo.bytes(), caption=logo.filename, width=210)
            elif logo:
                st.info("Logo preview is withheld until authorization is confirmed.")
        except ImageValidationError as exc:
            st.error(str(exc))
        brand["footer_disclaimer"] = st.text_area(
            "Footer disclaimer *", current.branding.footer_disclaimer, height=110, key=_revision_key("footer_disclaimer")
        )

    with st.expander("2. Report information", expanded=True):
        report_cols = st.columns(2)
        draft["report_no"] = report_cols[0].text_input("Report number *", current.report_no, key=_revision_key("report_no"))
        draft["client"] = report_cols[1].text_input("Client *", current.client, key=_revision_key("client"))
        dates_a = st.columns(2)
        draft["receipt_date"] = dates_a[0].date_input("Receipt date *", current.receipt_date, key=_revision_key("receipt_date"))
        draft["analysis_date"] = dates_a[1].date_input("Analysis date *", current.analysis_date, key=_revision_key("analysis_date"))
        dates_b = st.columns(2)
        draft["report_date"] = dates_b[0].date_input("Report date *", current.report_date, key=_revision_key("report_date"))
        draft["document_issue_date"] = dates_b[1].date_input(
            "Document issue date *", current.document_issue_date, key=_revision_key("issue_date")
        )
        template = draft["template"]
        format_cols = st.columns(3)
        header_formats = ["%b. %d, %Y", "%B %d, %Y", "%m/%d/%Y"]
        body_formats = ["%m/%d/%Y", "%Y-%m-%d", "%b %d, %Y"]
        page_formats = ["1", "1 of 1"]
        template["header_date_format"] = format_cols[0].selectbox(
            "Header date format",
            header_formats,
            _select_index(header_formats, current.template.header_date_format),
            key=_revision_key("header_date_format"),
        )
        template["body_date_format"] = format_cols[1].selectbox(
            "Body date format",
            body_formats,
            _select_index(body_formats, current.template.body_date_format),
            key=_revision_key("body_date_format"),
        )
        template["page_number_format"] = format_cols[2].selectbox(
            "Page-number format",
            page_formats,
            _select_index(page_formats, current.template.page_number_format),
            key=_revision_key("page_format"),
        )

    with st.expander("3. Sample information", expanded=True):
        sample_cols = st.columns(2)
        draft["sample_name"] = sample_cols[0].text_input("Sample name *", current.sample_name, key=_revision_key("sample_name"))
        draft["strength_or_presentation"] = sample_cols[1].text_input(
            "Strength / presentation", current.strength_or_presentation or "", key=_revision_key("strength")
        ) or None
        sample_cols_2 = st.columns(2)
        draft["batch_no"] = sample_cols_2[0].text_input("Batch or lot", current.batch_no or "", key=_revision_key("batch_no")) or None
        draft["number_of_samples"] = sample_cols_2[1].number_input(
            "Number of samples *", min_value=1, max_value=10000, value=current.number_of_samples, step=1, key=_revision_key("sample_count")
        )
        sample_cols_3 = st.columns(2)
        draft["test"] = sample_cols_3[0].text_input("Test *", current.test, key=_revision_key("test"))
        draft["matrix"] = sample_cols_3[1].text_input("Matrix *", current.matrix, key=_revision_key("matrix"))
        draft["notes"] = st.text_area("Optional notes", current.notes or "", key=_revision_key("notes")) or None
        label_cols = st.columns(2)
        draft["template"]["sample_label"] = label_cols[0].text_input(
            "Sample field label", current.template.sample_label, key=_revision_key("sample_label")
        )
        draft["template"]["batch_label"] = label_cols[1].text_input(
            "Batch / lot field label", current.template.batch_label, key=_revision_key("batch_label")
        )
        draft["template"]["append_strength_to_sample"] = st.toggle(
            "Append strength to the displayed sample-name row",
            current.template.append_strength_to_sample,
            key=_revision_key("append_strength"),
        )
        basis_cols = st.columns(2)
        draft["purity_basis_description"] = basis_cols[0].text_input(
            "Purity basis", current.purity_basis_description or "", key=_revision_key("purity_basis")
        ) or None
        draft["excluded_component_text"] = basis_cols[1].text_input(
            "Excluded components", current.excluded_component_text or "", key=_revision_key("excluded_components")
        ) or None

    with st.expander("4. Submitted-sample image"):
        sample_image = current.sample_image
        caption = st.text_input(
            "Image caption", sample_image.caption if sample_image and sample_image.caption else "", key=_revision_key("sample_caption")
        )
        crop_options = ["center", "top", "bottom", "left", "right"]
        crop = st.selectbox(
            "Crop position",
            crop_options,
            _select_index(crop_options, sample_image.crop_position if sample_image else "center"),
            key=_revision_key("sample_crop"),
        )
        sample_upload = st.file_uploader(
            "Sample image (PNG, JPEG, or WebP)", type=["png", "jpg", "jpeg", "webp"], key=_revision_key("sample_upload")
        )
        remove_sample = st.button("Remove sample image", key=_revision_key("remove_sample"))
        if remove_sample:
            updated = current.model_copy(deep=True)
            updated.template.preset = "Reference COA"
            updated.sample_image = None
            st.session_state.pop("upload_cache_sample", None)
            _replace_config(updated)
            st.rerun()
        try:
            image = _processed_upload(
                sample_upload, sample_image, "sample", caption=caption or None, crop_position=crop
            )
            if image and sample_upload is None:
                image = image.model_copy(update={"caption": caption or None, "crop_position": crop})
            draft["sample_image"] = image.model_dump(mode="python") if image else None
            if image:
                st.image(image.bytes(), caption=image.caption or image.filename, width=280)
            else:
                st.info("No sample image selected. The exported PDF will omit the sample-image panel.")
        except ImageValidationError as exc:
            st.error(str(exc))

    with st.expander("5. Analytical-result settings", expanded=True):
        analytical = draft["analytical"]
        result_cols = st.columns(3)
        analytical["purity_percent"] = result_cols[0].number_input(
            "Requested purity % *", 0.0, 100.0, float(current.analytical.purity_percent), 0.1, key=_revision_key("purity")
        )
        analytical["purity_display_decimals"] = result_cols[1].selectbox(
            "Purity decimals", [1, 2, 3], [1, 2, 3].index(current.analytical.purity_display_decimals), key=_revision_key("purity_decimals")
        )
        analytical["random_seed"] = result_cols[2].number_input(
            "Random seed *", 0, 2_147_483_647, current.analytical.random_seed, 1, key=_revision_key("seed")
        )
        times = st.columns(3)
        analytical["retention_time_start"] = times[0].number_input(
            "Run start (min)", value=float(current.analytical.retention_time_start), step=0.1, key=_revision_key("rt_start")
        )
        analytical["retention_time_end"] = times[1].number_input(
            "Run end (min)", value=float(current.analytical.retention_time_end), step=0.1, key=_revision_key("rt_end")
        )
        analytical["main_peak_time"] = times[2].number_input(
            "Main peak time", value=float(current.analytical.main_peak_time), step=0.001, format="%.3f", key=_revision_key("main_time")
        )
        secondary_text = st.text_input(
            "Secondary peak times (semicolon separated)",
            "; ".join(f"{value:g}" for value in current.analytical.secondary_peak_times),
            key=_revision_key("secondary_times"),
        )
        secondary_areas_text = st.text_input(
            "Optional secondary % areas (must total 100 minus purity)",
            "" if current.analytical.secondary_peak_percent_areas is None else "; ".join(
                f"{value:g}" for value in current.analytical.secondary_peak_percent_areas
            ),
            key=_revision_key("secondary_areas"),
        )
        try:
            analytical["secondary_peak_times"] = _parse_float_list(secondary_text)
            analytical["secondary_peak_percent_areas"] = (
                _parse_float_list(secondary_areas_text) if secondary_areas_text.strip() else None
            )
        except ValueError:
            st.error("Peak lists must contain numbers separated by semicolons.")
        sim_cols = st.columns(3)
        analytical["baseline_noise"] = sim_cols[0].number_input(
            "Baseline noise", 0.0, 0.25, float(current.analytical.baseline_noise), 0.001, format="%.3f", key=_revision_key("noise")
        )
        analytical["baseline_level"] = sim_cols[1].number_input(
            "Baseline level", -1.0, 1.0, float(current.analytical.baseline_level), 0.01, key=_revision_key("baseline")
        )
        analytical["baseline_drift"] = sim_cols[2].number_input(
            "Baseline drift", -0.25, 0.25, float(current.analytical.baseline_drift), 0.01, key=_revision_key("drift")
        )
        analytical["injection_disturbance"] = st.toggle(
            "Show injection / solvent-front disturbance (excluded from peak math)",
            current.analytical.injection_disturbance,
            key=_revision_key("disturbance"),
        )
        analytical["absolute_area_scale"] = st.number_input(
            "Absolute peak-list area scale", min_value=1.0, value=float(current.analytical.absolute_area_scale), step=1000.0, key=_revision_key("area_scale")
        )
        peak_shape_cols = st.columns(4)
        analytical["default_peak_width"] = peak_shape_cols[0].number_input(
            "Peak width",
            0.001,
            2.0,
            float(current.analytical.default_peak_width),
            0.005,
            format="%.3f",
            key=_revision_key("peak_width"),
        )
        analytical["tailing"] = peak_shape_cols[1].number_input(
            "Tailing",
            0.0,
            5.0,
            float(current.analytical.tailing),
            0.05,
            key=_revision_key("tailing"),
        )
        analytical["chart_label_threshold_percent"] = peak_shape_cols[2].number_input(
            "Label threshold %",
            0.0,
            100.0,
            float(current.analytical.chart_label_threshold_percent),
            0.05,
            key=_revision_key("label_threshold"),
        )
        analytical["injection_disturbance_amplitude"] = peak_shape_cols[3].number_input(
            "Front amplitude",
            -1.0,
            1.0,
            float(current.analytical.injection_disturbance_amplitude),
            0.01,
            key=_revision_key("front_amplitude"),
        )
        precision_cols = st.columns(3)
        percent_precision_options = [1, 2, 3, 4]
        raw_precision_options = [0, 1, 2, 3, 4, 5, 6]
        rt_precision_options = [1, 2, 3, 4, 5]
        analytical["percent_area_decimals"] = precision_cols[0].selectbox(
            "%Area decimals",
            percent_precision_options,
            percent_precision_options.index(current.analytical.percent_area_decimals),
            key=_revision_key("percent_area_decimals"),
        )
        analytical["raw_area_decimals"] = precision_cols[1].selectbox(
            "Raw-area decimals",
            raw_precision_options,
            raw_precision_options.index(current.analytical.raw_area_decimals),
            key=_revision_key("raw_area_decimals"),
        )
        analytical["retention_time_decimals"] = precision_cols[2].selectbox(
            "Retention-time decimals",
            rt_precision_options,
            rt_precision_options.index(current.analytical.retention_time_decimals),
            key=_revision_key("rt_decimals"),
        )
        manual_mode = st.toggle(
            "Use manual analytical peak rows",
            value=bool(current.analytical.manual_peaks),
            key=_revision_key("manual_peak_mode"),
            help="Manual areas must produce the requested purity within 0.000001.",
        )
        if manual_mode:
            import pandas as pd

            if current.analytical.manual_peaks:
                manual_rows = [peak.model_dump() for peak in current.analytical.manual_peaks]
            else:
                automatic = build_analytical_result(current.analytical)
                manual_rows = [
                    {
                        "retention_time": peak.retention_time,
                        "area": peak.area,
                        "width": peak.width,
                        "tailing": peak.tailing,
                        "is_main": peak.is_main,
                        "include_in_table": peak.include_in_table,
                        "annotate": peak.annotate,
                        "annotation_prefix": peak.annotation_prefix,
                        "marker": peak.marker or "",
                    }
                    for peak in automatic.peaks
                ]
            edited_peaks = st.data_editor(
                pd.DataFrame(manual_rows),
                num_rows="dynamic",
                width="stretch",
                key=_revision_key("manual_peak_editor"),
            )
            parsed_manual: list[dict[str, object]] = []
            for row in edited_peaks.to_dict(orient="records"):
                if pd.isna(row.get("retention_time")) or pd.isna(row.get("area")):
                    continue
                prefix = row.get("annotation_prefix")
                marker_value = row.get("marker")
                width_value = row.get("width")
                tailing_value = row.get("tailing")
                parsed_manual.append(
                    {
                        "retention_time": float(row["retention_time"]),
                        "area": float(row["area"]),
                        "width": float(
                            current.analytical.default_peak_width
                            if pd.isna(width_value)
                            else width_value
                        ),
                        "tailing": float(0 if pd.isna(tailing_value) else tailing_value),
                        "is_main": bool(row.get("is_main", False)),
                        "include_in_table": bool(row.get("include_in_table", True)),
                        "annotate": bool(row.get("annotate", True)),
                        "annotation_prefix": "" if pd.isna(prefix) else str(prefix),
                        "marker": None if pd.isna(marker_value) or not str(marker_value) else str(marker_value),
                    }
                )
            analytical["manual_peaks"] = parsed_manual
        else:
            analytical["manual_peaks"] = []
        qualifier_cols = st.columns(2)
        draft["purity_qualifier"] = qualifier_cols[0].text_input(
            "Purity qualifier", current.purity_qualifier or "", key=_revision_key("qualifier")
        ) or None
        draft["result_note_marker"] = qualifier_cols[1].text_input(
            "Result-note marker", current.result_note_marker or "", max_chars=4, key=_revision_key("note_marker")
        ) or None
        draft["result_note"] = st.text_area(
            "Result footnote", current.result_note or "", key=_revision_key("result_note")
        ) or None

    with st.expander("6. Instrument and acquisition metadata"):
        instrument = draft["instrument_metadata"]
        inst_cols = st.columns(2)
        instrument["data_file"] = inst_cols[0].text_input("Data-file display name *", current.instrument_metadata.data_file, key=_revision_key("data_file"))
        instrument["instrument_sample_name"] = inst_cols[1].text_input(
            "Instrument sample identifier *", current.instrument_metadata.instrument_sample_name, key=_revision_key("instrument_sample")
        )
        inst_cols_2 = st.columns(2)
        instrument["instrument"] = inst_cols_2[0].text_input("Instrument name", current.instrument_metadata.instrument, key=_revision_key("instrument"))
        instrument["operator"] = inst_cols_2[1].text_input("Operator / system identity", current.instrument_metadata.operator, key=_revision_key("operator"))
        status_cols = st.columns(2)
        instrument["sample_type"] = status_cols[0].text_input(
            "Instrument sample type", current.instrument_metadata.sample_type, key=_revision_key("sample_type")
        )
        instrument["calibration_status"] = status_cols[1].text_input(
            "Calibration / readiness status",
            current.instrument_metadata.calibration_status,
            key=_revision_key("calibration_status"),
        )
        methods = st.columns(2)
        instrument["acquisition_method"] = methods[0].text_input("Acquisition method", current.instrument_metadata.acquisition_method, key=_revision_key("acq_method"))
        instrument["analysis_method"] = methods[1].text_input("Analysis method", current.instrument_metadata.analysis_method, key=_revision_key("analysis_method"))
        metadata_cols = st.columns(3)
        instrument["position"] = metadata_cols[0].text_input("Position", current.instrument_metadata.position, key=_revision_key("position"))
        instrument["sample_group"] = metadata_cols[1].text_input("Sample group", current.instrument_metadata.sample_group, key=_revision_key("sample_group"))
        instrument["stream_name"] = metadata_cols[2].text_input("Stream / channel", current.instrument_metadata.stream_name, key=_revision_key("stream"))
        instrument["software_version"] = st.text_input(
            "Acquisition SW version",
            current.instrument_metadata.software_version,
            key=_revision_key("acquisition_sw_version"),
        )
        optional_metadata = st.columns(2)
        instrument["comment"] = optional_metadata[0].text_input(
            "Optional instrument comment", current.instrument_metadata.comment or "", key=_revision_key("instrument_comment")
        ) or None
        instrument["information"] = optional_metadata[1].text_input(
            "Optional information value", current.instrument_metadata.information or "", key=_revision_key("instrument_information")
        ) or None
        custom_rows_text = st.text_area(
            "Additional visible metadata rows (one Label=Value per line; maximum 8)",
            "\n".join(f"{row.label}={row.value}" for row in current.instrument_metadata.custom_rows),
            key=_revision_key("custom_metadata_rows"),
        )
        try:
            parsed_custom_rows = []
            for line_number, line in enumerate(custom_rows_text.splitlines(), start=1):
                if not line.strip():
                    continue
                if "=" not in line:
                    raise ValueError(f"Custom row {line_number} must contain '='")
                label, value = line.split("=", 1)
                parsed_custom_rows.append({"label": label.strip(), "value": value.strip(), "visible": True})
            instrument["custom_rows"] = parsed_custom_rows
        except ValueError as exc:
            st.error(str(exc))
        target_analysis_date = draft["analysis_date"]
        current_acquired = current.instrument_metadata.acquired_at
        if current_acquired.date() != target_analysis_date:
            timezone_info = current_acquired.tzinfo
            if timezone_info is not None:
                instrument["acquired_at"] = randomized_acquisition_time(
                    target_analysis_date,
                    timezone_info,
                )
        acquired_display = instrument["acquired_at"]
        if isinstance(acquired_display, datetime):
            st.caption(
                "Acquired time is automatically set to the analysis date at a random time "
                f"between 1:00 PM and 5:00 PM: {acquired_display.strftime('%m/%d/%Y %I:%M:%S %p')}"
            )
        st.markdown("**Detector and channel**")
        detector = draft["detector"]
        detector_cols = st.columns(4)
        detector["trace_name"] = detector_cols[0].text_input(
            "Trace", current.detector.trace_name, key=_revision_key("trace_name")
        )
        detector["channel"] = detector_cols[1].text_input(
            "Channel", current.detector.channel, key=_revision_key("detector_channel")
        )
        detector["signal_wavelength_nm"] = detector_cols[2].number_input(
            "Signal nm", 100, 2000, current.detector.signal_wavelength_nm, 1, key=_revision_key("signal_nm")
        )
        detector["signal_bandwidth_nm"] = detector_cols[3].number_input(
            "Bandwidth nm", 0, 1000, current.detector.signal_bandwidth_nm, 1, key=_revision_key("signal_bandwidth")
        )
        detector["reference_enabled"] = st.toggle(
            "Reference wavelength enabled", current.detector.reference_enabled, key=_revision_key("reference_enabled")
        )
        reference_cols = st.columns(3)
        detector["reference_wavelength_nm"] = reference_cols[0].number_input(
            "Reference nm",
            100,
            2000,
            current.detector.reference_wavelength_nm or 400,
            1,
            disabled=not detector["reference_enabled"],
            key=_revision_key("reference_nm"),
        )
        detector["reference_bandwidth_nm"] = reference_cols[1].number_input(
            "Reference bandwidth",
            0,
            1000,
            current.detector.reference_bandwidth_nm or 100,
            1,
            disabled=not detector["reference_enabled"],
            key=_revision_key("reference_bandwidth"),
        )
        detector["processing_label"] = reference_cols[2].text_input(
            "Processing operation", current.detector.processing_label or "", key=_revision_key("detector_processing")
        ) or None
        if st.button("Derive canonical instrument identifiers", key=_revision_key("derive_ids")):
            instrument["instrument_sample_name"] = derive_instrument_sample_identifier(
                draft["sample_name"], draft["batch_no"], draft["test"]
            )
            instrument["data_file"] = derive_data_file_name(
                draft["sample_name"], draft["batch_no"], draft["analysis_date"], draft["test"]
            )
            try:
                _replace_config(COAConfig.model_validate(draft))
                st.rerun()
            except ValidationError as exc:
                st.error(str(exc))

    with st.expander("7. Chromatogram settings"):
        chart = draft["chromatogram"]
        chart_cols = st.columns(3)
        chart["show_peak_fill"] = chart_cols[0].toggle("Fill integrated peaks", current.chromatogram.show_peak_fill, key=_revision_key("peak_fill"))
        chart["show_detector_descriptor"] = chart_cols[1].toggle(
            "Detector descriptor", current.chromatogram.show_detector_descriptor, key=_revision_key("detector_descriptor")
        )
        chart["show_processing_label"] = chart_cols[2].toggle(
            "Processing label", current.chromatogram.show_processing_label, key=_revision_key("processing_label")
        )
        chart["response_units"] = st.text_input("Y-axis response units", current.chromatogram.response_units, key=_revision_key("response_units"))
        chart["x_major_tick_interval"] = st.number_input(
            "X-axis major tick interval", 0.1, 10.0, float(current.chromatogram.x_major_tick_interval), 0.1, key=_revision_key("tick_interval")
        )
        axis_cols = st.columns(3)
        axis_modes = ["auto", "fixed"]
        chart["y_axis_mode"] = axis_cols[0].selectbox(
            "Y-axis range",
            axis_modes,
            _select_index(axis_modes, current.chromatogram.y_axis_mode),
            key=_revision_key("y_axis_mode"),
        )
        fixed_axis = chart["y_axis_mode"] == "fixed"
        chart["y_axis_min"] = axis_cols[1].number_input(
            "Y minimum",
            value=float(current.chromatogram.y_axis_min if current.chromatogram.y_axis_min is not None else -0.1),
            step=0.1,
            disabled=not fixed_axis,
            key=_revision_key("y_axis_min"),
        ) if fixed_axis else None
        chart["y_axis_max"] = axis_cols[2].number_input(
            "Y maximum",
            value=float(current.chromatogram.y_axis_max if current.chromatogram.y_axis_max is not None else 1.2),
            step=0.1,
            disabled=not fixed_axis,
            key=_revision_key("y_axis_max"),
        ) if fixed_axis else None
        render_cols = st.columns(2)
        scale_text = render_cols[0].text_input(
            "Optional y-axis multiplier",
            "" if current.chromatogram.y_axis_scale_multiplier is None else f"{current.chromatogram.y_axis_scale_multiplier:g}",
            key=_revision_key("y_axis_multiplier"),
        )
        try:
            chart["y_axis_scale_multiplier"] = float(scale_text) if scale_text.strip() else None
        except ValueError:
            st.error("Y-axis multiplier must be a positive number or blank.")
        chart["dpi"] = render_cols[1].slider(
            "Chart DPI", 150, 400, current.chromatogram.dpi, 10, key=_revision_key("chart_dpi")
        )

    with st.expander("8. Approval block"):
        approval = draft["approval"]
        approval["heading"] = st.text_input(
            "Approval heading", current.approval.heading, key=_revision_key("approval_heading")
        )
        approval_cols = st.columns(2)
        approval["approver"] = approval_cols[0].text_input("Approver display name *", current.approval.approver, key=_revision_key("approver"))
        approval["approver_title"] = approval_cols[1].text_input("Role / title *", current.approval.approver_title, key=_revision_key("approver_title"))
        approval["approval_date"] = st.date_input("Approval date", current.approval.approval_date, key=_revision_key("approval_date"))
        approval["approval_mark"] = st.text_input("Generated non-personal approval mark", current.approval.approval_mark, key=_revision_key("approval_mark"))
        approval["show_rule"] = st.toggle(
            "Show approval rule", current.approval.show_rule, key=_revision_key("approval_rule")
        )
        signature_upload = st.file_uploader(
            "Optional authorized signature image (PNG only)", type=["png"], key=_revision_key("signature_upload")
        )
        remove_signature = st.button("Remove signature image", key=_revision_key("remove_signature"))
        if remove_signature:
            updated = current.model_copy(deep=True)
            updated.approval.signature_image = None
            updated.approval.signature_image_use_authorized = False
            st.session_state.pop("upload_cache_signature", None)
            _replace_config(updated)
            st.rerun()
        try:
            signature = _processed_upload(
                signature_upload, current.approval.signature_image, "signature"
            )
            approval["signature_image"] = signature.model_dump(mode="python") if signature else None
            signature_still_same = bool(
                signature
                and current.approval.signature_image
                and signature.sha256 == current.approval.signature_image.sha256
            )
            approval["signature_image_use_authorized"] = st.checkbox(
                "I own this signature or have the signer's authorization",
                value=current.approval.signature_image_use_authorized if signature_still_same else False,
                disabled=signature is None,
                key=_revision_key("signature_auth"),
            )
            if signature and approval["signature_image_use_authorized"]:
                st.image(signature.bytes(), caption=signature.filename, width=260)
            elif signature:
                st.info("Preview is withheld until authorization is confirmed.")
        except ImageValidationError as exc:
            st.error(str(exc))
        st.caption("This block is presentational only; it is not an electronic or digital signature.")

    with st.expander("9. Document watermark and protection", expanded=True):
        protection = draft["document_protection"]
        watermark = protection["watermark"]
        watermark["enabled"] = st.toggle("Enable custom text watermark", current.document_protection.watermark.enabled, key=_revision_key("watermark_enabled"))
        watermark["text"] = st.text_input(
            "Watermark text",
            current.document_protection.watermark.text,
            max_chars=200,
            disabled=not watermark["enabled"],
            key=_revision_key("watermark_text"),
            help="Variables: {client}, {report_no}, {sample_name}, {document_issue_date}",
        )
        watermark_style = st.columns(3)
        watermark_fonts = ["DejaVu Sans", "DejaVu Serif"]
        placements = ["center", "upper", "lower"]
        watermark["font"] = watermark_style[0].selectbox(
            "Watermark font",
            watermark_fonts,
            _select_index(watermark_fonts, current.document_protection.watermark.font),
            disabled=not watermark["enabled"],
            key=_revision_key("wm_font"),
        )
        watermark["color"] = watermark_style[1].color_picker(
            "Watermark color",
            current.document_protection.watermark.color,
            disabled=not watermark["enabled"],
            key=_revision_key("wm_color"),
        )
        watermark["placement"] = watermark_style[2].selectbox(
            "Single-mark placement",
            placements,
            _select_index(placements, current.document_protection.watermark.placement),
            disabled=not watermark["enabled"],
            key=_revision_key("wm_placement"),
        )
        wm_cols = st.columns(4)
        watermark["size"] = wm_cols[0].number_input(
            "Size", 14.0, 54.0, float(current.document_protection.watermark.size), 1.0, disabled=not watermark["enabled"], key=_revision_key("wm_size")
        )
        watermark["opacity"] = wm_cols[1].number_input(
            "Opacity", 0.05, 0.22, float(current.document_protection.watermark.opacity), 0.01, disabled=not watermark["enabled"], key=_revision_key("wm_opacity")
        )
        watermark["rotation_degrees"] = wm_cols[2].number_input(
            "Rotation", -60.0, 60.0, float(current.document_protection.watermark.rotation_degrees), 1.0, disabled=not watermark["enabled"], key=_revision_key("wm_rotation")
        )
        watermark["repeat"] = wm_cols[3].toggle(
            "Repeat", current.document_protection.watermark.repeat, disabled=not watermark["enabled"], key=_revision_key("wm_repeat")
        )
        restriction = protection["editing_restriction"]
        restriction["enabled"] = st.toggle(
            "Restrict editing in PDF editors",
            current.document_protection.editing_restriction.enabled,
            key=_revision_key("restriction_enabled"),
        )
        restriction["allow_printing"] = st.checkbox(
            "Allow high-quality printing",
            current.document_protection.editing_restriction.allow_printing,
            disabled=not restriction["enabled"],
            key=_revision_key("allow_printing"),
        )
        restriction["allow_copying"] = st.checkbox(
            "Allow ordinary content copying",
            current.document_protection.editing_restriction.allow_copying,
            disabled=not restriction["enabled"],
            key=_revision_key("allow_copying"),
        )
        st.caption(
            "Accessibility extraction remains enabled. PDF permissions deter casual editing in compliant "
            "software but cannot prevent screenshots, photography, copying, or modification by capable tools."
        )

candidate: COAConfig | None = None
candidate_error: str | None = None
try:
    candidate = COAConfig.model_validate(draft)
    candidate.preserved_warnings = (
        identifier_warnings(candidate) if not candidate.strict_identifier_matching else []
    )
    st.session_state.config = candidate
except ValidationError as exc:
    candidate_error = str(exc)

with right:
    st.subheader("10. Live preview")
    if candidate_error:
        st.error(candidate_error)
    elif candidate is not None:
        validation = validate_for_export(candidate)
        for issue in validation.errors:
            st.error(f"{issue.field}: {issue.message}")
        for issue in validation.warnings:
            st.warning(f"{issue.field}: {issue.message}")
        if candidate.report_no in recent_report_numbers():
            st.warning(
                f"Report number {candidate.report_no!r} appears in recent export history. "
                "Use a new number unless this duplicate is intentional."
            )
        if candidate.document_protection.watermark.enabled:
            try:
                st.info(f"Resolved watermark: {resolve_watermark_text(candidate)}")
            except ValueError as exc:
                st.error(str(exc))
        if st.button("Generate preview", type="primary", width="stretch", disabled=not validation.valid):
            try:
                generated = generate_pdf(candidate, apply_editing_restriction=False)
                st.session_state.preview_pdf = generated.pdf_bytes
                st.session_state.preview_png = _render_preview(generated.pdf_bytes)
                st.session_state.preview_digest = _config_digest(candidate)
            except Exception as exc:
                st.error(str(exc))
        digest = _config_digest(candidate)
        if st.session_state.get("preview_digest") == digest:
            if st.session_state.get("preview_png"):
                st.image(st.session_state.preview_png, width="stretch")
            else:
                st.info("Inline rendering is unavailable; download the prepared preview PDF below.")
            st.download_button(
                "Download preview PDF",
                st.session_state.preview_pdf,
                file_name=f"{candidate.report_no}-preview.pdf",
                mime="application/pdf",
                width="stretch",
            )
        else:
            st.markdown(
                '<div class="coa-card small-muted">Generate a preview to inspect the exact current PDF. '
                "Stale previews are hidden automatically.</div>",
                unsafe_allow_html=True,
            )

    st.subheader("11. Export and reusable JSON")
    scenario_upload = st.file_uploader("Load existing scenario JSON", type=["json"], key=_revision_key("scenario_upload"))
    scenario_actions = st.columns(3)
    if scenario_actions[0].button("Load JSON", disabled=scenario_upload is None, width="stretch"):
        try:
            _replace_config(load_scenario_json(scenario_upload.getvalue()))
            st.rerun()
        except ScenarioError as exc:
            st.error(str(exc))
    if scenario_actions[1].button("Duplicate", width="stretch"):
        duplicate = (candidate or current).model_copy(deep=True)
        duplicate.report_no = f"{current.report_no}-COPY"
        duplicate.audit.generation_identifier = None
        _replace_config(duplicate)
        st.rerun()
    if scenario_actions[2].button("Reset defaults", width="stretch"):
        _replace_config(load_template(BUILTIN_TEMPLATE_NAME))
        st.rerun()

    if candidate is not None:
        st.download_button(
            "Download current source JSON",
            scenario_json(candidate),
            file_name=f"{candidate.report_no}.json",
            mime="application/json",
            width="stretch",
        )
        export_validation = validate_for_export(candidate)
        if st.button(
            "Prepare standard PDF",
            width="stretch",
            disabled=not export_validation.valid,
        ):
            try:
                generated = generate_pdf(candidate, apply_editing_restriction=False)
                st.session_state.standard_export = {
                    "digest": _config_digest(candidate),
                    "result": generated,
                }
                record_recent_export(
                    generated.config.report_no,
                    generated.config.audit.generation_identifier,
                    protected=False,
                )
            except Exception as exc:
                st.error(str(exc))
        standard = st.session_state.get("standard_export")
        if standard and standard["digest"] == _config_digest(candidate):
            standard_result: PDFGenerationResult = standard["result"]
            st.download_button(
                "Download standard PDF",
                standard_result.pdf_bytes,
                file_name=f"{candidate.report_no}.pdf",
                mime="application/pdf",
                width="stretch",
            )

        if candidate.document_protection.editing_restriction.enabled:
            st.warning(
                "A forgotten owner password cannot be recovered. Permissions are honored by compliant "
                "applications such as Adobe Acrobat but are not an absolute security boundary."
            )
            with st.form("protected_export_form", clear_on_submit=True):
                owner_password = st.text_input("Owner password (12+ characters)", type="password")
                owner_confirm = st.text_input("Confirm owner password", type="password")
                open_password = st.text_input("Optional document-open password", type="password")
                protect_submit = st.form_submit_button("Prepare protected PDF", width="stretch")
                if protect_submit:
                    try:
                        protected = generate_pdf(
                            candidate,
                            apply_editing_restriction=True,
                            owner_password=owner_password,
                            owner_password_confirm=owner_confirm,
                            open_password=open_password or None,
                        )
                        st.session_state.protected_export = {
                            "digest": _config_digest(candidate),
                            "result": protected,
                        }
                        record_recent_export(
                            protected.config.report_no,
                            protected.config.audit.generation_identifier,
                            protected=True,
                        )
                    except PDFSecurityError as exc:
                        st.error(str(exc))
            protected_export = st.session_state.get("protected_export")
            if protected_export and protected_export["digest"] == _config_digest(candidate):
                protected_result: PDFGenerationResult = protected_export["result"]
                st.success("AES-256 encryption and requested permission flags passed two-parser verification.")
                st.download_button(
                    "Download protected PDF",
                    protected_result.pdf_bytes,
                    file_name=f"{candidate.report_no}-protected.pdf",
                    mime="application/pdf",
                    width="stretch",
                )

    st.markdown("#### Batch CSV / JSON")
    st.caption(
        "Upload CSV or JSON directly. For rows that reference relative logo, sample, or signature paths, "
        "upload a ZIP containing exactly one input file plus its images. Maximum 100 reports."
    )
    batch_upload = st.file_uploader("Batch input", type=["csv", "json", "zip"], key=_revision_key("batch_upload"))
    partial_success = st.checkbox("Allow partial-success batch", value=False, key=_revision_key("partial_batch"))
    if candidate is not None and st.button(
        "Validate all batch rows", disabled=batch_upload is None, width="stretch"
    ):
        batch_content = batch_upload.getvalue()
        batch_validation = validate_batch_upload(
            batch_content, batch_upload.name, candidate, partial_success=partial_success
        )
        st.session_state.batch_validation = batch_validation
        st.session_state.batch_source_digest = _batch_digest(
            batch_content, batch_upload.name, candidate, partial_success
        )
        st.session_state.pop("batch_archive", None)
    batch_validation = st.session_state.get("batch_validation")
    source_matches = (
        batch_upload is not None
        and candidate is not None
        and st.session_state.get("batch_source_digest")
        == _batch_digest(
            batch_upload.getvalue(), batch_upload.name, candidate, partial_success
        )
    )
    if batch_validation and source_matches:
        for error in batch_validation.errors:
            st.error(f"Row {error.row} · {error.field}: {error.message}")
        if batch_validation.configs:
            st.success(f"{len(batch_validation.configs)} report(s) validated and reserved for this batch.")
            restricted_batch = any(
                config.document_protection.editing_restriction.enabled
                for config in batch_validation.configs
            )
            if restricted_batch:
                st.warning("One transient owner password will protect every restricted PDF in this batch.")
                with st.form("batch_password_form", clear_on_submit=True):
                    batch_owner = st.text_input("Batch owner password", type="password")
                    batch_confirm = st.text_input("Confirm batch owner password", type="password")
                    batch_submit = st.form_submit_button("Generate protected batch ZIP", width="stretch")
                    if batch_submit:
                        try:
                            st.session_state.batch_archive = generate_batch_archive(
                                batch_validation.configs,
                                owner_password=batch_owner,
                                owner_password_confirm=batch_confirm,
                            )
                            for batch_config in batch_validation.configs:
                                record_recent_export(batch_config.report_no, None, protected=True)
                        except Exception as exc:
                            st.error(str(exc))
            elif st.button("Generate batch ZIP", width="stretch"):
                try:
                    st.session_state.batch_archive = generate_batch_archive(batch_validation.configs)
                    for batch_config in batch_validation.configs:
                        record_recent_export(batch_config.report_no, None, protected=False)
                except Exception as exc:
                    st.error(str(exc))
            if st.session_state.get("batch_archive"):
                st.download_button(
                    "Download batch ZIP",
                    st.session_state.batch_archive,
                    file_name="coa-batch.zip",
                    mime="application/zip",
                    width="stretch",
                )
