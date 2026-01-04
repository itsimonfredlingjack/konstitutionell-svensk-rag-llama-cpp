#!/usr/bin/env python3
"""
Generate kommun_manifest.json with all 290 Swedish municipalities.
Includes URLs and priority based on population size.
"""

import json
from datetime import datetime
from pathlib import Path

# All 290 kommuner from SCB (2024)
# Format: (kod, namn, lan)
KOMMUNER = [
    ("0114", "Upplands Väsby", "Stockholms län"),
    ("0115", "Vallentuna", "Stockholms län"),
    ("0117", "Österåker", "Stockholms län"),
    ("0120", "Värmdö", "Stockholms län"),
    ("0123", "Järfälla", "Stockholms län"),
    ("0125", "Ekerö", "Stockholms län"),
    ("0126", "Huddinge", "Stockholms län"),
    ("0127", "Botkyrka", "Stockholms län"),
    ("0128", "Salem", "Stockholms län"),
    ("0136", "Haninge", "Stockholms län"),
    ("0138", "Tyresö", "Stockholms län"),
    ("0139", "Upplands-Bro", "Stockholms län"),
    ("0140", "Nykvarn", "Stockholms län"),
    ("0160", "Täby", "Stockholms län"),
    ("0162", "Danderyd", "Stockholms län"),
    ("0163", "Sollentuna", "Stockholms län"),
    ("0180", "Stockholm", "Stockholms län"),
    ("0181", "Södertälje", "Stockholms län"),
    ("0182", "Nacka", "Stockholms län"),
    ("0183", "Sundbyberg", "Stockholms län"),
    ("0184", "Solna", "Stockholms län"),
    ("0186", "Lidingö", "Stockholms län"),
    ("0187", "Vaxholm", "Stockholms län"),
    ("0188", "Norrtälje", "Stockholms län"),
    ("0191", "Sigtuna", "Stockholms län"),
    ("0192", "Nynäshamn", "Stockholms län"),
    ("0305", "Håbo", "Uppsala län"),
    ("0319", "Älvkarleby", "Uppsala län"),
    ("0330", "Knivsta", "Uppsala län"),
    ("0331", "Heby", "Uppsala län"),
    ("0360", "Tierp", "Uppsala län"),
    ("0380", "Uppsala", "Uppsala län"),
    ("0381", "Enköping", "Uppsala län"),
    ("0382", "Östhammar", "Uppsala län"),
    ("0428", "Vingåker", "Södermanlands län"),
    ("0461", "Gnesta", "Södermanlands län"),
    ("0480", "Nyköping", "Södermanlands län"),
    ("0481", "Oxelösund", "Södermanlands län"),
    ("0482", "Flen", "Södermanlands län"),
    ("0483", "Katrineholm", "Södermanlands län"),
    ("0484", "Eskilstuna", "Södermanlands län"),
    ("0486", "Strängnäs", "Södermanlands län"),
    ("0488", "Trosa", "Södermanlands län"),
    ("0509", "Ödeshög", "Östergötlands län"),
    ("0512", "Ydre", "Östergötlands län"),
    ("0513", "Kinda", "Östergötlands län"),
    ("0560", "Boxholm", "Östergötlands län"),
    ("0561", "Åtvidaberg", "Östergötlands län"),
    ("0562", "Finspång", "Östergötlands län"),
    ("0563", "Valdemarsvik", "Östergötlands län"),
    ("0580", "Linköping", "Östergötlands län"),
    ("0581", "Norrköping", "Östergötlands län"),
    ("0582", "Söderköping", "Östergötlands län"),
    ("0583", "Motala", "Östergötlands län"),
    ("0584", "Vadstena", "Östergötlands län"),
    ("0586", "Mjölby", "Östergötlands län"),
    ("0604", "Aneby", "Jönköpings län"),
    ("0617", "Gnosjö", "Jönköpings län"),
    ("0642", "Mullsjö", "Jönköpings län"),
    ("0643", "Habo", "Jönköpings län"),
    ("0662", "Gislaved", "Jönköpings län"),
    ("0665", "Vaggeryd", "Jönköpings län"),
    ("0680", "Jönköping", "Jönköpings län"),
    ("0682", "Nässjö", "Jönköpings län"),
    ("0683", "Värnamo", "Jönköpings län"),
    ("0684", "Sävsjö", "Jönköpings län"),
    ("0685", "Vetlanda", "Jönköpings län"),
    ("0686", "Eksjö", "Jönköpings län"),
    ("0687", "Tranås", "Jönköpings län"),
    ("0760", "Uppvidinge", "Kronobergs län"),
    ("0761", "Lessebo", "Kronobergs län"),
    ("0763", "Tingsryd", "Kronobergs län"),
    ("0764", "Alvesta", "Kronobergs län"),
    ("0765", "Älmhult", "Kronobergs län"),
    ("0767", "Markaryd", "Kronobergs län"),
    ("0780", "Växjö", "Kronobergs län"),
    ("0781", "Ljungby", "Kronobergs län"),
    ("0821", "Högsby", "Kalmar län"),
    ("0834", "Torsås", "Kalmar län"),
    ("0840", "Mörbylånga", "Kalmar län"),
    ("0860", "Hultsfred", "Kalmar län"),
    ("0861", "Mönsterås", "Kalmar län"),
    ("0862", "Emmaboda", "Kalmar län"),
    ("0880", "Kalmar", "Kalmar län"),
    ("0881", "Nybro", "Kalmar län"),
    ("0882", "Oskarshamn", "Kalmar län"),
    ("0883", "Västervik", "Kalmar län"),
    ("0884", "Vimmerby", "Kalmar län"),
    ("0885", "Borgholm", "Kalmar län"),
    ("0980", "Gotland", "Gotlands län"),
    ("1060", "Olofström", "Blekinge län"),
    ("1080", "Karlskrona", "Blekinge län"),
    ("1081", "Ronneby", "Blekinge län"),
    ("1082", "Karlshamn", "Blekinge län"),
    ("1083", "Sölvesborg", "Blekinge län"),
    ("1214", "Svalöv", "Skåne län"),
    ("1230", "Staffanstorp", "Skåne län"),
    ("1231", "Burlöv", "Skåne län"),
    ("1233", "Vellinge", "Skåne län"),
    ("1256", "Östra Göinge", "Skåne län"),
    ("1257", "Örkelljunga", "Skåne län"),
    ("1260", "Bjuv", "Skåne län"),
    ("1261", "Kävlinge", "Skåne län"),
    ("1262", "Lomma", "Skåne län"),
    ("1263", "Svedala", "Skåne län"),
    ("1264", "Skurup", "Skåne län"),
    ("1265", "Sjöbo", "Skåne län"),
    ("1266", "Hörby", "Skåne län"),
    ("1267", "Höör", "Skåne län"),
    ("1270", "Tomelilla", "Skåne län"),
    ("1272", "Bromölla", "Skåne län"),
    ("1273", "Osby", "Skåne län"),
    ("1275", "Perstorp", "Skåne län"),
    ("1276", "Klippan", "Skåne län"),
    ("1277", "Åstorp", "Skåne län"),
    ("1278", "Båstad", "Skåne län"),
    ("1280", "Malmö", "Skåne län"),
    ("1281", "Lund", "Skåne län"),
    ("1282", "Landskrona", "Skåne län"),
    ("1283", "Helsingborg", "Skåne län"),
    ("1284", "Höganäs", "Skåne län"),
    ("1285", "Eslöv", "Skåne län"),
    ("1286", "Ystad", "Skåne län"),
    ("1287", "Trelleborg", "Skåne län"),
    ("1290", "Kristianstad", "Skåne län"),
    ("1291", "Simrishamn", "Skåne län"),
    ("1292", "Ängelholm", "Skåne län"),
    ("1293", "Hässleholm", "Skåne län"),
    ("1315", "Hylte", "Hallands län"),
    ("1380", "Halmstad", "Hallands län"),
    ("1381", "Laholm", "Hallands län"),
    ("1382", "Falkenberg", "Hallands län"),
    ("1383", "Varberg", "Hallands län"),
    ("1384", "Kungsbacka", "Hallands län"),
    ("1401", "Härryda", "Västra Götalands län"),
    ("1402", "Partille", "Västra Götalands län"),
    ("1407", "Öckerö", "Västra Götalands län"),
    ("1415", "Stenungsund", "Västra Götalands län"),
    ("1419", "Tjörn", "Västra Götalands län"),
    ("1421", "Orust", "Västra Götalands län"),
    ("1427", "Sotenäs", "Västra Götalands län"),
    ("1430", "Munkedal", "Västra Götalands län"),
    ("1435", "Tanum", "Västra Götalands län"),
    ("1438", "Dals-Ed", "Västra Götalands län"),
    ("1439", "Färgelanda", "Västra Götalands län"),
    ("1440", "Ale", "Västra Götalands län"),
    ("1441", "Lerum", "Västra Götalands län"),
    ("1442", "Vårgårda", "Västra Götalands län"),
    ("1443", "Bollebygd", "Västra Götalands län"),
    ("1444", "Grästorp", "Västra Götalands län"),
    ("1445", "Essunga", "Västra Götalands län"),
    ("1446", "Karlsborg", "Västra Götalands län"),
    ("1447", "Gullspång", "Västra Götalands län"),
    ("1452", "Tranemo", "Västra Götalands län"),
    ("1460", "Bengtsfors", "Västra Götalands län"),
    ("1461", "Mellerud", "Västra Götalands län"),
    ("1462", "Lilla Edet", "Västra Götalands län"),
    ("1463", "Mark", "Västra Götalands län"),
    ("1465", "Svenljunga", "Västra Götalands län"),
    ("1466", "Herrljunga", "Västra Götalands län"),
    ("1470", "Vara", "Västra Götalands län"),
    ("1471", "Götene", "Västra Götalands län"),
    ("1472", "Tibro", "Västra Götalands län"),
    ("1473", "Töreboda", "Västra Götalands län"),
    ("1480", "Göteborg", "Västra Götalands län"),
    ("1481", "Mölndal", "Västra Götalands län"),
    ("1482", "Kungälv", "Västra Götalands län"),
    ("1484", "Lysekil", "Västra Götalands län"),
    ("1485", "Uddevalla", "Västra Götalands län"),
    ("1486", "Strömstad", "Västra Götalands län"),
    ("1487", "Vänersborg", "Västra Götalands län"),
    ("1488", "Trollhättan", "Västra Götalands län"),
    ("1489", "Alingsås", "Västra Götalands län"),
    ("1490", "Borås", "Västra Götalands län"),
    ("1491", "Ulricehamn", "Västra Götalands län"),
    ("1492", "Åmål", "Västra Götalands län"),
    ("1493", "Mariestad", "Västra Götalands län"),
    ("1494", "Lidköping", "Västra Götalands län"),
    ("1495", "Skara", "Västra Götalands län"),
    ("1496", "Skövde", "Västra Götalands län"),
    ("1497", "Hjo", "Västra Götalands län"),
    ("1498", "Tidaholm", "Västra Götalands län"),
    ("1499", "Falköping", "Västra Götalands län"),
    ("1715", "Kil", "Värmlands län"),
    ("1730", "Eda", "Värmlands län"),
    ("1737", "Torsby", "Värmlands län"),
    ("1760", "Storfors", "Värmlands län"),
    ("1761", "Hammarö", "Värmlands län"),
    ("1762", "Munkfors", "Värmlands län"),
    ("1763", "Forshaga", "Värmlands län"),
    ("1764", "Grums", "Värmlands län"),
    ("1765", "Årjäng", "Värmlands län"),
    ("1766", "Sunne", "Värmlands län"),
    ("1780", "Karlstad", "Värmlands län"),
    ("1781", "Kristinehamn", "Värmlands län"),
    ("1782", "Filipstad", "Värmlands län"),
    ("1783", "Hagfors", "Värmlands län"),
    ("1784", "Arvika", "Värmlands län"),
    ("1785", "Säffle", "Värmlands län"),
    ("1814", "Lekeberg", "Örebro län"),
    ("1860", "Laxå", "Örebro län"),
    ("1861", "Hallsberg", "Örebro län"),
    ("1862", "Degerfors", "Örebro län"),
    ("1863", "Hällefors", "Örebro län"),
    ("1864", "Ljusnarsberg", "Örebro län"),
    ("1880", "Örebro", "Örebro län"),
    ("1881", "Kumla", "Örebro län"),
    ("1882", "Askersund", "Örebro län"),
    ("1883", "Karlskoga", "Örebro län"),
    ("1884", "Nora", "Örebro län"),
    ("1885", "Lindesberg", "Örebro län"),
    ("1904", "Skinnskatteberg", "Västmanlands län"),
    ("1907", "Surahammar", "Västmanlands län"),
    ("1960", "Kungsör", "Västmanlands län"),
    ("1961", "Hallstahammar", "Västmanlands län"),
    ("1962", "Norberg", "Västmanlands län"),
    ("1980", "Västerås", "Västmanlands län"),
    ("1981", "Sala", "Västmanlands län"),
    ("1982", "Fagersta", "Västmanlands län"),
    ("1983", "Köping", "Västmanlands län"),
    ("1984", "Arboga", "Västmanlands län"),
    ("2021", "Vansbro", "Dalarnas län"),
    ("2023", "Malung-Sälen", "Dalarnas län"),
    ("2026", "Gagnef", "Dalarnas län"),
    ("2029", "Leksand", "Dalarnas län"),
    ("2031", "Rättvik", "Dalarnas län"),
    ("2034", "Orsa", "Dalarnas län"),
    ("2039", "Älvdalen", "Dalarnas län"),
    ("2061", "Smedjebacken", "Dalarnas län"),
    ("2062", "Mora", "Dalarnas län"),
    ("2080", "Falun", "Dalarnas län"),
    ("2081", "Borlänge", "Dalarnas län"),
    ("2082", "Säter", "Dalarnas län"),
    ("2083", "Hedemora", "Dalarnas län"),
    ("2084", "Avesta", "Dalarnas län"),
    ("2085", "Ludvika", "Dalarnas län"),
    ("2101", "Ockelbo", "Gävleborgs län"),
    ("2104", "Hofors", "Gävleborgs län"),
    ("2121", "Ovanåker", "Gävleborgs län"),
    ("2132", "Nordanstig", "Gävleborgs län"),
    ("2161", "Ljusdal", "Gävleborgs län"),
    ("2180", "Gävle", "Gävleborgs län"),
    ("2181", "Sandviken", "Gävleborgs län"),
    ("2182", "Söderhamn", "Gävleborgs län"),
    ("2183", "Bollnäs", "Gävleborgs län"),
    ("2184", "Hudiksvall", "Gävleborgs län"),
    ("2260", "Ånge", "Västernorrlands län"),
    ("2262", "Timrå", "Västernorrlands län"),
    ("2280", "Härnösand", "Västernorrlands län"),
    ("2281", "Sundsvall", "Västernorrlands län"),
    ("2282", "Kramfors", "Västernorrlands län"),
    ("2283", "Sollefteå", "Västernorrlands län"),
    ("2284", "Örnsköldsvik", "Västernorrlands län"),
    ("2303", "Ragunda", "Jämtlands län"),
    ("2305", "Bräcke", "Jämtlands län"),
    ("2309", "Krokom", "Jämtlands län"),
    ("2313", "Strömsund", "Jämtlands län"),
    ("2321", "Åre", "Jämtlands län"),
    ("2326", "Berg", "Jämtlands län"),
    ("2361", "Härjedalen", "Jämtlands län"),
    ("2380", "Östersund", "Jämtlands län"),
    ("2401", "Nordmaling", "Västerbottens län"),
    ("2403", "Bjurholm", "Västerbottens län"),
    ("2404", "Vindeln", "Västerbottens län"),
    ("2409", "Robertsfors", "Västerbottens län"),
    ("2417", "Norsjö", "Västerbottens län"),
    ("2418", "Malå", "Västerbottens län"),
    ("2421", "Storuman", "Västerbottens län"),
    ("2422", "Sorsele", "Västerbottens län"),
    ("2425", "Dorotea", "Västerbottens län"),
    ("2460", "Vännäs", "Västerbottens län"),
    ("2462", "Vilhelmina", "Västerbottens län"),
    ("2463", "Åsele", "Västerbottens län"),
    ("2480", "Umeå", "Västerbottens län"),
    ("2481", "Lycksele", "Västerbottens län"),
    ("2482", "Skellefteå", "Västerbottens län"),
    ("2505", "Arvidsjaur", "Norrbottens län"),
    ("2506", "Arjeplog", "Norrbottens län"),
    ("2510", "Jokkmokk", "Norrbottens län"),
    ("2513", "Överkalix", "Norrbottens län"),
    ("2514", "Kalix", "Norrbottens län"),
    ("2518", "Övertorneå", "Norrbottens län"),
    ("2521", "Pajala", "Norrbottens län"),
    ("2523", "Gällivare", "Norrbottens län"),
    ("2560", "Älvsbyn", "Norrbottens län"),
    ("2580", "Luleå", "Norrbottens län"),
    ("2581", "Piteå", "Norrbottens län"),
    ("2582", "Boden", "Norrbottens län"),
    ("2583", "Haparanda", "Norrbottens län"),
    ("2584", "Kiruna", "Norrbottens län"),
]

