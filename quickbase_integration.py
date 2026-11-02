import os
from typing import Any, Dict, Iterable, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


QB_TABLES = {
    "parameters": "PARAMETERS_TABLE_ID",
    "families": "FAMILIES_TABLE_ID",
    "family_param_links": "FAMILY_PARAM_LINK_TABLE_ID",
    "validation_log": "VALIDATION_LOG_TABLE_ID",
}


class QuickbaseClient:
    """Quickbase REST client tailored to the DDM database workflow."""

    def __init__(
        self,
        app_id: str,
        user_token: str,
        app_token: Optional[str] = None,
        realm_hostname: str = "https://api.quickbase.com",
    ) -> None:
        if not app_id:
            raise ValueError("app_id is required")
        if not user_token:
            raise ValueError("user_token is required")

        self.app_id = app_id
        self.user_token = user_token
        self.app_token = app_token
        self.realm_hostname = realm_hostname.rstrip("/")

    def _require_requests(self) -> None:
        if requests is None:
            raise RuntimeError(
                "The 'requests' package is required for Quickbase API calls. "
                "Install it with: pip install requests"
            )

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "QB-USER-TOKEN": self.user_token,
        }
        if self.app_token:
            headers["Authorization"] = f"QB-USER-TOKEN {self.user_token}"
        return headers

    def _request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._require_requests()
        response = requests.request(
            method=method,
            url=f"{self.realm_hostname}{path}",
            headers=self._headers(),
            json=payload,
            timeout=30,
        )

        try:
            body = response.json()
        except ValueError:
            body = {"text": response.text}

        if response.status_code >= 400:
            raise RuntimeError(
                f"Quickbase API error ({response.status_code}) for {method} {path}: {body}"
            )

        return body

    def get_app(self) -> Dict[str, Any]:
        return self._request("GET", f"/v1/apps/{self.app_id}")

    def list_tables(self) -> Dict[str, Any]:
        return self._request("GET", f"/v1/apps/{self.app_id}/tables")

    def list_fields(self, table_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/v1/tables/{table_id}/fields")

    def query(
        self,
        table_id: str,
        fields: Optional[Iterable[int]] = None,
        where: Optional[Dict[str, Any]] = None,
        sort_by: Optional[List[Dict[str, str]]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "from": table_id,
            "select": list(fields) if fields is not None else [],
            "options": {"limit": limit},
        }

        if where is not None:
            payload["where"] = where

        if sort_by is not None:
            payload["sortBy"] = sort_by

        result = self._request("POST", "/v1/records/query", payload)
        return result.get("data", [])

    def create_records(self, table_id: str, records: List[Dict[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
        payload = {"to": table_id, "data": records}
        result = self._request("POST", "/v1/records", payload)
        return result.get("data", [])

    def update_records(self, table_id: str, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        payload = {"to": table_id, "data": records}
        result = self._request("POST", "/v1/records", payload)
        return result.get("data", [])

    def upsert_record(
        self,
        table_id: str,
        external_field_id: int,
        external_value: str,
        payload: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        existing = self.query(
            table_id=table_id,
            where={"fieldId": external_field_id, "operator": "=", "value": external_value},
            limit=1,
        )

        if existing:
            record = existing[0]
            record_id = record.get("id")
            if record_id is None:
                raise ValueError(f"Quickbase record from query missing id: {record}")
            update_payload = {"id": record_id, **payload}
            updated = self.update_records(table_id, [update_payload])
            return updated[0]

        created = self.create_records(table_id, [payload])
        return created[0]


class QuickbaseSchema:
    """Starter field map for the DDM database app."""

    PARAMETERS = {
        "name": 3,
        "guid": 4,
        "dtype": 5,
        "group_under": 6,
        "formula": 7,
        "instance_param": 8,
        "status": 9,
        "validation_message": 10,
    }

    FAMILIES = {
        "name": 3,
        "client": 4,
        "country": 5,
        "category": 6,
        "description": 7,
        "status": 8,
        "validation_message": 9,
    }

    FAMILY_PARAM_LINKS = {
        "family_id": 3,
        "parameter_id": 4,
        "included_in_family": 5,
        "required": 6,
        "notes": 7,
    }

    VALIDATION_LOG = {
        "record_type": 3,
        "record_id": 4,
        "severity": 5,
        "message": 6,
        "created_at": 7,
        "resolved": 8,
    }


class QuickbaseSyncService:
    """Service layer used to map project data into Quickbase tables."""

    def __init__(self, client: QuickbaseClient, table_ids: Optional[Dict[str, str]] = None):
        self.client = client
        self.table_ids = {**QB_TABLES, **(table_ids or {})}

    def map_param_record(self, param_obj: Any) -> Dict[str, Dict[str, Any]]:
        fields = QuickbaseSchema.PARAMETERS
        return {
            str(fields["name"]): {"value": getattr(param_obj, "name", "")},
            str(fields["guid"]): {"value": getattr(param_obj, "guid", "")},
            str(fields["dtype"]): {"value": getattr(param_obj, "dtype", "")},
            str(fields["group_under"]): {"value": getattr(param_obj, "group_under", "") or ""},
            str(fields["formula"]): {"value": getattr(param_obj, "formula", "") or ""},
            str(fields["instance_param"]): {"value": int(bool(getattr(param_obj, "instance_param", True)))},
            str(fields["status"]): {"value": "Draft"},
            str(fields["validation_message"]): {"value": ""},
        }

    def map_family_record(self, family_obj: Any) -> Dict[str, Dict[str, Any]]:
        fields = QuickbaseSchema.FAMILIES
        return {
            str(fields["name"]): {"value": getattr(family_obj, "name", "")},
            str(fields["client"]): {"value": getattr(family_obj, "client", "") or ""},
            str(fields["country"]): {"value": getattr(family_obj, "country", "") or ""},
            str(fields["category"]): {"value": getattr(family_obj, "category", "") or ""},
            str(fields["description"]): {"value": getattr(family_obj, "description", "") or ""},
            str(fields["status"]): {"value": "Draft"},
            str(fields["validation_message"]): {"value": ""},
        }

    def map_family_param_link(
        self,
        family_id: Any,
        parameter_id: Any,
        *,
        required: bool = False,
        notes: str = "",
    ) -> Dict[str, Dict[str, Any]]:
        fields = QuickbaseSchema.FAMILY_PARAM_LINKS
        return {
            str(fields["family_id"]): {"value": family_id},
            str(fields["parameter_id"]): {"value": parameter_id},
            str(fields["included_in_family"]): {"value": True},
            str(fields["required"]): {"value": int(bool(required))},
            str(fields["notes"]): {"value": notes},
        }

    def sync_parameter(self, param_obj: Any) -> Dict[str, Any]:
        payload = self.map_param_record(param_obj)
        return self.client.upsert_record(
            table_id=self.table_ids["parameters"],
            external_field_id=QuickbaseSchema.PARAMETERS["name"],
            external_value=getattr(param_obj, "name", ""),
            payload=payload,
        )

    def sync_family(self, family_obj: Any) -> Dict[str, Any]:
        payload = self.map_family_record(family_obj)
        return self.client.upsert_record(
            table_id=self.table_ids["families"],
            external_field_id=QuickbaseSchema.FAMILIES["name"],
            external_value=getattr(family_obj, "name", ""),
            payload=payload,
        )

    def sync_family_param_links(self, family_id: Any, params: Iterable[Any]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for param in params:
            payload = self.map_family_param_link(
                family_id=family_id,
                parameter_id=getattr(param, "guid", ""),
                required=False,
                notes="",
            )
            result.append(
                self.client.create_records(
                    table_id=self.table_ids["family_param_links"],
                    records=[payload],
                )
            )
        return result

    def add_validation_log(self, record_type: str, record_id: Any, severity: str, message: str) -> Dict[str, Any]:
        payload = {
            str(QuickbaseSchema.VALIDATION_LOG["record_type"]): {"value": record_type},
            str(QuickbaseSchema.VALIDATION_LOG["record_id"]): {"value": str(record_id)},
            str(QuickbaseSchema.VALIDATION_LOG["severity"]): {"value": severity},
            str(QuickbaseSchema.VALIDATION_LOG["message"]): {"value": message},
        }
        return self.client.create_records(self.table_ids["validation_log"], [payload])[0]

    def publish_validation_status(self, table_name: str, record_name: str, status: str, message: str) -> Dict[str, Any]:
        table_id = self.table_ids[table_name]
        field_map = QuickbaseSchema.PARAMETERS if table_name == "parameters" else QuickbaseSchema.FAMILIES
        payload = {
            str(field_map["status"]): {"value": status},
            str(field_map["validation_message"]): {"value": message},
        }

        existing = self.client.query(
            table_id=table_id,
            where={"fieldId": field_map["name"], "operator": "=", "value": record_name},
            limit=1,
        )

        if existing:
            return self.client.update_records(table_id, [{"id": existing[0]["id"], **payload}])[0]
        return self.client.create_records(table_id, [payload])[0]


def param_to_quickbase_record(param_obj: Any) -> Dict[str, Dict[str, Any]]:
    """Example map from a local Param-style object to Quickbase payload."""
    svc = QuickbaseSyncService(client=None, table_ids=QB_TABLES)
    return svc.map_param_record(param_obj)


def family_to_quickbase_record(family_obj: Any) -> Dict[str, Dict[str, Any]]:
    """Example map from a local Fam-style object to Quickbase payload."""
    svc = QuickbaseSyncService(client=None, table_ids=QB_TABLES)
    return svc.map_family_record(family_obj)


if __name__ == "__main__":
    qb = QuickbaseClient(
        app_id=os.environ.get("QB_APP_ID", "REPLACE_WITH_APP_ID"),
        user_token=os.environ.get("QB_USER_TOKEN", "REPLACE_WITH_USER_TOKEN"),
        app_token=os.environ.get("QB_APP_TOKEN"),
    )

    sync = QuickbaseSyncService(
        qb,
        table_ids={
            "parameters": "PARAMETERS_TABLE_ID",
            "families": "FAMILIES_TABLE_ID",
            "family_param_links": "FAMILY_PARAM_LINK_TABLE_ID",
            "validation_log": "VALIDATION_LOG_TABLE_ID",
        },
    )

    print("Quickbase sync module is ready.")
    print("Example usage:")
    print("  sync.sync_parameter(param_obj)")
    print("  sync.sync_family(family_obj)")
    print("  sync.publish_validation_status('parameters', 'Length', 'Error', 'Missing family association')")
    print("  sync.add_validation_log('parameter', 'abc', 'Error', 'Formula references missing parameter')")


__all__ = [
    "QuickbaseClient",
    "QuickbaseSchema",
    "QuickbaseSyncService",
    "param_to_quickbase_record",
    "family_to_quickbase_record",
]
