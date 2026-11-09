"""Stream XES into typed CSVs; verify source bytes before processing."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import urllib.request
import xml.etree.ElementTree as ET

EXPECTED_MD5 = "10b37a2f78e870d78406198403ff13d2"
URLS = [
    "https://ndownloader.figshare.com/files/24044117",
    "https://raw.githubusercontent.com/Patrick-Megard/ProcessMining-Loans/main/Datasets/BPI%20Challenge%202017.xes.gz",
]
APP_COLS = ["application_id", "requested_amount", "application_type", "loan_goal"]
EVENT_COLS = ["application_id", "source_sequence", "event_id", "activity", "lifecycle", "event_time", "origin", "resource", "offer_id", "offered_amount", "accepted", "selected"]


def verify(path):
    digest = hashlib.md5(Path(path).read_bytes()).hexdigest()
    if digest != EXPECTED_MD5:
        raise ValueError(f"Source checksum mismatch: {digest}")
    return digest


def acquire(root):
    raw = root / "data/raw"
    raw.mkdir(parents=True, exist_ok=True)
    target = raw / "bpi2017.xes.gz"
    if not target.exists():
        errors = []
        for url in URLS:
            temp = target.with_suffix(".download")
            try:
                with urllib.request.urlopen(url, timeout=40) as src, temp.open("wb") as out:
                    while block := src.read(1024 * 1024):
                        out.write(block)
                verify(temp)
                temp.replace(target)
                (raw / "download_provenance.json").write_text(json.dumps({"download_url": url, "md5": EXPECTED_MD5}, indent=2))
                break
            except Exception as exc:
                temp.unlink(missing_ok=True)
                errors.append(str(exc))
        else:
            raise RuntimeError("Download failed: " + "; ".join(errors))
    verify(target)
    return target


def attributes(element):
    return {x.get("key"): x.get("value") for x in element if "key" in x.attrib}


def file_sha256(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block:=stream.read(1024*1024):digest.update(block)
    return digest.hexdigest()


def extract_cache_valid(source,processed):
    manifest=Path(processed)/'extraction_manifest.json'
    if not manifest.exists():return False
    try:
        stored=json.loads(manifest.read_text())
        return stored['source_sha256']==file_sha256(source) and all(
            (Path(processed)/name).exists() and file_sha256(Path(processed)/name)==digest
            for name,digest in stored['outputs'].items()) and set(stored['outputs'])=={'applications.csv','events.csv'}
    except (KeyError,ValueError,OSError):return False


def extract(source, processed):
    """Keep original trace ordinal to break timestamp ties without inventing order."""
    processed.mkdir(parents=True, exist_ok=True)
    app_count = event_count = 0
    with (processed / "applications.csv").open("w", newline="") as af, (processed / "events.csv").open("w", newline="") as ef:
        aw, ew = csv.writer(af), csv.writer(ef)
        aw.writerow(APP_COLS)
        ew.writerow(EVENT_COLS)
        with gzip.open(source, "rb") as stream:
            context = ET.iterparse(stream, events=("start", "end"))
            _, document = next(context)
            for kind, trace in context:
                if kind != "end" or trace.tag.rsplit("}", 1)[-1] != "trace":
                    continue
                a = attributes(trace)
                aid = a["concept:name"]
                aw.writerow([aid, a.get("RequestedAmount"), a.get("ApplicationType"), a.get("LoanGoal")])
                app_count += 1
                for ordinal, event in enumerate(x for x in trace if x.tag.rsplit("}", 1)[-1] == "event"):
                    e = attributes(event)
                    activity = e.get("concept:name", "").strip()
                    offer = e.get("OfferID") or (e.get("EventID") if activity == "O_Create Offer" else None)
                    ew.writerow([aid, ordinal, e.get("EventID"), activity, e.get("lifecycle:transition"), e.get("time:timestamp"), e.get("EventOrigin"), e.get("org:resource"), offer, e.get("OfferedAmount"), e.get("Accepted"), e.get("Selected")])
                    event_count += 1
                trace.clear()
                document.clear()
    (processed/'extraction_manifest.json').write_text(json.dumps({
        'source_sha256':file_sha256(source),
        'outputs':{name:file_sha256(processed/name) for name in ['applications.csv','events.csv']}
    },indent=2))
    return {"applications": app_count, "events": event_count}
