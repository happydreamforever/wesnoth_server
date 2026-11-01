"""Select a domain by verified database generation, never by a request field."""
from .domain import AllianceService


def service_for(db):
    record = db.schema_metadata.find_one({'_id': 'alliance'}, {'version': 1})
    if record and record.get('version') == 5:
        from .court.service import CourtService
        return CourtService(db)
    return AllianceService(db)
