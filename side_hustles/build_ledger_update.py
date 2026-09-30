"""Turn a fresh hustle_rankings.csv into database writes for the Boring Money Ledger.

Usage:
  python3 side_hustles/build_ledger_update.py CURRENT_DIR VERSIONS_TXT OUT_DIR

CURRENT_DIR holds the ledger's current documents as exported by the
ArtifactData tool (`list` with `out_dir`), i.e. CURRENT_DIR/hustles/<id>.json.
VERSIONS_TXT is the text of that same `list` result saved to a file: the
exported files hold only document bodies, and the result text is where each
document's version is printed ("<id>" ... version N, or "<id>" N in the
summary line). Every existing document must have a version or the script stops.

OUT_DIR receives:
  docs/<id>.json         one document body per write
  batch_NN.json          ArtifactData batch `writes` lists (<= 50 entries each)

Only scan-derived fields are written. Fields the viewer owns (status, star,
rating, notes, foundAt, ...) are never included, and existing documents are
written with `update`, pinned to the version that was read, so nothing the
viewer entered is overwritten. Hustles that drop out of a scan are left alone.
"""
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
RANKINGS = HERE / "data" / "hustle_rankings.csv"
VIDEOS = HERE / "data" / "videos.json"
QUERY_COUNT = 22
BATCH = 45  # leaves room for the scan record in the final batch


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def top_videos(field):
    out = []
    for t in field.split(" | "):
        m = re.match(r"(.*) \((https://youtu\.be/\S+), ([\d,]+) views\)$", t)
        if m:
            out.append({"title": m.group(1), "url": m.group(2), "views": int(m.group(3).replace(",", ""))})
    return out


def load_current(current_dir, versions_txt):
    text = Path(versions_txt).read_text()
    versions = {m.group(1): int(m.group(2))
                for m in re.finditer(r'"([A-Za-z0-9_.~:@+-]+)"\s+(?:\d+ bytes\s+)?(?:version\s+)?(\d+)(?=[\s,\]])', text)}
    docs, missing = {}, []
    for f in (Path(current_dir) / "hustles").glob("*.json"):
        if f.stem not in versions:
            missing.append(f.stem)
        docs[f.stem] = {"version": versions.get(f.stem), "data": json.loads(f.read_text())}
    if missing:
        sys.exit(f"No version found in {versions_txt} for: {', '.join(sorted(missing))}")
    return docs


def main(current_dir, versions_txt, out_dir):
    scan = date.today().isoformat()
    out = Path(out_dir)
    (out / "docs").mkdir(parents=True, exist_ok=True)
    current = load_current(current_dir, versions_txt)
    writes, new, updated = [], [], []

    for r in csv.DictReader(RANKINGS.open()):
        doc_id = slug(r["hustle"])
        scanned = {
            "name": r["hustle"], "source": "youtube", "tier": r["tier"],
            "videos": int(r["videos"]), "chapters": int(r["featured_in_chapters"]),
            "views": int(r["total_views"]), "recent": int(r["recent_share"]),
            "unattractive": float(r["unattractive_score"]), "passive": float(r["passive_score"]),
            "combo": float(r["boring_passive_score"]), "opportunity": float(r["opportunity_score"]),
            "topVideos": top_videos(r["top_videos"]), "lastScan": scan,
        }
        point = {"date": scan, "videos": scanned["videos"], "views": scanned["views"]}
        prev = current.get(doc_id)
        if prev:
            hist = [h for h in prev["data"].get("history", []) if h.get("date") != scan]
            scanned["history"] = (hist + [point])[-52:]
            if prev["data"].get("tier") and prev["data"]["tier"] != scanned["tier"]:
                scanned["previousTier"] = prev["data"]["tier"]
            entry = {"op": "update", "collection": "hustles", "doc_id": doc_id,
                     "if_version": prev["version"]}
            updated.append(doc_id)
        else:
            scanned["history"] = [point]
            entry = {"op": "set", "collection": "hustles", "doc_id": doc_id}
            new.append(doc_id)
        path = out / "docs" / f"{doc_id}.json"
        path.write_text(json.dumps(scanned, ensure_ascii=False))
        entry["file_path"] = str(path.resolve())
        writes.append(entry)

    videos = json.loads(VIDEOS.read_text())
    scan_doc = out / "docs" / f"_scan_{scan}.json"
    scan_doc.write_text(json.dumps({
        "date": scan, "videos": len(videos), "queries": QUERY_COUNT,
        "views": sum(v.get("views", 0) for v in videos),
        "newHustles": new,
        "note": "Weekly rescan: titles, descriptions and chapters via YouTube InnerTube search",
    }))
    scan_write = {"op": "set", "collection": "scans", "doc_id": scan, "file_path": str(scan_doc.resolve())}

    batches = [writes[i:i + BATCH] for i in range(0, len(writes), BATCH)] or [[]]
    batches[-1].append(scan_write)
    for i, b in enumerate(batches, 1):
        (out / f"batch_{i:02d}.json").write_text(json.dumps(b, indent=1))
    print(json.dumps({"scan": scan, "updated": len(updated), "new": new,
                      "batches": [str((out / f"batch_{i:02d}.json").resolve()) for i in range(1, len(batches) + 1)]}, indent=1))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
