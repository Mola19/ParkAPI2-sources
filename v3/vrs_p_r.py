"""
Copyright 2023 binary butterfly GmbH
Use of this source code is governed by an MIT-style license that can be found in the LICENSE.txt.
"""

from datetime import datetime, timezone

from openpyxl.workbook.workbook import Workbook
from validataclass.exceptions import ValidationError

from common.base_converter import XlsxConverter
from common.exceptions import ImportParkingSiteException
from common.models import ImportSourceResult
from common.validators import StaticParkingSiteInput
from util import SourceInfo


class VrsParkAndRideConverter(XlsxConverter):
    source_info = SourceInfo(
        id='vrs-p-r',
        name='Verband Region Stuttgart: Park and Ride',
        public_url='https://www.region-stuttgart.org/de/bereiche-aufgaben/mobilitaet/park-ride/',
    )

    # If there are more tables with our defined format, it would make sense to move header_row to XlsxConverter
    header_row: dict[str, str] = {
        'ID': 'uid',
        'Name': 'name',
        'Art der Anlage': 'type',
        'Betreiber Name': 'operator_name',
        'Längengrad': 'lat',
        'Breitengrad': 'lon',
        'Adresse mit PLZ und Stadt': 'address',
        'Maximale Parkdauer': 'max_stay',
        'Anzahl Stellplätze': 'capacity',
        'Anzahl Carsharing-Parkplätze': 'capacity_carsharing',
        'Anzahl Ladeplätze': 'capacity_charging',
        'Anzahl Frauenparkplätze': 'capacity_woman',
        'Anzahl Behindertenparkplätze': 'capacity_disabled',
        'Anlage beleuchtet?': 'has_lighting',
        'gebührenpflichtig?': 'has_fee',
        'Existieren Live-Daten?': 'has_realtime_data',
        'Gebühren-Informationen': 'fee_description',
        'Webseite': 'public_url',
        'Park&Ride': 'is_park_and_ride',
        '24/7 geöffnet?': 'opening_hours_is_24_7',
        'Öffnungszeiten Mo-Fr Beginn': 'opening_hours_weekday_begin',
        'Öffnungszeiten Mo-Fr Ende': 'opening_hours_weekday_end',
        'Öffnungszeiten Sa Beginn': 'opening_hours_saturday_begin',
        'Öffnungszeiten Sa Ende': 'opening_hours_saturday_end',
        'Öffnungszeiten So Beginn': 'opening_hours_sunday_begin',
        'Öffnungszeiten So Ende': 'opening_hours_sunday_end',
        'Weitere öffentliche Informationen': 'description',
    }
    # If there are more tables with our defined format, it would make sense to move type_mapping to XlsxConverter
    type_mapping: dict[str, str] = {
        'Parkplatz': 'OFF_STREET_PARKING_GROUND',
        'Parkhaus': 'CAR_PARK',
        'Tiefgarage': 'UNDERGROUND',
        'Am Straßenrand': 'ON_STREET',
    }

    def handle_xlsx(self, workbook: Workbook) -> ImportSourceResult:
        worksheet = workbook.active
        mapping = self.get_mapping_by_header(next(worksheet.rows))

        static_parking_site_errors: list[ImportParkingSiteException] = []
        static_parking_site_inputs: list[StaticParkingSiteInput] = []

        for row in worksheet.iter_rows(min_row=2):
            # ignore empty lines as LibreOffice sometimes adds empty rows at the end of a file
            if row[0].value is None:
                continue

            parking_site_raw_dict: dict[str, str] = {}
            for position, field in enumerate(mapping):
                parking_site_raw_dict[field] = row[position].value

            parking_site_dict = {key: value for key, value in parking_site_raw_dict.items() if not key.startswith('opening_hours_')}
            opening_hours_input = self.excel_opening_time_validator.validate(
                {key: value for key, value in parking_site_raw_dict.items() if key.startswith('opening_hours_')}
            )
            parking_site_dict['opening_hours'] = opening_hours_input.get_osm_opening_hours()
            parking_site_dict['type'] = self.type_mapping.get(parking_site_dict.get('type'))
            parking_site_dict['static_data_updated_at'] = datetime.now(tz=timezone.utc).isoformat()

            try:
                static_parking_site_inputs.append(self.static_parking_site_validator.validate(parking_site_dict))
            except ValidationError as e:
                static_parking_site_errors.append(
                    ImportParkingSiteException(
                        uid=parking_site_dict.get('uid'),
                        message=f'invalid static parking site data: {e.to_dict()}',
                    )
                )
                continue

        return self.generate_import_source_result(
            static_parking_site_inputs=static_parking_site_inputs,
            static_parking_site_errors=static_parking_site_errors,
        )