# Priority 5: Top 4 (>200k)
PRIORITY_5 = {"0180", "1480", "1280", "0380"}  # Stockholm, Göteborg, Malmö, Uppsala

# Priority 4: >100k inhabitants
PRIORITY_4 = {
    "0580",  # Linköping
    "1880",  # Örebro
    "1980",  # Västerås
    "1283",  # Helsingborg
    "0581",  # Norrköping
    "0680",  # Jönköping
    "1281",  # Lund
    "2480",  # Umeå
    "2180",  # Gävle
    "1490",  # Borås
    "0484",  # Eskilstuna
    "0181",  # Södertälje
    "1380",  # Halmstad
    "0780",  # Växjö
    "1780",  # Karlstad
    "2281",  # Sundsvall
}

# Priority 3: 50-100k
PRIORITY_3 = {
    "0126",  # Huddinge
    "0182",  # Nacka
    "0163",  # Sollentuna
    "0160",  # Täby
    "0136",  # Haninge
    "0127",  # Botkyrka
    "1488",  # Trollhättan
    "2580",  # Luleå
    "1496",  # Skövde
    "1481",  # Mölndal
    "0184",  # Solna
    "1485",  # Uddevalla
    "2380",  # Östersund
    "1287",  # Trelleborg
    "1290",  # Kristianstad
    "1293",  # Hässleholm
    "0880",  # Kalmar
    "0980",  # Gotland
    "1080",  # Karlskrona
    "1383",  # Varberg
    "1384",  # Kungsbacka
    "2284",  # Örnsköldsvik
    "0583",  # Motala
    "2081",  # Borlänge
    "2482",  # Skellefteå
    "1489",  # Alingsås
    "1401",  # Härryda
    "0123",  # Järfälla
    "2080",  # Falun
    "2581",  # Piteå
    "0114",  # Upplands Väsby
    "1441",  # Lerum
    "1381",  # Laholm
    "1382",  # Falkenberg
    "0188",  # Norrtälje
    "1292",  # Ängelholm
    "1487",  # Vänersborg
    "2584",  # Kiruna
    "1282",  # Landskrona
    "0117",  # Österåker
}


