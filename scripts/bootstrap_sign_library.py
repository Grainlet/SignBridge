from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SIGN_LIBRARY_DIR = BASE_DIR / "sign_library"
INDEX_PATH = SIGN_LIBRARY_DIR / "wlasl_index.json"
METADATA_PATH = SIGN_LIBRARY_DIR / "metadata.json"

WLASL_HF_BASE = "https://huggingface.co/datasets/Voxel51/WLASL/resolve/main/"

STARTER_GLOSSES = {
    "greetings": [
        "hello",
        "good",
        "morning",
        "afternoon",
        "night",
        "goodbye",
        "welcome",
        "nice",
        "meet",
    ],
    "questions": [
        "how",
        "what",
        "who",
        "where",
        "when",
        "why",
        "which",
        "name",
        "you",
        "your",
    ],
    "daily_life": [
        "thank you",
        "please",
        "sorry",
        "yes",
        "no",
        "help",
        "fine",
        "school",
        "go",
        "book",
        "learn",
        "understand",
        "work",
        "home",
        "family",
        "friend",
        "time",
        "today",
        "tomorrow",
        "yesterday",
        "now",
    ],
    "conversations": [
        "see",
        "later",
        "i",
        "me",
        "we",
        "they",
        "want",
        "need",
        "like",
        "love",
        "happy",
        "not",
        "bird",
        "blue",
        "dark",
        "smooth",
        "background",
    ],
}


def probe_duration(video_path: Path) -> tuple[float, int, int]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(proc.stdout)
    vstream = next(s for s in info["streams"] if s.get("codec_type") == "video")
    dur = float(info.get("format", {}).get("duration") or vstream.get("duration") or 2.0)
    return round(dur, 3), int(vstream["width"]), int(vstream["height"])


def main() -> None:
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    signs = []

    for category, glosses in STARTER_GLOSSES.items():
        cat_dir = SIGN_LIBRARY_DIR / category
        cat_dir.mkdir(parents=True, exist_ok=True)
        for gloss in glosses:
            candidates = index.get(gloss, [])
            if not candidates:
                print(f"[skip] gloss '{gloss}' not in WLASL index")
                continue

            slug = gloss.replace(" ", "_")
            dest = cat_dir / f"{slug}.mp4"
            rel_path = f"{category}/{slug}.mp4"

            downloaded = dest.exists() and dest.stat().st_size > 0
            if not downloaded:
                for cand in candidates:
                    url = WLASL_HF_BASE + cand["filepath"]
                    try:
                        urllib.request.urlretrieve(url, str(dest))
                        if dest.exists() and dest.stat().st_size > 1000:
                            downloaded = True
                            break
                    except Exception as exc:
                        print(f"[warn] failed {url}: {exc}")
                        dest.unlink(missing_ok=True)

            if not downloaded:
                print(f"[fail] could not download '{gloss}'")
                continue

            dur, w, h = probe_duration(dest)
            signs.append(
                {
                    "id": f"wlasl_{slug}",
                    "english_phrase": gloss,
                    "asl_gloss": gloss.upper(),
                    "category": category,
                    "video_path": rel_path,
                    "duration": dur,
                    "width": w,
                    "height": h,
                    "dataset": "WLASL (Voxel51/WLASL)",
                    "verified": True,
                }
            )
            print(f"[ok] {rel_path} ({dur}s, {w}x{h})")

    metadata = {
        "version": "1.0",
        "dataset": "WLASL (Word-Level American Sign Language) via Voxel51/WLASL",
        "description": "Verified prerecorded human ASL video library with on-demand WLASL 2000-gloss expansion",
        "signs": signs,
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Saved {len(signs)} starter signs to {METADATA_PATH}")


if __name__ == "__main__":
    main()
