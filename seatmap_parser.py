"""Output format for JSON (primary key indicates row):

{
    "1": [
        {
            "id": "1A"
            "available": false,
            "cabinClass": "Economy",
            "price": "no offer",
            "currency": "no offer",
            "seatType": [
               "Limited Recline",
                "Center"
            ]
        },
        {
            "id": "1B",
            "available": true,
            "cabinClass": "Economy"
            "price": 44.0,
            "currency": "USD",
            "seatType": [
                "Window"
            ]
        },
    ],
    "2": [
        ...
"""
import argparse
import os
import xml.etree.ElementTree as ET  # noqa: standard import alias is CamelCase
import json
import sys

# OpenTravel namespaces
OTNS = {
    "soapenv": "http://schemas.xmlsoap.org/soap/envelope/",
    "ns": "http://www.opentravel.org/OTA/2003/05/common/",
}

# IATA namespaces
IATANS = {"": "http://www.iata.org/IATA/EDIST/2017.2"}


def cli():
    """Main command-line interface for this app."""
    parser = argparse.ArgumentParser(description="Parse XML seatmaps into JSON")
    parser.add_argument(
        "input_file", type=argparse.FileType("r"), help="XML input file", nargs=1
    )
    args = parser.parse_args()
    in_file = args.input_file[0]
    try:
        parsed = parse_from(in_file)
    except ValueError as e:
        parser.error(str(e))
        sys.exit(1)
    with open(out_name(in_file.name), "w") as f:
        json.dump(parsed, f)


def parse_from(in_file):
    """Parse the XML in_file and save to [FILENAME]_parsed.json"""
    tree = ET.parse(in_file)
    root = tree.getroot()
    if root.tag.endswith("Envelope"):
        return parse_opentravel(root)
    if root.tag.endswith("SeatAvailabilityRS"):
        return parse_iata(root)
    raise ValueError("unsupported XML format: use OpenTravel or IATA.")


def parse_opentravel(root):
    """Parse the OpenTravel XML in_file and save to [FILENAME]_parsed.json"""
    out = {}
    cabins = root.iterfind(
        (
            "soapenv:Body/ns:OTA_AirSeatMapRS/ns:SeatMapResponses/"
            "ns:SeatMapResponse/ns:SeatMapDetails/ns:CabinClass"
        ),
        OTNS,
    )
    for cabin in cabins:
        for row in cabin:
            cabin_class = row.get("CabinType")
            seats = []
            for seat in row.iterfind("ns:SeatInfo", OTNS):
                summary = seat.find("ns:Summary", OTNS)
                service = seat.find("ns:Service", OTNS)
                if service:
                    fee = service.find("ns:Fee", OTNS)
                    price = float(fee.get("Amount")) / 10 ** int(
                        fee.get("DecimalPlaces")
                    )
                    currency = fee.get("CurrencyCode")
                else:
                    price = currency = "no offer"
                seats.append(
                    {
                        "id": summary.get("SeatNumber"),
                        "available": summary.get("AvailableInd") == "true",
                        "cabinClass": cabin_class,
                        "price": price,
                        "currency": currency,
                        "seatType": [
                            feat.text
                            if "Other" not in feat.text
                            else feat.get("extension")
                            for feat in seat.iterfind("ns:Features", OTNS)
                        ],
                    }
                )
            out[row.get("RowNumber")] = seats
    return out


def parse_iata(root):
    """Parse the IATA XML in_file and save to [FILENAME]_parsed.json"""
    offers = {}
    for offer in root.iterfind("ALaCarteOffer/ALaCarteOfferItem", namespaces=IATANS):
        currency_price = offer.find(
            "UnitPriceDetail/TotalAmount/SimpleCurrencyPrice", namespaces=IATANS
        )
        currency = currency_price.get("Code")
        price = float(currency_price.text)
        offers[offer.get("OfferItemID")] = currency, price
    defs = {
        defn.get("SeatDefinitionID"): defn.find(
            "Description/Text", namespaces=IATANS
        ).text
        for defn in root.iterfind(
            "DataLists/SeatDefinitionList/SeatDefinition", namespaces=IATANS
        )
    }
    out = {}
    for row in root.iterfind("SeatMap/Cabin/Row", namespaces=IATANS):
        seats = []
        row_num = row.find("Number", namespaces=IATANS).text
        for seat in row.iterfind("Seat", namespaces=IATANS):
            offer = seat.find("OfferItemRefs", namespaces=IATANS)
            if offer is not None:
                price, currency = offers[offer.text]
            else:
                price = currency = "no offer"
            seat_type = [
                defs[ref.text]
                for ref in seat.findall("SeatDefinitionRef", namespaces=IATANS)
            ]
            seats.append(
                {
                    "id": row_num + seat.find("Column", namespaces=IATANS).text,
                    "available": "AVAILABLE" in seat_type,
                    "cabinClass": "unspecified",
                    "price": price,
                    "currency": currency,
                    "seatType": [x for x in seat_type if x != "AVAILABLE"],
                }
            )
        out[row_num] = seats
    return out


def out_name(in_name):
    """Get the output filename for an XML in_name.

    Examples:
        >>> out_name("/Users/exampleperson/Documents/seatmap1.xml")
        'seatmap1_parsed.json'
    """
    return f"{''.join(os.path.basename(in_name).split('.')[:-1])}_parsed.json"


if __name__ == "__main__":
    cli()  # CLI