def get_priority(kod: str) -> int:
    """Determine priority based on kommun code."""
    if kod in PRIORITY_5:
        return 5
    elif kod in PRIORITY_4:
        return 4
    elif kod in PRIORITY_3:
        return 3
    else:
        # Default: smaller kommuner
        return 2


def normalize_url_name(namn: str) -> str:
    """
    Convert kommun name to URL-friendly format.
    Examples: "Upplands Väsby" -> "upplandsvasby"
              "Malung-Sälen" -> "malungsalen"
    """
    # Character replacements
    replacements = {
        "å": "a",
        "ä": "a",
        "ö": "o",
        "Å": "a",
        "Ä": "a",
        "Ö": "o",
        "-": "",
        " ": "",
        "'": "",
    }

    result = namn.lower()
    for old, new in replacements.items():
        result = result.replace(old, new)

    return result


# Special URL mappings (kommuner with non-standard URLs)
URL_OVERRIDES = {
    "0180": "stockholm.se",
    "1480": "goteborg.se",
    "1280": "malmo.se",
    "0380": "uppsala.se",
    "0980": "gotland.se",  # Region Gotland
    "1283": "helsingborg.se",
    "0580": "linkoping.se",
    "0581": "norrkoping.se",
    "1880": "orebro.se",
    "1980": "vasteras.se",
    "1281": "lund.se",
    "0680": "jonkoping.se",
    "2480": "umea.se",
    "2180": "gavle.se",
    "1490": "boras.se",
    "0181": "sodertalje.se",
    "0126": "huddinge.se",
    "0182": "nacka.se",
    "1380": "halmstad.se",
    "0780": "vaxjo.se",
    "1780": "karlstad.se",
    "2281": "sundsvall.se",
    "0184": "solna.se",
    "0183": "sundbyberg.se",
    "1488": "trollhattan.se",
    "1383": "varberg.se",
    "1384": "kungsbacka.se",
    "2580": "lulea.se",
    "1496": "skovde.se",
    "1485": "uddevalla.se",
    "2380": "ostersund.se",
    "1287": "trelleborg.se",
    "1290": "kristianstad.se",
    "0880": "kalmar.se",
    "2284": "ornskoldsvik.se",
    "1080": "karlskrona.se",
    "2080": "falun.se",
    "2081": "borlange.se",
    "2482": "skelleftea.se",
    "2584": "kiruna.se",
    "1489": "alingsas.se",
    "1481": "molndal.se",
    "1487": "vanersborg.se",
    "1282": "landskrona.se",
    "1292": "angelholm.se",
    "0484": "eskilstuna.se",
    "0163": "sollentuna.se",
    "0160": "taby.se",
    "0136": "haninge.se",
    "0127": "botkyrka.se",
    "0117": "osteraker.se",
    "0123": "jarfalla.se",
    "0114": "upplandsvasby.se",
    "1293": "hassleholm.se",
}


