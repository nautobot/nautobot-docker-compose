from datetime import date, datetime

from nautobot.extras.plugins import TemplateExtension

try:
    from nautobot_device_lifecycle_mgmt.models import HardwareLCM, SoftwareLCM
except Exception:  # pragma: no cover - keep the plugin loadable if DLM is absent
    HardwareLCM = None
    SoftwareLCM = None


class LocationTopologyButtons(TemplateExtension):
    """Extend the DCIM location template to include content from this plugin."""

    model = "dcim.location"

    def buttons(self):
        return self.render("nautobot_ui_plugin/location_topo_button.html")


def _value_to_text(value):
    """Normalize UI values into strings for rendering."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    return text or None


def _field(label, value, url=None):
    """Build a field row for the device EOX panel."""
    return {
        "label": label,
        "value": _value_to_text(value),
        "url": _value_to_text(url),
    }


def _custom_field_value(obj, key):
    """Retrieve a custom field value from a Nautobot object."""
    if obj is None:
        return None
    custom_field_data = getattr(obj, "custom_field_data", None)
    if isinstance(custom_field_data, dict) and key in custom_field_data:
        return custom_field_data.get(key)
    cf_dict = getattr(obj, "cf", None)
    if isinstance(cf_dict, dict) and key in cf_dict:
        return cf_dict.get(key)
    return None


def _section_status(record, expired_attr="expired"):
    """Return a Bootstrap badge class and label for a lifecycle record."""
    if not record:
        return "bg-secondary", "No record"
    expired = getattr(record, expired_attr, None)
    if expired is True:
        return "bg-danger", "Expired"
    return "bg-success", "Active"


class DeviceEffectiveEOXContent(TemplateExtension):
    """Extend the device detail page with effective hardware and software EOX data."""

    model = "dcim.device"

    def _hardware_notice(self, device):
        if HardwareLCM is None or not getattr(device, "device_type_id", None):
            return None
        return (
            HardwareLCM.objects.filter(device_type_id=device.device_type_id)
            .order_by("-end_of_support", "-end_of_sale", "-release_date")
            .first()
        )

    def _software_notice(self, device):
        if SoftwareLCM is None:
            return None

        software_version = getattr(device, "software_version", None)
        if not software_version:
            return None

        platform = getattr(software_version, "platform", None)
        version = getattr(software_version, "version", None) or str(software_version)
        if platform and version:
            return (
                SoftwareLCM.objects.filter(device_platform=platform, version=version)
                .order_by("-end_of_support", "-release_date")
                .first()
            )

        return None

    def _hardware_section(self, device):
        record = self._hardware_notice(device)
        status_class, status_label = _section_status(record)
        section = {
            "title": "Hardware lifecycle",
            "source": _value_to_text(getattr(device, "device_type", None)),
            "record_label": _value_to_text(record) if record else None,
            "status_class": status_class,
            "status_label": status_label,
            "record": record,
            "native_fields": [
                _field("Release date", getattr(record, "release_date", None) if record else None),
                _field("End of sale", getattr(record, "end_of_sale", None) if record else None),
                _field("End of support", getattr(record, "end_of_support", None) if record else None),
                _field(
                    "End of SW maintenance releases",
                    getattr(record, "end_of_sw_releases", None) if record else None,
                ),
                _field(
                    "End of security patches",
                    getattr(record, "end_of_security_patches", None) if record else None,
                ),
                _field(
                    "Documentation URL",
                    getattr(record, "documentation_url", None) if record else None,
                    getattr(record, "documentation_url", None) if record else None,
                ),
            ],
            "custom_fields": [],
            "notes": getattr(record, "comments", None) if record else None,
        }

        if record:
            for label, key in (
                ("Product bulletin number", "product_bulletin_number"),
                ("External announcement date", "external_announcement_date"),
                ("End of service contract renewal date", "end_of_service_contract_renewal_date"),
                ("End of routine failure analysis date", "end_of_routine_failure_analysis_date"),
                ("End of service attach date", "end_of_svc_attach_date"),
                ("Updated timestamp", "updated_timestamp"),
            ):
                value = _custom_field_value(record, key)
                if value not in (None, ""):
                    section["custom_fields"].append(_field(label, value))
        return section

    def _software_section(self, device):
        record = self._software_notice(device)
        status_class, status_label = _section_status(record)
        software_version = getattr(device, "software_version", None)
        source_label = _value_to_text(software_version) if software_version else None
        if software_version and getattr(software_version, "version", None):
            source_label = f"{software_version.platform} - {software_version.version}"

        section = {
            "title": "Software lifecycle",
            "source": source_label,
            "record_label": _value_to_text(record) if record else None,
            "status_class": status_class,
            "status_label": status_label,
            "record": record,
            "native_fields": [
                _field("Release date", getattr(record, "release_date", None) if record else None),
                _field("End of support", getattr(record, "end_of_support", None) if record else None),
                _field(
                    "Documentation URL",
                    getattr(record, "documentation_url", None) if record else None,
                    getattr(record, "documentation_url", None) if record else None,
                ),
                _field("Long term support", getattr(record, "long_term_support", None) if record else None),
                _field("Pre-release", getattr(record, "pre_release", None) if record else None),
            ],
            "custom_fields": [],
            "notes": None,
        }

        if record:
            for label, key in (
                ("Product bulletin number", "product_bulletin_number"),
                ("External announcement date", "external_announcement_date"),
                ("End of service contract renewal date", "end_of_service_contract_renewal_date"),
                ("End of routine failure analysis date", "end_of_routine_failure_analysis_date"),
                ("End of service attach date", "end_of_svc_attach_date"),
                ("Updated timestamp", "updated_timestamp"),
                ("PID active flag", "pid_active_flag"),
                ("Migration information", "migration_information"),
                ("Migration option", "migration_option"),
                ("Migration product ID", "migration_product_id"),
                ("Migration product name", "migration_product_name"),
                ("Migration strategy", "migration_strategy"),
                ("Migration product info URL", "migration_product_info_url"),
            ):
                value = _custom_field_value(record, key)
                if value not in (None, ""):
                    section["custom_fields"].append(
                        _field(label, value, value if key.endswith("_url") else None)
                    )
        return section

    def full_width_page(self):
        """Render the effective EOX panel across the full detail page width."""
        device = self.context["object"]
        sections = [self._hardware_section(device), self._software_section(device)]
        return self.render(
            "nautobot_ui_plugin/device_effective_eox.html",
            extra_context={"sections": sections, "device": device},
        )


template_extensions = [LocationTopologyButtons, DeviceEffectiveEOXContent]