def get_url(kod: str, namn: str) -> str:
    """Get URL for kommun."""
    if kod in URL_OVERRIDES:
        return f"https://{URL_OVERRIDES[kod]}"

    # Generate from name
    url_name = normalize_url_name(namn)
    return f"https://{url_name}.se"


def generate_manifest():
    """Generate the full manifest."""
    tasks = []

    for kod, namn, lan in KOMMUNER:
        task = {
            "id": kod,
            "namn": namn,
            "lan": lan,
            "url": get_url(kod, namn),
            "priority": get_priority(kod),
        }
        tasks.append(task)

    # Sort by priority (highest first), then by name
    tasks.sort(key=lambda x: (-x["priority"], x["namn"]))

    manifest = {
        "total": len(tasks),
        "generated": datetime.now().isoformat(),
        "source": "SCB Län och kommuner i kodnummerordning (2024)",
        "priority_distribution": {
            "5_storstader": len([t for t in tasks if t["priority"] == 5]),
            "4_stora": len([t for t in tasks if t["priority"] == 4]),
            "3_medelstora": len([t for t in tasks if t["priority"] == 3]),
            "2_sma": len([t for t in tasks if t["priority"] == 2]),
        },
        "tasks": tasks,
    }

    return manifest


def main():
    output_path = Path(
        "/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data/kommun_manifest.json"
    )

    print("Generating kommun manifest...")
    manifest = generate_manifest()

    print(f"Total kommuner: {manifest['total']}")
    print(f"Priority distribution: {manifest['priority_distribution']}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_path}")

    # Show first 10 (highest priority)
    print("\nTop 10 kommuner (highest priority):")
    for task in manifest["tasks"][:10]:
        print(f"  [{task['priority']}] {task['namn']} ({task['id']}) - {task['url']}")

    return manifest


if __name__ == "__main__":
    main()
