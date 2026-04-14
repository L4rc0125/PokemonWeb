from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import difflib
import html
import json
import os
import re
import secrets
import threading
import time
import unicodedata
from urllib.parse import quote, urlparse

import requests
from flask import Flask, Response, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get("POKEMONWEB_SESSION_SECRET", "PokemonWeb-local-session-secret")

BASE_DIR = Path(__file__).resolve().parent
ALL_SPECIES_CACHE_FILE = BASE_DIR / "pokemon_species_cache.json"
FINAL_SPECIES_CACHE_FILE = BASE_DIR / "pokemon_final_species_cache.json"
DETAIL_CACHE_FILE = BASE_DIR / "pokemon_detail_cache.json"
MOVE_DETAIL_CACHE_FILE = BASE_DIR / "pokemon_move_cache.json"
MOVE_USAGE_CACHE_FILE = BASE_DIR / "pokemon_move_usage_cache.json"
FORM_ALIAS_CACHE_FILE = BASE_DIR / "pokemon_form_alias_cache.json"
ABILITY_LIST_CACHE_FILE = BASE_DIR / "pokemon_ability_list_cache.json"
ABILITY_DETAIL_CACHE_FILE = BASE_DIR / "pokemon_ability_detail_cache.json"
ABILITY_DESC_OVERRIDE_FILE = BASE_DIR / "ability_desc.json"
ACCESS_KEY = os.environ.get("POKEMONWEB_ACCESS_KEY", "mFYXkElhk0qvdp8LxIGfgrMpQ-XisfNA")

POKEAPI_BASE = "https://pokeapi.co/api/v2"
POKEDB_SV_BASE = "https://sv.pokedb.tokyo"
SPECIES_LIST_URL = f"{POKEAPI_BASE}/pokemon-species?limit=2000"

DEFAULT_ATTACKER = "ガブリアス"
DEFAULT_DEFENDER = "カイリュー"

TYPE_JP_MAP = {
    "normal": "ノーマル", "fire": "ほのお", "water": "みず", "electric": "でんき",
    "grass": "くさ", "ice": "こおり", "fighting": "かくとう", "poison": "どく",
    "ground": "じめん", "flying": "ひこう", "psychic": "エスパー", "bug": "むし",
    "rock": "いわ", "ghost": "ゴースト", "dragon": "ドラゴン", "dark": "あく",
    "steel": "はがね", "fairy": "フェアリー",
}
MOVE_CLASS_JP_MAP = {"physical": "物理", "special": "特殊", "status": "変化"}

_session = requests.Session()
_session.trust_env = False
_session.headers.update({"User-Agent": "PokemonWeb/2.0"})

state_lock = threading.Lock()
state = {
    "ready": False,
    "building": False,
    "total": 0,
    "done": 0,
    "error": "",
    "message": "初期化待機中",
}

refresh_lock = threading.Lock()
refresh_state = {
    "running": False,
    "total": 0,
    "done": 0,
    "error": "",
    "message": "",
    "started_at": 0.0,
    "finished_at": 0.0,
}

all_species_index: list[dict] = []
pokemon_index: list[dict] = []
detail_cache: dict[str, dict] = {}
move_detail_cache: dict[str, dict] = {}
move_usage_cache: dict[str, dict] = {}
form_alias_cache: dict[str, dict[str, list[str]]] = {}
resource_name_cache: dict[str, str] = {}
name_to_api: dict[str, str] = {}
ability_name_to_api: dict[str, str] = {}
ability_detail_cache: dict[str, dict] = {}
ability_desc_override: dict[str, str] = {}

MIN_VALID_COUNT = 50



SPECIAL_FORM_ALIASES: dict[str, list[str]] = {
    "urshifu-single-strike": [
        "ウーラオス(いちげきのかた)",
        "ウーラオス（いちげきのかた）",
        "ウーラオスいちげき",
        "ウーラオス(いちげき)",
        "ウーラオス（いちげき）",
        "いちげきのかた",
        "いちげき",
    ],
    "urshifu-rapid-strike": [
        "ウーラオス(れんげきのかた)",
        "ウーラオス（れんげきのかた）",
        "ウーラオスれんげき",
        "ウーラオス(れんげき)",
        "ウーラオス（れんげき）",
        "れんげきのかた",
        "れんげき",
    ],
    "zacian-crowned": [
        "ザシアン(けんのおう)",
        "ザシアン（けんのおう）",
        "ザシアンけんのおう",
        "けんのおう",
    ],
    "zamazenta-crowned": [
        "ザマゼンタ(たてのおう)",
        "ザマゼンタ（たてのおう）",
        "ザマゼンタたてのおう",
        "たてのおう",
    ],
    "ursaluna-bloodmoon": [
        "ガチグマ(アカツキ)",
        "ガチグマ（アカツキ）",
        "アカツキガチグマ",
        "ガチグマアカツキ",
    ],
    "calyrex-shadow": [
        "バドレックス(こくばじょう)",
        "バドレックス（こくばじょう）",
        "バドレックスこくばじょう",
        "こくばじょう",
        "黒馬バドレックス",
    ],
    "calyrex-ice": [
        "バドレックス(はくばじょう)",
        "バドレックス（はくばじょう）",
        "バドレックスはくばじょう",
        "はくばじょう",
        "白馬バドレックス",
    ],
    "rotom-heat": [
        "ロトム(ヒート)",
        "ロトム（ヒート）",
        "ロトムヒート",
        "ヒートロトム",
        "ヒート",
    ],
    "rotom-wash": [
        "ロトム(ウォッシュ)",
        "ロトム（ウォッシュ）",
        "ロトムウォッシュ",
        "ウォッシュロトム",
        "ウォッシュ",
    ],
    "rotom-frost": [
        "ロトム(フロスト)",
        "ロトム（フロスト）",
        "ロトムフロスト",
        "フロストロトム",
        "フロスト",
    ],
    "rotom-fan": [
        "ロトム(スピン)",
        "ロトム（スピン）",
        "ロトムスピン",
        "スピンロトム",
        "スピン",
    ],
    "rotom-mow": [
        "ロトム(カット)",
        "ロトム（カット）",
        "ロトムカット",
        "カットロトム",
        "カット",
    ],
}



SPECIAL_FORM_MOVES: dict[str, list[dict[str, object]]] = {
    "zacian-crowned": [
        {"name": "きょじゅうざん", "type": "はがね", "power": 100, "class": "物理", "class_jp": "物理", "damage_class": "physical"},
    ],
    "zamazenta-crowned": [
        {"name": "きょじゅうだん", "type": "はがね", "power": 100, "class": "物理", "class_jp": "物理", "damage_class": "physical"},
    ],
    "calyrex-shadow": [
        {"name": "アストラルビット", "type": "ゴースト", "power": 120, "class": "特殊", "class_jp": "特殊", "damage_class": "special"},
    ],
    "calyrex-ice": [
        {"name": "ブリザードランス", "type": "こおり", "power": 120, "class": "物理", "class_jp": "物理", "damage_class": "physical"},
    ],
}


SPECIAL_FORM_ABILITIES: dict[str, dict[str, object]] = {
    "dragonite-mega": {
        "abilities": [{"name": "マルチスケイル"}],
        "ability_descriptions": {
            "マルチスケイル": "HPが満タンのとき、受けるダメージが半減する"
        },
    },
    "scovillain-mega": {
        "abilities": [{"name": "とびだすハバネロ"}],
        "ability_descriptions": {
            "とびだすハバネロ": "技のダメージを受けると相手をやけどにする"
        },
    },
    "victreebel-mega": {
        "abilities": [{"name": "とびだすなかみ"}],
        "ability_descriptions": {
            "とびだすなかみ": "倒されたとき残りHP分ダメージ"
        },
    },
    "glimmora-mega": {
        "abilities": [{"name": "てきおうりょく"}],
        "ability_descriptions": {
            "てきおうりょく": "タイプ一致技の威力がさらに上がる"
        },
    },
    "starmie-mega": {
        "abilities": [{"name": "ちからもち"}],
        "ability_descriptions": {
            "ちからもち": "こうげきが2倍になる"
        },
    },
    "meowstic-mega": {
        "abilities": [{"name": "トレース"}],
        "ability_descriptions": {
            "トレース": "場に出たとき、相手と同じ特性になる"
        },
    },
    "chandelure-mega": {
        "abilities": [{"name": "すりぬけ"}],
        "ability_descriptions": {
            "すりぬけ": "相手の壁やみがわりなどを無視して攻撃できる"
        },
    },
    "drampa-mega": {
        "abilities": [{"name": "ぎゃくじょう"}],
        "ability_descriptions": {
            "ぎゃくじょう": "HPが半分以下になると、とくこうが上がる"
        },
    },
    "skarmory-mega": {
        "abilities": [{"name": "すじがねいり"}],
        "ability_descriptions": {
            "すじがねいり": "相手の特性の影響を受けずに技を出せる"
        },
    },
    "excadrill-mega": {
        "abilities": [{"name": "かんつうドリル"}],
        "ability_descriptions": {
            "かんつうドリル": "守りを無視して1/4ダメージ"
        },
    },
    "clefable-mega": {
        "abilities": [{"name": "マジックミラー"}],
        "ability_descriptions": {
            "マジックミラー": "相手から受ける変化技を跳ね返す"
        },
    },
    "crabominable-mega": {
        "abilities": [{"name": "てつのこぶし"}],
        "ability_descriptions": {
            "てつのこぶし": "パンチ系の技の威力が上がる"
        },
    },
}


def apply_special_form_overrides(api_name: str, detail: dict) -> dict:
    if not isinstance(detail, dict):
        return detail
    moves = detail.get("moves")
    if not isinstance(moves, list):
        moves = []
        detail["moves"] = moves

    existing = {str((m or {}).get("name") or "").strip() for m in moves if isinstance(m, dict)}
    for move in SPECIAL_FORM_MOVES.get(api_name, []):
        name = str(move.get("name") or "").strip()
        if name and name not in existing:
            moves.append(dict(move))
            existing.add(name)

    moves.sort(
        key=lambda item: (
            -(float((item or {}).get("usage_rate")) if (item or {}).get("usage_rate") is not None else -1.0),
            str((item or {}).get("name") or ""),
        )
    )
    return detail


def apply_special_form_abilities(api_name: str, detail: dict) -> dict:
    if not isinstance(detail, dict):
        return detail

    data = SPECIAL_FORM_ABILITIES.get(api_name)
    if not isinstance(data, dict):
        return detail

    raw_abilities = data.get("abilities")
    abilities: list[str] = []
    if isinstance(raw_abilities, list):
        for item in raw_abilities:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
            else:
                name = str(item or "").strip()
            if name:
                abilities.append(name)
    if abilities:
        detail["abilities"] = abilities

    raw_desc = data.get("ability_descriptions")
    if isinstance(raw_desc, dict):
        detail["ability_descriptions"] = {
            str(k or "").strip(): str(v or "").strip()
            for k, v in raw_desc.items()
            if str(k or "").strip()
        }

    return detail


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_unlink(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except Exception:
        pass


def kana_to_hira(text: str) -> str:
    return "".join(
        chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch
        for ch in str(text or "")
    )


def normalize_text(text: str) -> str:
    text = kana_to_hira(unicodedata.normalize("NFKC", str(text or "")).strip()).lower()
    for ch in (" ", "　", "-", "‐", "‑", "‒", "–", "—", "―", "ー", "・", "/", "(", ")", "（", "）"):
        text = text.replace(ch, "")
    return text


def fetch_json(url: str, timeout: int = 20):
    response = _session.get(url, timeout=timeout)
    response.raise_for_status()
    return response.json()


def proxy_sprite_url(sprite_url: str) -> str:
    sprite_url = str(sprite_url or "").strip()
    if not sprite_url or sprite_url.startswith("/"):
        return sprite_url
    return f"/api/sprite?url={quote(sprite_url, safe='')}"


def local_sprite_url(api_name: str) -> str:
    api_name = str(api_name or "").strip()
    if not api_name:
        return ""
    path = BASE_DIR / "static" / "sprites" / f"{api_name}.png"
    if path.exists():
        return f"/static/sprites/{api_name}.png?v={int(path.stat().st_mtime)}"
    return ""


def cache_sprite_locally(api_name: str, sprite_url: str) -> str:
    api_name = str(api_name or "").strip()
    sprite_url = str(sprite_url or "").strip()
    if not api_name or not sprite_url:
        return ""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", api_name):
        return ""

    cached_url = local_sprite_url(api_name)
    if cached_url:
        return cached_url

    parsed = urlparse(sprite_url)
    if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
        return ""

    try:
        sprite_dir = BASE_DIR / "static" / "sprites"
        sprite_dir.mkdir(parents=True, exist_ok=True)
        response = _session.get(sprite_url, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type") or ""
        if "image" not in content_type.lower():
            return ""
        path = sprite_dir / f"{api_name}.png"
        path.write_bytes(response.content)
        return f"/static/sprites/{api_name}.png"
    except Exception:
        return ""


def pick_japanese_name(name_entries: list[dict]) -> str:
    if not isinstance(name_entries, list):
        return ""
    for lang in ("ja-Hrkt", "ja"):
        for item in name_entries:
            if item.get("language", {}).get("name") == lang and item.get("name"):
                return str(item["name"]).strip()
    return ""


def set_state(**kwargs) -> None:
    with state_lock:
        state.update(kwargs)


def set_refresh_state(**kwargs) -> None:
    with refresh_lock:
        refresh_state.update(kwargs)


def get_refresh_state() -> dict:
    with refresh_lock:
        return dict(refresh_state)


def register_name_alias(mapping: dict[str, str], alias: str, api_name: str) -> None:
    key = normalize_text(alias)
    if key and api_name and key not in mapping:
        mapping[key] = api_name


def rebuild_name_mapping() -> None:
    global name_to_api
    mapping = {}
    for item in pokemon_index:
        jp_name = str(item.get("jp_name") or "").strip()
        api_name = str(item.get("api_name") or "").strip()
        if jp_name and api_name:
            register_name_alias(mapping, jp_name, api_name)
    for alias_map in form_alias_cache.values():
        for api_name, aliases in (alias_map or {}).items():
            for alias in aliases or []:
                register_name_alias(mapping, alias, api_name)
    for api_name, aliases in SPECIAL_FORM_ALIASES.items():
        for alias in aliases:
            register_name_alias(mapping, alias, api_name)
    name_to_api = mapping


def load_ability_desc_override() -> None:
    global ability_desc_override

    data = load_json(ABILITY_DESC_OVERRIDE_FILE, {})
    if not isinstance(data, dict):
        ability_desc_override = {}
        return

    mapping: dict[str, str] = {}
    for raw_key, raw_value in data.items():
        key = normalize_text(str(raw_key or ""))
        value = str(raw_value or "").strip()
        if not key or not value:
            continue
        mapping[key] = value

    ability_desc_override = mapping


def invalidate_bad_caches() -> None:
    for path in (ALL_SPECIES_CACHE_FILE, FINAL_SPECIES_CACHE_FILE):
        data = load_json(path, [])
        if isinstance(data, list) and 0 < len(data) < MIN_VALID_COUNT:
            safe_unlink(path)


def load_caches() -> None:
    global all_species_index, pokemon_index, detail_cache, move_detail_cache, move_usage_cache, form_alias_cache, ability_name_to_api, ability_detail_cache, ability_desc_override

    invalidate_bad_caches()

    all_species_index = load_json(ALL_SPECIES_CACHE_FILE, [])
    pokemon_index = load_json(FINAL_SPECIES_CACHE_FILE, [])
    detail_cache = load_json(DETAIL_CACHE_FILE, {})
    move_detail_cache = load_json(MOVE_DETAIL_CACHE_FILE, {})
    move_usage_cache = load_json(MOVE_USAGE_CACHE_FILE, {})
    form_alias_cache = load_json(FORM_ALIAS_CACHE_FILE, {})
    ability_name_to_api = load_json(ABILITY_LIST_CACHE_FILE, {})
    ability_detail_cache = load_json(ABILITY_DETAIL_CACHE_FILE, {})
    load_ability_desc_override()

    if not isinstance(all_species_index, list):
        all_species_index = []
    if not isinstance(pokemon_index, list):
        pokemon_index = []
    if not isinstance(detail_cache, dict):
        detail_cache = {}
    if not isinstance(move_detail_cache, dict):
        move_detail_cache = {}
    if not isinstance(move_usage_cache, dict):
        move_usage_cache = {}
    if not isinstance(form_alias_cache, dict):
        form_alias_cache = {}
    if not isinstance(ability_name_to_api, dict):
        ability_name_to_api = {}
    if not isinstance(ability_detail_cache, dict):
        ability_detail_cache = {}

    rebuild_name_mapping()

    if pokemon_index:
        set_state(
            ready=True,
            building=False,
            total=len(pokemon_index),
            done=len(pokemon_index),
            error="",
            message=f"キャッシュ読み込み済み（最終進化のみ: {len(pokemon_index)}件）",
        )


def build_species_entry(species_url: str) -> dict | None:
    try:
        data = fetch_json(species_url, timeout=20)
        jp_name = pick_japanese_name(data.get("names", []))
        species_name = str(data.get("name") or "").strip()
        if not jp_name or not species_name:
            return None

        default_api_name = ""
        for v in data.get("varieties", []) or []:
            if v.get("is_default"):
                default_api_name = str((v.get("pokemon") or {}).get("name") or "").strip()
                break
        if not default_api_name and (data.get("varieties") or []):
            default_api_name = str((((data.get("varieties") or [])[0]).get("pokemon") or {}).get("name") or "").strip()

        return {
            "jp_name": jp_name,
            "species_name": species_name,
            "api_name": default_api_name or species_name,
            "species_url": species_url,
            "evolution_chain_url": str(((data.get("evolution_chain") or {}).get("url")) or "").strip(),
        }
    except Exception:
        return None


def build_all_species_index() -> None:
    global all_species_index

    if all_species_index:
        return

    set_state(building=True, ready=False, total=0, done=0, error="", message="全ポケモン種族一覧を取得中")
    data = fetch_json(SPECIES_LIST_URL, timeout=30)
    results = data.get("results", [])
    total = len(results)
    set_state(total=total, done=0, message="全ポケモン種族一覧を構築中")

    entries = []
    seen = set()

    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(build_species_entry, item["url"]): item for item in results if item.get("url")}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            set_state(done=done_count, message=f"種族一覧を構築中 {done_count}/{total}")
            entry = future.result()
            if not entry:
                continue
            key = normalize_text(entry["jp_name"])
            if not key or key in seen:
                continue
            seen.add(key)
            entries.append(entry)

    entries.sort(key=lambda x: x["jp_name"])
    if len(entries) < MIN_VALID_COUNT:
        raise RuntimeError(f"全種族一覧が少なすぎます: {len(entries)}件")

    all_species_index = entries
    save_json(ALL_SPECIES_CACHE_FILE, all_species_index)


def get_leaf_species_names(node: dict) -> set[str]:
    if not isinstance(node, dict):
        return set()
    children = node.get("evolves_to", []) or []
    if not children:
        species_name = str((node.get("species") or {}).get("name") or "").strip()
        return {species_name} if species_name else set()
    leaves = set()
    for child in children:
        leaves.update(get_leaf_species_names(child))
    return leaves


def is_final_species(species_entry: dict) -> bool:
    try:
        species_name = str(species_entry.get("species_name") or "").strip()
        chain_url = str(species_entry.get("evolution_chain_url") or "").strip()

        if not chain_url:
            return True

        chain_data = fetch_json(chain_url, timeout=20)
        leaf_species = get_leaf_species_names(chain_data.get("chain") or {})
        if not leaf_species:
            return True
        return species_name in leaf_species
    except Exception:
        return True


def build_final_index() -> None:
    global pokemon_index

    if pokemon_index:
        return
    if not all_species_index:
        build_all_species_index()

    set_state(
        building=True,
        ready=False,
        total=len(all_species_index),
        done=0,
        error="",
        message="最終進化だけに絞り込み中",
    )

    final_entries = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(is_final_species, item): item for item in all_species_index}
        done_count = 0
        for future in as_completed(futures):
            done_count += 1
            set_state(done=done_count, message=f"最終進化判定中 {done_count}/{len(all_species_index)}")
            item = futures[future]
            keep = future.result()
            if keep:
                final_entries.append({
                    "jp_name": item["jp_name"],
                    "api_name": item["api_name"],
                    "species_name": item["species_name"],
                })

    final_entries.sort(key=lambda x: x["jp_name"])
    if len(final_entries) < MIN_VALID_COUNT:
        raise RuntimeError(f"最終進化の件数が少なすぎます: {len(final_entries)}件")

    pokemon_index = final_entries
    save_json(FINAL_SPECIES_CACHE_FILE, pokemon_index)
    rebuild_name_mapping()

    set_state(
        ready=True,
        building=False,
        total=len(pokemon_index),
        done=len(pokemon_index),
        error="",
        message=f"準備完了（最終進化のみ: {len(pokemon_index)}件）",
    )


def ensure_ready_async() -> None:
    with state_lock:
        if state.get("ready") or state.get("building"):
            return
        state["building"] = True
        state["message"] = "バックグラウンド準備開始"

    def worker():
        try:
            if not all_species_index:
                build_all_species_index()
            if not pokemon_index:
                build_final_index()
        except Exception as e:
            set_state(
                ready=False,
                building=False,
                error=str(e),
                message="初期化に失敗しました",
            )
        finally:
            with state_lock:
                if state.get("ready"):
                    state["building"] = False

    threading.Thread(target=worker, daemon=True).start()


def localize_resource_name(resource_url: str) -> str:
    cached = resource_name_cache.get(resource_url)
    if cached:
        return cached
    try:
        data = fetch_json(resource_url, timeout=20)
        jp_name = pick_japanese_name(data.get("names", []))
        if not jp_name:
            jp_name = str(data.get("name") or "").strip()
        resource_name_cache[resource_url] = jp_name
        return jp_name
    except Exception:
        return ""


def build_move_entry(move_data: dict) -> dict:
    damage_class_en = str((move_data.get("damage_class") or {}).get("name") or "").strip()
    return {
        "name": pick_japanese_name(move_data.get("names", [])) or str(move_data.get("name") or "").strip(),
        "type": TYPE_JP_MAP.get(str((move_data.get("type") or {}).get("name") or ""), ""),
        "power": move_data.get("power"),
        "class": MOVE_CLASS_JP_MAP.get(damage_class_en, ""),
        "class_jp": MOVE_CLASS_JP_MAP.get(damage_class_en, ""),
        "damage_class": damage_class_en,
    }


def get_move_entry(move_url: str, *, force_refresh: bool = False) -> tuple[dict | None, bool]:
    cached = move_detail_cache.get(move_url)
    if (not force_refresh) and isinstance(cached, dict) and cached.get("name"):
        return dict(cached), False

    try:
        move_data = fetch_json(move_url, timeout=20)
    except Exception:
        return None, False

    move_entry = build_move_entry(move_data)
    if not move_entry.get("name"):
        return None, False

    move_detail_cache[move_url] = move_entry
    return dict(move_entry), True


def is_mega_api_name(api_name: str) -> bool:
    name = str(api_name or "").strip().lower()
    return bool(re.fullmatch(r"[a-z0-9-]+-mega(?:-[xy])?", name))


def get_mega_base_api_name(api_name: str) -> str:
    name = str(api_name or "").strip().lower()
    if not is_mega_api_name(name):
        return name
    return re.sub(r"-mega(?:-[xy])?$", "", name)


def parse_pokedb_move_usage_html(page_html: str) -> dict[str, float]:
    page_html = str(page_html or "")
    usage: dict[str, float] = {}

    for item_html in re.findall(r'<div class="pokemon-move-list-item">(.*?)</div>\s*</div>\s*<span class="pokemon-move-rate">', page_html, re.S):
        name_match = re.search(r'<span class="pokemon-move-name">(.*?)</span>', item_html, re.S)
        if not name_match:
            continue
        name = html.unescape(name_match.group(1))
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            continue

    for name_match, rate_match in re.findall(
        r'<span class="pokemon-move-name">(.*?)</span>.*?<span class="pokemon-move-rate">\s*([0-9]+(?:\.[0-9]+)?)\s*<small>%</small>\s*</span>',
        page_html,
        re.S,
    ):
        name = html.unescape(name_match)
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            continue
        usage[name] = float(rate_match)

    return usage


def get_pokedb_move_usage(dex_no: int, *, rule: int = 0, force_refresh: bool = False) -> dict[str, float]:
    cache_key = f"{int(dex_no):04d}-00|{int(rule)}"
    cached = move_usage_cache.get(cache_key)
    if (not force_refresh) and isinstance(cached, dict) and cached.get("moves"):
        return {
            str(name): float(rate)
            for name, rate in (cached.get("moves") or {}).items()
            if str(name or "").strip()
        }

    try:
        page_html = _session.get(
            f"{POKEDB_SV_BASE}/pokemon/show/{int(dex_no):04d}-00?rule={int(rule)}",
            timeout=20,
        ).text
        moves = parse_pokedb_move_usage_html(page_html)
    except Exception:
        moves = {}

    move_usage_cache[cache_key] = {"moves": moves, "updated_at": int(time.time())}
    save_json(MOVE_USAGE_CACHE_FILE, move_usage_cache)
    return dict(moves)


def sort_moves_by_usage(moves: list[dict], usage_map: dict[str, float]) -> list[dict]:
    usage_map = {str(name or "").strip(): float(rate) for name, rate in (usage_map or {}).items()}
    enriched = []
    for move in moves or []:
        item = dict(move or {})
        name = str(item.get("name") or "").strip()
        item["usage_rate"] = usage_map.get(name)
        enriched.append(item)
    return sorted(
        enriched,
        key=lambda item: (
            -(float(item["usage_rate"]) if item.get("usage_rate") is not None else -1.0),
            str(item.get("name") or ""),
        ),
    )




def build_ability_name_mapping() -> None:
    global ability_name_to_api
    if ability_name_to_api:
        return

    mapping: dict[str, str] = {}
    try:
        data = fetch_json(f"{POKEAPI_BASE}/ability?limit=2000", timeout=30)
        for item in data.get("results", []) or []:
            api_name = str(item.get("name") or "").strip()
            url = str(item.get("url") or "").strip()
            if not api_name or not url:
                continue
            try:
                ability_data = fetch_json(url, timeout=20)
            except Exception:
                continue

            aliases = []
            jp_name = pick_japanese_name(ability_data.get("names", []))
            if jp_name:
                aliases.append(jp_name)
            aliases.extend([api_name, api_name.replace("-", ""), api_name.replace("-", " ")])

            for alias in aliases:
                key = normalize_text(alias)
                if key and key not in mapping:
                    mapping[key] = api_name
    except Exception:
        mapping = {}

    ability_name_to_api = mapping
    save_json(ABILITY_LIST_CACHE_FILE, ability_name_to_api)
    load_ability_desc_override()


def localize_ability_description(api_name: str) -> str:
    override = ability_desc_override.get(normalize_text(api_name), "")

    cached = ability_detail_cache.get(api_name)
    if isinstance(cached, dict) and cached.get("description") and not override:
        return str(cached["description"])

    try:
        data = fetch_json(f"{POKEAPI_BASE}/ability/{api_name}", timeout=25)
    except Exception:
        return override or ""

    override = override or ability_desc_override.get(
        normalize_text(pick_japanese_name(data.get("names", []))), ""
    )
    if override:
        return override

    description = ""
    for lang in ("ja-Hrkt", "ja"):
        for item in data.get("flavor_text_entries", []) or []:
            if (item.get("language") or {}).get("name") == lang and item.get("flavor_text"):
                description = str(item["flavor_text"]).replace("\n", " ").replace("\f", " ").strip()
                break
        if description:
            break

    if not description:
        for item in data.get("effect_entries", []) or []:
            if (item.get("language") or {}).get("name") == "en" and item.get("short_effect"):
                description = str(item["short_effect"]).replace("\n", " ").replace("\f", " ").strip()
                break

    ability_detail_cache[api_name] = {"description": description}
    save_json(ABILITY_DETAIL_CACHE_FILE, ability_detail_cache)
    return description


def resolve_ability_api_name(name: str) -> str:
    build_ability_name_mapping()
    return ability_name_to_api.get(normalize_text(name), "")


def strip_form_markers(name: str) -> str:
    s = normalize_text(name)
    s = s.removeprefix("メガ")
    s = s.removeprefix("ゲンシ")
    for suffix in ("アローラ", "ガラル", "ヒスイ", "パルデア"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    if s.endswith("x") or s.endswith("ｘ") or s.endswith("X"):
        s = s[:-1]
    if s.endswith("y") or s.endswith("ｙ") or s.endswith("Y"):
        s = s[:-1]
    return normalize_text(s)


def infer_form_aliases(base_jp_name: str, api_name: str, form_names: list[str], is_default: bool) -> list[str]:
    aliases: list[str] = []
    base = str(base_jp_name or "").strip()
    api = str(api_name or "").strip()
    if not base or not api:
        return aliases

    if is_default:
        aliases.append(base)

    lower_api = api.lower()
    suffix = ""
    species_api = lower_api.split("-")[0]
    if lower_api.startswith(species_api + "-"):
        suffix = lower_api[len(species_api) + 1 :]

    normalized_forms = [str(x or "").strip() for x in form_names if str(x or "").strip()]

    def add(*items: str) -> None:
        for item in items:
            item = str(item or "").strip()
            if item and item not in aliases:
                aliases.append(item)

    for label in normalized_forms:
        add(label, f"{base}（{label}）", f"{base}({label})")
        plain = label.replace("のすがた", "").replace("の姿", "").strip()
        if plain and plain != label:
            add(plain, f"{base}{plain}", f"{base}（{plain}）", f"{base}({plain})")
        if "メガ" in label:
            if "x" in label.lower() or "ｘ" in label.lower():
                add(f"メガ{base}X", f"メガ{base}Ｘ", f"{base}メガX", f"{base}（メガX）", f"{base}(メガX)")
            elif "y" in label.lower() or "ｙ" in label.lower():
                add(f"メガ{base}Y", f"メガ{base}Ｙ", f"{base}メガY", f"{base}（メガY）", f"{base}(メガY)")
            else:
                add(f"メガ{base}", f"{base}メガ", f"{base}（メガ）", f"{base}(メガ)")
        if "ゲンシ" in label:
            add(f"ゲンシ{base}", f"{base}（ゲンシ）", f"{base}(ゲンシ)")
        for region in ("アローラ", "ガラル", "ヒスイ", "パルデア"):
            if region in label:
                add(f"{base}{region}", f"{base}（{region}）", f"{base}({region})")

    if suffix:
        if "mega-x" in suffix:
            add(f"メガ{base}X", f"メガ{base}Ｘ", f"{base}（メガX）", f"{base}(メガX)")
        elif "mega-y" in suffix:
            add(f"メガ{base}Y", f"メガ{base}Ｙ", f"{base}（メガY）", f"{base}(メガY)")
        elif "mega" in suffix:
            add(f"メガ{base}", f"{base}（メガ）", f"{base}(メガ)")
        if "primal" in suffix:
            add(f"ゲンシ{base}", f"{base}（ゲンシ）", f"{base}(ゲンシ)")
        for region, token in (("アローラ", "alola"), ("ガラル", "galar"), ("ヒスイ", "hisui"), ("パルデア", "paldea")):
            if token in suffix:
                add(f"{base}{region}", f"{base}（{region}）", f"{base}({region})")
        if "single-strike" in suffix:
            add(
                f"{base}(いちげきのかた)", f"{base}（いちげきのかた）",
                f"{base}(いちげき)", f"{base}（いちげき）",
                f"{base}いちげき", "いちげきのかた", "いちげき",
            )
        if "rapid-strike" in suffix:
            add(
                f"{base}(れんげきのかた)", f"{base}（れんげきのかた）",
                f"{base}(れんげき)", f"{base}（れんげき）",
                f"{base}れんげき", "れんげきのかた", "れんげき",
            )

    if not aliases:
        add(base)
    return aliases


def build_form_aliases_for_species(species_entry: dict) -> dict[str, list[str]]:
    species_url = str(species_entry.get("species_url") or "").strip()
    base_jp_name = str(species_entry.get("jp_name") or "").strip()
    if not species_url or not base_jp_name:
        return {}

    species_name = str(species_entry.get("species_name") or "").strip()
    cache_key = species_name or base_jp_name
    cached = form_alias_cache.get(cache_key)
    if isinstance(cached, dict) and cached:
        return cached

    species_data = fetch_json(species_url, timeout=25)
    alias_map: dict[str, list[str]] = {}

    for variety in species_data.get("varieties", []) or []:
        pokemon_ref = variety.get("pokemon") or {}
        api_name = str(pokemon_ref.get("name") or "").strip()
        if not api_name:
            continue

        form_names: list[str] = []
        try:
            pokemon_data = fetch_json(f"{POKEAPI_BASE}/pokemon/{api_name}", timeout=25)
            for form in pokemon_data.get("forms", []) or []:
                form_url = str(form.get("url") or "").strip()
                if not form_url:
                    continue
                form_data = fetch_json(form_url, timeout=20)
                jp_form_name = pick_japanese_name(form_data.get("names", []))
                if jp_form_name:
                    form_names.append(jp_form_name)
        except Exception:
            pass

        alias_map[api_name] = infer_form_aliases(base_jp_name, api_name, form_names, bool(variety.get("is_default")))

    if alias_map:
        form_alias_cache[cache_key] = alias_map
        save_json(FORM_ALIAS_CACHE_FILE, form_alias_cache)
        rebuild_name_mapping()
    return alias_map


def find_species_entry_by_name(jp_name: str) -> dict | None:
    target = strip_form_markers(jp_name)
    if not target:
        return None
    for item in all_species_index:
        if strip_form_markers(item.get("jp_name") or "") == target:
            return item
    return None


def resolve_api_name_from_query(jp_name: str) -> str:
    query_key = normalize_text(jp_name)

    api_name = name_to_api.get(query_key)
    if api_name:
        return api_name

    for special_api_name, aliases in SPECIAL_FORM_ALIASES.items():
        if query_key in {normalize_text(alias) for alias in aliases}:
            return special_api_name

    species_entry = find_species_entry_by_name(jp_name)
    if not species_entry:
        return ""

    alias_map = build_form_aliases_for_species(species_entry)
    query_key = normalize_text(jp_name)

    for api_name, aliases in alias_map.items():
        for alias in aliases or []:
            if normalize_text(alias) == query_key:
                return api_name

    stripped_query = strip_form_markers(jp_name)
    for api_name, aliases in alias_map.items():
        for alias in aliases or []:
            if strip_form_markers(alias) == stripped_query:
                return api_name

    default_api_name = str(species_entry.get("api_name") or "").strip()
    return default_api_name


def build_pokemon_detail(
    api_name: str,
    jp_name: str,
    *,
    force_refresh: bool = False,
    save_cache: bool = True,
) -> dict:
    cached = detail_cache.get(api_name)
    cached_ready = (
        isinstance(cached, dict)
        and cached.get("moves")
        and cached.get("abilities")
        and cached.get("dex_no")
        and any((move or {}).get("usage_rate") is not None for move in (cached.get("moves") or []))
    )
    if (not force_refresh) and cached_ready:
        cached = apply_special_form_overrides(api_name, dict(cached))
        cached = apply_special_form_abilities(api_name, cached)
        detail_cache[api_name] = cached
        if save_cache:
            save_json(DETAIL_CACHE_FILE, detail_cache)
        return cached

    lookup_api_name = api_name
    pokemon_data = None
    try:
        pokemon_data = fetch_json(f"{POKEAPI_BASE}/pokemon/{lookup_api_name}", timeout=25)
    except Exception:
        base_api_name = get_mega_base_api_name(api_name)
        if base_api_name and base_api_name != api_name:
            lookup_api_name = base_api_name
            pokemon_data = fetch_json(f"{POKEAPI_BASE}/pokemon/{lookup_api_name}", timeout=25)
        else:
            raise

    base_move_api_name = get_mega_base_api_name(api_name)
    move_source_data = pokemon_data
    if base_move_api_name and base_move_api_name != lookup_api_name:
        try:
            move_source_data = fetch_json(f"{POKEAPI_BASE}/pokemon/{base_move_api_name}", timeout=25)
        except Exception:
            move_source_data = pokemon_data

    sprite = (
        ((pokemon_data.get("sprites") or {}).get("front_default"))
        or ((((pokemon_data.get("sprites") or {}).get("other") or {}).get("official-artwork") or {}).get("front_default"))
        or ""
    )

    abilities = []
    ability_descriptions: dict[str, str] = {}
    for item in pokemon_data.get("abilities", []):
        ability_info = item.get("ability") or {}
        ability_url = ability_info.get("url")
        ability_api_name = str(ability_info.get("name") or "").strip()
        ability_name = localize_resource_name(ability_url) if ability_url else ""
        if ability_name:
            abilities.append(ability_name)
            if ability_api_name:
                ability_descriptions[ability_name] = localize_ability_description(ability_api_name)
    abilities = list(dict.fromkeys(abilities))

    move_entries = []
    unique_move_urls = []
    seen_urls = set()
    for item in move_source_data.get("moves", []):
        move = item.get("move") or {}
        move_url = move.get("url")
        if move_url and move_url not in seen_urls:
            seen_urls.add(move_url)
            unique_move_urls.append(move_url)

    move_cache_changed = False

    def read_move(move_url: str) -> dict | None:
        nonlocal move_cache_changed
        move_entry, changed = get_move_entry(move_url)
        if changed:
            move_cache_changed = True
        return move_entry

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(read_move, url) for url in unique_move_urls]
        for future in as_completed(futures):
            result = future.result()
            if result and result.get("name"):
                move_entries.append(result)

    if move_cache_changed:
        save_json(MOVE_DETAIL_CACHE_FILE, move_detail_cache)

    dex_no = int(pokemon_data.get("id") or 0)
    if dex_no > 0:
        move_entries = sort_moves_by_usage(move_entries, get_pokedb_move_usage(dex_no))
    else:
        move_entries.sort(key=lambda x: x["name"])

    type_names = []
    for item in sorted(pokemon_data.get("types", []), key=lambda x: int(x.get("slot", 0))):
        en = str((item.get("type") or {}).get("name") or "")
        type_names.append(TYPE_JP_MAP.get(en, en))

    stat_map = {
        "hp": 0,
        "attack": 0,
        "defense": 0,
        "special-attack": 0,
        "special-defense": 0,
        "speed": 0,
    }
    for item in pokemon_data.get("stats", []) or []:
        stat_name = str((item.get("stat") or {}).get("name") or "").strip()
        if stat_name in stat_map:
            stat_map[stat_name] = int(item.get("base_stat") or 0)

    def calc_actual_stat(base: int, *, is_hp: bool = False, level: int = 50, iv: int = 31, ev: int = 0, nature: float = 1.0) -> int:
        if is_hp:
            return int(((base * 2 + iv + ev // 4) * level) / 100) + level + 10
        return int((int(((base * 2 + iv + ev // 4) * level) / 100) + 5) * nature)

    detail = {
        "jp_name": jp_name,
        "api_name": api_name,
        "dex_no": dex_no,
        "sprite": sprite,
        "abilities": abilities,
        "ability_descriptions": ability_descriptions,
        "moves": move_entries,
        "types": type_names,
        "stats": {
            "hp": calc_actual_stat(stat_map["hp"], is_hp=True),
            "attack": calc_actual_stat(stat_map["attack"]),
            "defense": calc_actual_stat(stat_map["defense"]),
            "special_attack": calc_actual_stat(stat_map["special-attack"]),
            "special_defense": calc_actual_stat(stat_map["special-defense"]),
            "speed": calc_actual_stat(stat_map["speed"]),
        },
    }
    detail = apply_special_form_overrides(api_name, detail)
    detail = apply_special_form_abilities(api_name, detail)
    detail_cache[api_name] = detail
    if save_cache:
        save_json(DETAIL_CACHE_FILE, detail_cache)
    return detail


def refresh_all_pokemon_details() -> None:
    if not pokemon_index:
        if not all_species_index:
            build_all_species_index()
        build_final_index()

    targets = [
        {
            "jp_name": str(item.get("jp_name") or "").strip(),
            "api_name": str(item.get("api_name") or "").strip(),
        }
        for item in pokemon_index
        if str(item.get("jp_name") or "").strip() and str(item.get("api_name") or "").strip()
    ]

    total = len(targets)
    set_refresh_state(
        running=True,
        total=total,
        done=0,
        error="",
        message="PokeAPI から再取得中",
        started_at=time.time(),
        finished_at=0.0,
    )

    try:
        for idx, item in enumerate(targets, start=1):
            build_pokemon_detail(item["api_name"], item["jp_name"], force_refresh=True, save_cache=False)
            if idx % 20 == 0:
                save_json(DETAIL_CACHE_FILE, detail_cache)
            set_refresh_state(
                running=True,
                total=total,
                done=idx,
                error="",
                message=f"更新中 {idx}/{total}: {item['jp_name']}",
            )
        save_json(DETAIL_CACHE_FILE, detail_cache)
        set_refresh_state(
            running=False,
            total=total,
            done=total,
            error="",
            message=f"更新完了 ({total}件)",
            finished_at=time.time(),
        )
    except Exception as e:
        current = get_refresh_state()
        set_refresh_state(
            running=False,
            total=total,
            done=int(current.get("done") or 0),
            error=str(e),
            message=f"更新失敗: {e}",
            finished_at=time.time(),
        )
        raise


def start_refresh_all_pokemon_details() -> bool:
    with refresh_lock:
        if refresh_state.get("running"):
            return False
        refresh_state.update({
            "running": True,
            "total": 0,
            "done": 0,
            "error": "",
            "message": "更新を開始します",
            "started_at": time.time(),
            "finished_at": 0.0,
        })

    def worker():
        try:
            refresh_all_pokemon_details()
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()
    return True


@app.before_request
def require_access_key():
    if public_access_enabled():
        return None

    key = str(request.args.get("key") or "")
    if key and secrets.compare_digest(key, ACCESS_KEY):
        session["pokemonweb_allowed"] = True

    if session.get("pokemonweb_allowed"):
        return None

    return Response(
        "このページは限定公開です。配布されたURLから開いてください。",
        status=403,
        mimetype="text/plain; charset=utf-8",
    )


@app.route("/")
def index():
    ensure_ready_async()
    pokemon_options = all_species_index or pokemon_index
    return render_template(
        "index.html",
        default_attacker=DEFAULT_ATTACKER,
        default_defender=DEFAULT_DEFENDER,
        pokemon_options=pokemon_options,
    )


@app.get("/api/status")
def api_status():
    with state_lock:
        return jsonify(dict(state))


@app.get("/api/refresh-all-status")
def api_refresh_all_status():
    return jsonify(get_refresh_state())


@app.post("/api/refresh-all")
def api_refresh_all():
    started = start_refresh_all_pokemon_details()
    status = get_refresh_state()
    return jsonify(status), (202 if started else 200)



@app.get("/api/pokemon-list")
def api_pokemon_list():
    if not all_species_index:
        ensure_ready_async()
    pokemon = all_species_index or pokemon_index
    return jsonify({"ready": bool(pokemon), "pokemon": pokemon})


@app.get("/api/pokemon-search")
def api_pokemon_search():
    query = str(request.args.get("q") or "").strip()
    if not all_species_index:
        ensure_ready_async()

    pokemon = all_species_index or pokemon_index
    query_key = normalize_text(query)
    limit = 20

    if not query_key:
        return jsonify({"ready": bool(pokemon), "pokemon": pokemon[:limit]})

    starts = []
    contains = []
    seen = set()

    for item in pokemon:
        jp_name = str(item.get("jp_name") or "").strip()
        if not jp_name:
            continue
        aliases = [
            jp_name,
            str(item.get("api_name") or "").strip(),
            str(item.get("species_name") or "").strip(),
        ]
        alias_keys = [normalize_text(alias) for alias in aliases if alias]
        if not alias_keys:
            continue
        item_key = normalize_text(jp_name)
        if item_key in seen:
            continue

        if any(key.startswith(query_key) for key in alias_keys):
            starts.append(item)
            seen.add(item_key)
        elif any(query_key in key for key in alias_keys):
            contains.append(item)
            seen.add(item_key)

    return jsonify({"ready": bool(pokemon), "pokemon": (starts + contains)[:limit]})


@app.get("/api/pokemon-detail")
def api_pokemon_detail():
    jp_name = str(request.args.get("name") or "").strip()
    refresh = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not jp_name:
        return jsonify({"error": "name is required"}), 400

    api_name = resolve_api_name_from_query(jp_name)
    if not api_name:
        return jsonify({"error": "そのポケモンは見つかりませんでした"}), 404

    try:
        detail = build_pokemon_detail(api_name, jp_name, force_refresh=refresh)
        detail = dict(detail)
        sprite_url = str(detail.get("sprite") or "")
        detail["sprite"] = (
            local_sprite_url(api_name)
            or cache_sprite_locally(api_name, sprite_url)
            or proxy_sprite_url(sprite_url)
        )
        detail["refreshed"] = refresh
        return jsonify(detail)
    except Exception as e:
        return jsonify({"error": f"詳細取得失敗: {e}"}), 500


@app.get("/api/sprite")
def api_sprite():
    url = str(request.args.get("url") or "").strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc not in {"raw.githubusercontent.com", "rawcdn.githack.com"}:
        return jsonify({"error": "unsupported sprite url"}), 400

    try:
        response = _session.get(url, timeout=15)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type") or "image/png"
        return Response(response.content, mimetype=content_type)
    except Exception as e:
        return jsonify({"error": f"sprite取得失敗: {e}"}), 502


@app.get("/api/pokemon-forms")
def api_pokemon_forms():
    jp_name = str(request.args.get("name") or "").strip()
    if not jp_name:
        return jsonify({"error": "name is required"}), 400

    try:
        species_entry = find_species_entry_by_name(jp_name)
        if not species_entry:
            return jsonify({"forms": [jp_name]})

        alias_map = build_form_aliases_for_species(species_entry)
        forms: list[str] = []
        seen = set()

        def add(name: str) -> None:
            key = normalize_text(name)
            if name and key and key not in seen:
                seen.add(key)
                forms.append(name)

        base_name = str(species_entry.get("jp_name") or "").strip()
        add(base_name)

        preferred = [
            f"{base_name}アローラ", f"{base_name}ガラル", f"{base_name}ヒスイ", f"{base_name}パルデア",
            f"メガ{base_name}", f"メガ{base_name}X", f"メガ{base_name}Y", f"ゲンシ{base_name}",
        ]
        for name in preferred:
            for aliases in alias_map.values():
                for alias in aliases or []:
                    if normalize_text(alias) == normalize_text(name):
                        add(alias)

        for aliases in alias_map.values():
            for alias in aliases or []:
                add(alias)

        if base_name == "ウーラオス":
            add("ウーラオス(いちげきのかた)")
            add("ウーラオス(れんげきのかた)")
            add("ウーラオス（いちげきのかた）")
            add("ウーラオス（れんげきのかた）")
        if base_name == "ザシアン":
            add("ザシアン(けんのおう)")
            add("ザシアン（けんのおう）")
        if base_name == "ザマゼンタ":
            add("ザマゼンタ(たてのおう)")
            add("ザマゼンタ（たてのおう）")
        if base_name == "ガチグマ":
            add("ガチグマ(アカツキ)")
            add("ガチグマ（アカツキ）")
            add("アカツキガチグマ")
        if base_name == "バドレックス":
            add("バドレックス(こくばじょう)")
            add("バドレックス（こくばじょう）")
            add("バドレックス(はくばじょう)")
            add("バドレックス（はくばじょう）")
        if base_name == "ロトム":
            add("ロトム(ヒート)")
            add("ロトム（ヒート）")
            add("ロトム(ウォッシュ)")
            add("ロトム（ウォッシュ）")
            add("ロトム(フロスト)")
            add("ロトム（フロスト）")
            add("ロトム(スピン)")
            add("ロトム（スピン）")
            add("ロトム(カット)")
            add("ロトム（カット）")

        def form_order(name: str):
            label = "通常"
            s = str(name or "").strip()
            if s.startswith("メガ"):
                if s.endswith(("X", "Ｘ", "x", "ｘ")):
                    label = "メガX"
                elif s.endswith(("Y", "Ｙ", "y", "ｙ")):
                    label = "メガY"
                else:
                    label = "メガ"
            elif s.startswith("ゲンシ"):
                label = "ゲンシ"
            elif "けんのおう" in s:
                label = "けんのおう"
            elif "たてのおう" in s:
                label = "たてのおう"
            elif "アカツキ" in s:
                label = "アカツキ"
            elif "こくばじょう" in s:
                label = "こくばじょう"
            elif "はくばじょう" in s:
                label = "はくばじょう"
            elif "ヒート" in s:
                label = "ヒート"
            elif "ウォッシュ" in s:
                label = "ウォッシュ"
            elif "フロスト" in s:
                label = "フロスト"
            elif "スピン" in s:
                label = "スピン"
            elif "カット" in s:
                label = "カット"
            elif "アローラ" in s:
                label = "アローラ"
            elif "ガラル" in s:
                label = "ガラル"
            elif "ヒスイ" in s:
                label = "ヒスイ"
            elif "パルデア" in s:
                label = "パルデア"
            order = ["通常", "けんのおう", "たてのおう", "こくばじょう", "はくばじょう", "アカツキ", "ヒート", "ウォッシュ", "フロスト", "スピン", "カット", "いちげきのかた", "れんげきのかた", "いちげき", "れんげき", "アローラ", "ガラル", "ヒスイ", "パルデア", "メガ", "メガX", "メガY", "ゲンシ"]
            idx = order.index(label) if label in order else 999
            return (idx, name)

        forms = sorted(forms, key=form_order)
        return jsonify({"forms": forms, "base_name": base_name})
    except Exception as e:
        return jsonify({"error": f"フォーム取得失敗: {e}"}), 500


@app.get("/api/ability")
def api_ability():
    jp_name = str(request.args.get("name") or "").strip()
    if not jp_name:
        return jsonify({"error": "name is required"}), 400

    build_ability_name_mapping()
    if not ability_desc_override:
        load_ability_desc_override()

    api_name = resolve_ability_api_name(jp_name)
    if not api_name:
        return jsonify({"error": "その特性は見つかりませんでした"}), 404

    override_desc = (
        ability_desc_override.get(normalize_text(jp_name), "")
        or ability_desc_override.get(normalize_text(api_name), "")
    )
    if override_desc:
        return jsonify({"name": jp_name, "api_name": api_name, "description": override_desc})

    description = localize_ability_description(api_name)
    return jsonify({"name": jp_name, "api_name": api_name, "description": description})

TYPE_EFFECTIVENESS = {
    "ノーマル": {"いわ": 0.5, "ゴースト": 0, "はがね": 0.5},
    "ほのお": {"ほのお": 0.5, "みず": 0.5, "くさ": 2, "こおり": 2, "むし": 2, "いわ": 0.5, "ドラゴン": 0.5, "はがね": 2},
    "みず": {"ほのお": 2, "みず": 0.5, "くさ": 0.5, "じめん": 2, "いわ": 2, "ドラゴン": 0.5},
    "でんき": {"みず": 2, "でんき": 0.5, "くさ": 0.5, "じめん": 0, "ひこう": 2, "ドラゴン": 0.5},
    "くさ": {"ほのお": 0.5, "みず": 2, "くさ": 0.5, "どく": 0.5, "じめん": 2, "ひこう": 0.5, "むし": 0.5, "いわ": 2, "ドラゴン": 0.5, "はがね": 0.5},
    "こおり": {"ほのお": 0.5, "みず": 0.5, "くさ": 2, "こおり": 0.5, "じめん": 2, "ひこう": 2, "ドラゴン": 2, "はがね": 0.5},
    "かくとう": {"ノーマル": 2, "こおり": 2, "どく": 0.5, "ひこう": 0.5, "エスパー": 0.5, "むし": 0.5, "いわ": 2, "ゴースト": 0, "あく": 2, "はがね": 2, "フェアリー": 0.5},
    "どく": {"くさ": 2, "どく": 0.5, "じめん": 0.5, "いわ": 0.5, "ゴースト": 0.5, "はがね": 0, "フェアリー": 2},
    "じめん": {"ほのお": 2, "でんき": 2, "くさ": 0.5, "どく": 2, "ひこう": 0, "むし": 0.5, "いわ": 2, "はがね": 2},
    "ひこう": {"でんき": 0.5, "くさ": 2, "かくとう": 2, "むし": 2, "いわ": 0.5, "はがね": 0.5},
    "エスパー": {"かくとう": 2, "どく": 2, "エスパー": 0.5, "あく": 0, "はがね": 0.5},
    "むし": {"ほのお": 0.5, "くさ": 2, "かくとう": 0.5, "どく": 0.5, "ひこう": 0.5, "エスパー": 2, "ゴースト": 0.5, "あく": 2, "はがね": 0.5, "フェアリー": 0.5},
    "いわ": {"ほのお": 2, "こおり": 2, "かくとう": 0.5, "じめん": 0.5, "ひこう": 2, "むし": 2, "はがね": 0.5},
    "ゴースト": {"ノーマル": 0, "エスパー": 2, "ゴースト": 2, "あく": 0.5},
    "ドラゴン": {"ドラゴン": 2, "はがね": 0.5, "フェアリー": 0},
    "あく": {"かくとう": 0.5, "エスパー": 2, "ゴースト": 2, "あく": 0.5, "フェアリー": 0.5},
    "はがね": {"ほのお": 0.5, "みず": 0.5, "でんき": 0.5, "こおり": 2, "いわ": 2, "はがね": 0.5, "フェアリー": 2},
    "フェアリー": {"ほのお": 0.5, "かくとう": 2, "どく": 0.5, "ドラゴン": 2, "あく": 2, "はがね": 0.5},
}
EN_TYPE_TO_JP = {en: jp for en, jp in TYPE_JP_MAP.items()}


def coerce_number(value, default=0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def coerce_int(value, default=0) -> int:
    return int(coerce_number(value, default))


def coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "y"}
    return False


def public_access_enabled() -> bool:
    return coerce_bool(os.environ.get("POKEMONWEB_PUBLIC", "0"))


def normalize_type_name(type_name: str) -> str:
    value = str(type_name or "").strip()
    return EN_TYPE_TO_JP.get(value, value)


def calculate_type_effectiveness(move_type: str, defender_types: list[str]) -> float:
    attack_type = normalize_type_name(move_type)
    chart = TYPE_EFFECTIVENESS.get(attack_type, {})
    effectiveness = 1.0
    for defender_type in defender_types or []:
        effectiveness *= float(chart.get(normalize_type_name(defender_type), 1.0))
    return effectiveness


def rank_multiplier(rank: int) -> float:
    rank = max(-6, min(6, int(rank or 0)))
    if rank >= 0:
        return (2 + rank) / 2
    return 2 / (2 - rank)


def find_move_in_detail(detail: dict, move_name: str) -> dict:
    move_key = normalize_text(move_name)
    for move in detail.get("moves") or []:
        if normalize_text(str((move or {}).get("name") or "")) == move_key:
            return dict(move)
    return {"name": move_name}


def resolve_calculate_pokemon(payload: dict, side: str) -> dict:
    direct = payload.get(side)
    if isinstance(direct, dict):
        return dict(direct)

    name = str(payload.get(f"{side}_name") or direct or "").strip()
    if not name:
        return {}

    api_name = resolve_api_name_from_query(name)
    if not api_name:
        return {"jp_name": name}
    return dict(build_pokemon_detail(api_name, name))


def resolve_calculate_move(payload: dict, attacker: dict) -> dict:
    direct = payload.get("move")
    if isinstance(direct, dict):
        return dict(direct)

    move_name = str(payload.get("move_name") or direct or "").strip()
    if not move_name:
        return {}
    if attacker:
        return find_move_in_detail(attacker, move_name)
    return {"name": move_name}


def calculate_ko_text(min_damage: int, max_damage: int, hp: int) -> str:
    if hp <= 0:
        return "HP不明"
    if min_damage >= hp:
        return "確定1発"
    if max_damage >= hp:
        return "乱数1発"
    if min_damage * 2 >= hp:
        return "確定2発"
    if max_damage * 2 >= hp:
        return "乱数2発"
    if min_damage * 3 >= hp:
        return "確定3発"
    if max_damage * 3 >= hp:
        return "乱数3発"
    return "4発以上"


def calculate_ko_chance(rolls: list[int], hp: int, turns: int) -> float:
    if hp <= 0 or turns <= 0 or not rolls:
        return 0.0

    totals = {0: 1}
    for _ in range(turns):
        next_totals: dict[int, int] = {}
        for current_damage, count in totals.items():
            for roll in rolls:
                total_damage = current_damage + roll
                next_totals[total_damage] = next_totals.get(total_damage, 0) + count
        totals = next_totals

    total_cases = len(rolls) ** turns
    ko_cases = sum(count for damage, count in totals.items() if damage >= hp)
    return round((ko_cases / total_cases) * 100, 2)


def calculate_weather_modifier(weather: str, move_type: str) -> float:
    weather = str(weather or "").strip()
    move_type = normalize_type_name(move_type)
    if weather == "sunny":
        if move_type == "ほのお":
            return 1.5
        if move_type == "みず":
            return 0.5
    if weather == "rain":
        if move_type == "みず":
            return 1.5
        if move_type == "ほのお":
            return 0.5
    return 1.0


def calculate_field_modifier(field: str, move_type: str, grounded: bool) -> float:
    if not grounded:
        return 1.0
    field = str(field or "").strip()
    move_type = normalize_type_name(move_type)
    if field == "electric" and move_type == "でんき":
        return 1.3
    if field == "grassy" and move_type == "くさ":
        return 1.3
    if field == "psychic" and move_type == "エスパー":
        return 1.3
    if field == "misty" and move_type == "ドラゴン":
        return 0.5
    return 1.0


def calculate_wall_modifier(wall: str, category: str, critical: bool) -> float:
    if critical:
        return 1.0
    wall = str(wall or "").strip()
    if wall == "aurora_veil":
        return 0.5
    if wall == "reflect" and category == "physical":
        return 0.5
    if wall == "light_screen" and category == "special":
        return 0.5
    return 1.0


def canonical_item_key(value: str) -> str:
    key = normalize_text(value)
    aliases = {
        "こだわりハチマキ": "choice_band",
        "こだわりメガネ": "choice_specs",
        "いのちのたま": "life_orb",
        "たつじんのおび": "expert_belt",
        "ちからのハチマキ": "muscle_band",
        "ものしりメガネ": "wise_glasses",
        "しんかのきせき": "eviolite",
        "とつげきチョッキ": "assault_vest",
        "メタルパウダー": "metal_powder",
        "半減実": "resist_berry",
    }
    for alias, canonical in aliases.items():
        if key == normalize_text(alias):
            return canonical
    return str(value or "").strip()


def get_payload_choice(payload: dict, *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def canonical_ability_key(value: str) -> str:
    raw = str(value or "").strip()
    normalized = normalize_text(raw)
    aliases = {
        "huge_power": ["huge_power", "huge-power", "ちからもち"],
        "pure_power": ["pure_power", "pure-power", "ヨガパワー"],
        "gorilla_tactics": ["gorilla_tactics", "gorilla-tactics", "ごりむちゅう"],
        "guts": ["guts", "こんじょう"],
        "hustle": ["hustle", "はりきり"],
        "solar_power": ["solar_power", "solar-power", "サンパワー"],
        "hadron_engine": ["hadron_engine", "hadron-engine", "ハドロンエンジン"],
        "fur_coat": ["fur_coat", "fur-coat", "ファーコート"],
        "ice_scales": ["ice_scales", "ice-scales", "こおりのりんぷん"],
        "adaptability": ["adaptability", "てきおうりょく"],
        "protean": ["protean", "へんげんじざい", "変幻自在"],
        "libero": ["libero", "リベロ"],
        "tinted_lens": ["tinted_lens", "tinted-lens", "いろめがね"],
        "sniper": ["sniper", "スナイパー"],
        "multiscale": ["multiscale", "マルチスケイル"],
        "shadow_shield": ["shadow_shield", "shadow-shield", "ファントムガード"],
        "wonder_guard": ["wonder_guard", "wonder-guard", "ふしぎなまもり"],
        "levitate": ["levitate", "ふゆう"],
        "flash_fire": ["flash_fire", "flash-fire", "もらいび"],
        "volt_absorb": ["volt_absorb", "volt-absorb", "ちくでん"],
        "lightning_rod": ["lightning_rod", "lightning-rod", "ひらいしん"],
        "motor_drive": ["motor_drive", "motor-drive", "でんきエンジン"],
        "water_absorb": ["water_absorb", "water-absorb", "ちょすい"],
        "storm_drain": ["storm_drain", "storm-drain", "よびみず"],
        "sap_sipper": ["sap_sipper", "sap-sipper", "そうしょく"],
        "mold_breaker": ["mold_breaker", "mold-breaker", "かたやぶり"],
        "teravolt": ["teravolt", "テラボルテージ"],
        "turboblaze": ["turboblaze", "ターボブレイズ"],
    }
    for canonical, names in aliases.items():
        if normalized in {normalize_text(name) for name in names}:
            return canonical
    return normalized


def calculate_item_modifiers(payload: dict, category: str, effectiveness: float) -> dict[str, float]:
    attacker_item = canonical_item_key(get_payload_choice(payload, "attacker_item", "atk_item", "item"))
    defender_item = canonical_item_key(get_payload_choice(payload, "defender_item", "def_item", "def_item_d"))

    attack = 1.0
    defense = 1.0
    power = 1.0
    final = 1.0

    if category == "physical":
        if attacker_item == "choice_band":
            attack *= 1.5
        if attacker_item == "muscle_band":
            power *= 4505 / 4096
        if defender_item == "eviolite":
            defense *= 1.5
        if defender_item == "metal_powder":
            defense *= 2.0
    elif category == "special":
        if attacker_item == "choice_specs":
            attack *= 1.5
        if attacker_item == "wise_glasses":
            power *= 4505 / 4096
        if defender_item == "assault_vest":
            defense *= 1.5
        if defender_item == "eviolite":
            defense *= 1.5

    if attacker_item == "type_power_boost":
        power *= 4915 / 4096
    if attacker_item == "life_orb":
        final *= 5324 / 4096
    if attacker_item == "expert_belt" and effectiveness > 1:
        final *= 4915 / 4096
    if defender_item == "resist_berry" and effectiveness > 1:
        final *= 0.5

    return {
        "attack": attack,
        "defense": defense,
        "power": power,
        "final": final,
        "attacker_item": attacker_item,
        "defender_item": defender_item,
    }


def calculate_ability_modifiers(
    attacker_ability: str,
    defender_ability: str,
    move_type: str,
    category: str,
    effectiveness: float,
    critical: bool,
    defender_hp_percent: float = 100.0,
) -> dict[str, float]:
    attacker_key = canonical_ability_key(attacker_ability)
    defender_key = canonical_ability_key(defender_ability)
    move_type = normalize_type_name(move_type)
    ignores_defender_ability = attacker_key in {"mold_breaker", "teravolt", "turboblaze"}
    attack = 1.0
    defense = 1.0
    final = 1.0
    stab = 1.0

    if category == "physical":
        if attacker_key in {"huge_power", "pure_power"}:
            attack *= 2.0
        if attacker_key in {"gorilla_tactics", "guts", "hustle"}:
            attack *= 1.5
        if not ignores_defender_ability and defender_key == "fur_coat":
            defense *= 2.0
    elif category == "special":
        if attacker_key == "solar_power":
            attack *= 1.5
        if attacker_key == "hadron_engine":
            attack *= 1.3333
        if not ignores_defender_ability and defender_key == "ice_scales":
            final *= 0.5

    if attacker_key == "adaptability":
        stab = 2.0
    if attacker_key in {"protean", "libero"}:
        stab = max(stab, 1.5)
    if attacker_key == "tinted_lens" and 0 < effectiveness < 1:
        final *= 2.0
    if attacker_key == "sniper" and critical:
        final *= 1.5

    if not ignores_defender_ability:
        if defender_hp_percent >= 100 and defender_key in {"multiscale", "shadow_shield"}:
            final *= 0.5
        if defender_key == "wonder_guard" and effectiveness <= 1:
            final = 0.0
        if defender_key == "levitate" and move_type == "\u3058\u3081\u3093":
            final = 0.0
        if defender_key == "flash_fire" and move_type == "\u307b\u306e\u304a":
            final = 0.0
        if defender_key in {"volt_absorb", "lightning_rod", "motor_drive"} and move_type == "\u3067\u3093\u304d":
            final = 0.0
        if defender_key in {"water_absorb", "storm_drain"} and move_type == "\u307f\u305a":
            final = 0.0
        if defender_key == "sap_sipper" and move_type == "\u304f\u3055":
            final = 0.0

    return {
        "attack": attack,
        "defense": defense,
        "final": final,
        "stab": stab,
        "ignores_defender_ability": 1.0 if ignores_defender_ability else 0.0,
    }


@app.post("/calculate")
def calculate():
    payload = request.get_json(force=True, silent=True) or {}

    try:
        attacker = resolve_calculate_pokemon(payload, "attacker")
        defender = resolve_calculate_pokemon(payload, "defender")
        move = resolve_calculate_move(payload, attacker)

        move_name = str(move.get("name") or payload.get("move_name") or "").strip()
        move_type = normalize_type_name(str(move.get("type") or payload.get("move_type") or ""))
        category = str(move.get("damage_class") or payload.get("category") or payload.get("damage_class") or "").strip()
        if not category:
            class_label = str(move.get("class") or move.get("class_jp") or "").strip()
            category = "special" if class_label == "特殊" else "physical" if class_label == "物理" else "status"

        power = coerce_int(move.get("power", payload.get("power")), 0)
        if not move_name:
            return jsonify({"error": "move_name is required"}), 400
        if category == "status" or power <= 0:
            return jsonify({
                "min_damage": 0,
                "max_damage": 0,
                "min_percent": 0,
                "max_percent": 0,
                "ko_text": "変化技または威力なし",
                "effectiveness": 1.0,
                "move": {"name": move_name, "type": move_type, "power": power, "damage_class": category},
                "rolls": [],
            })

        attacker_stats = dict(attacker.get("stats") or payload.get("attacker_stats") or {})
        defender_stats = dict(defender.get("stats") or payload.get("defender_stats") or {})
        attacker_types = list(attacker.get("types") or payload.get("attacker_types") or [])
        defender_types = list(defender.get("types") or payload.get("defender_types") or [])

        attack_key = "special_attack" if category == "special" else "attack"
        defense_key = "special_defense" if category == "special" else "defense"
        attack = coerce_int(payload.get("attack", attacker_stats.get(attack_key)), 0)
        defense = coerce_int(payload.get("defense", defender_stats.get(defense_key)), 0)
        defender_hp = coerce_int(payload.get("defender_hp", defender_stats.get("hp")), 0)
        if attack <= 0 or defense <= 0 or defender_hp <= 0:
            return jsonify({"error": "attacker/defender stats are required"}), 400

        level = coerce_int(payload.get("level"), 50)
        atk_rank = coerce_int(payload.get("atk_rank", payload.get("attack_rank")), 0)
        def_rank = coerce_int(payload.get("def_rank", payload.get("defense_rank")), 0)
        critical = coerce_bool(payload.get("critical", False))
        if critical:
            atk_rank = max(0, atk_rank)
            def_rank = min(0, def_rank)

        weather = str(payload.get("weather") or payload.get("battle_weather") or "").strip()
        field = str(payload.get("field") or payload.get("battle_field") or "").strip()
        wall = str(payload.get("wall") or payload.get("def_wall") or "").strip()
        grounded = not coerce_bool(payload.get("not_grounded", False))
        hits = max(1, min(10, coerce_int(payload.get("hits", payload.get("move_hits")), 1)))
        attacker_ability = get_payload_choice(payload, "attacker_ability", "atk_ability")
        defender_ability = get_payload_choice(payload, "defender_ability", "def_ability")
        defender_current_hp = coerce_number(payload.get("defender_current_hp", payload.get("def_current_hp")), 0)
        if defender_current_hp > 0:
            defender_hp_percent = max(0.0, min(100.0, defender_current_hp / defender_hp * 100))
        else:
            defender_hp_percent = max(
                0.0,
                min(100.0, coerce_number(payload.get("defender_current_hp_percent", payload.get("def_cur_hp_pct")), 100)),
            )

        effectiveness = calculate_type_effectiveness(move_type, defender_types)
        item_modifiers = calculate_item_modifiers(payload, category, effectiveness)
        ability_modifiers = calculate_ability_modifiers(
            attacker_ability,
            defender_ability,
            move_type,
            category,
            effectiveness,
            critical,
            defender_hp_percent,
        )

        attack = max(1, int(
            attack
            * rank_multiplier(atk_rank)
            * item_modifiers["attack"]
            * ability_modifiers["attack"]
            * coerce_number(payload.get("attack_modifier"), 1)
        ))
        defense = max(1, int(
            defense
            * rank_multiplier(def_rank)
            * item_modifiers["defense"]
            * ability_modifiers["defense"]
            * coerce_number(payload.get("defense_modifier"), 1)
        ))
        power = max(1, int(
            power
            * item_modifiers["power"]
            * coerce_number(payload.get("power_modifier"), 1)
        ))

        if weather == "sand" and category == "special" and "いわ" in [normalize_type_name(t) for t in defender_types]:
            defense = max(1, int(defense * 1.5))

        normalized_attacker_types = [normalize_type_name(t) for t in attacker_types]
        has_stab = normalize_type_name(move_type) in normalized_attacker_types
        protean_like = canonical_ability_key(attacker_ability) in {"protean", "libero"}
        stab = ability_modifiers["stab"] if ability_modifiers["stab"] > 1 else 1.5 if (has_stab or protean_like) else 1.0
        burn = coerce_bool(payload.get("burn", payload.get("atk_burn", False))) and category == "physical"
        burn_modifier = 0.5 if burn and not critical else 1.0
        critical_modifier = 1.5 if critical else 1.0
        wall_modifier = calculate_wall_modifier(wall, category, critical)
        weather_modifier = calculate_weather_modifier(weather, move_type)
        field_modifier = calculate_field_modifier(field, move_type, grounded)
        final_modifier = (
            item_modifiers["final"]
            * ability_modifiers["final"]
            * coerce_number(payload.get("final_modifier"), 1)
        )

        base_damage = (((2 * level // 5 + 2) * power * attack // defense) // 50) + 2
        rolls = []
        for random_percent in range(85, 101):
            damage = int(base_damage * random_percent / 100)
            damage = int(
                damage
                * stab
                * effectiveness
                * burn_modifier
                * critical_modifier
                * wall_modifier
                * weather_modifier
                * field_modifier
                * final_modifier
            )
            rolls.append(max(0, damage) * hits)

        min_damage = min(rolls)
        max_damage = max(rolls)
        ko_chances = {
            "one_hit": calculate_ko_chance(rolls, defender_hp, 1),
            "two_hit": calculate_ko_chance(rolls, defender_hp, 2),
            "three_hit": calculate_ko_chance(rolls, defender_hp, 3),
            "four_hit": calculate_ko_chance(rolls, defender_hp, 4),
        }
        return jsonify({
            "min_damage": min_damage,
            "max_damage": max_damage,
            "min_percent": round(min_damage / defender_hp * 100, 1),
            "max_percent": round(max_damage / defender_hp * 100, 1),
            "ko_text": calculate_ko_text(min_damage, max_damage, defender_hp),
            "ko_chances": ko_chances,
            "one_hit_chance": ko_chances["one_hit"],
            "two_hit_chance": ko_chances["two_hit"],
            "three_hit_chance": ko_chances["three_hit"],
            "four_hit_chance": ko_chances["four_hit"],
            "effectiveness": effectiveness,
            "stab": stab,
            "modifiers": {
                "burn": burn_modifier,
                "critical": critical_modifier,
                "wall": wall_modifier,
                "weather": weather_modifier,
                "field": field_modifier,
                "final": final_modifier,
                "hits": hits,
                "item_attack": item_modifiers["attack"],
                "item_defense": item_modifiers["defense"],
                "item_power": item_modifiers["power"],
                "item_final": item_modifiers["final"],
                "ability_attack": ability_modifiers["attack"],
                "ability_defense": ability_modifiers["defense"],
                "ability_final": ability_modifiers["final"],
                "ignores_defender_ability": ability_modifiers["ignores_defender_ability"],
            },
            "items": {"attacker": item_modifiers["attacker_item"], "defender": item_modifiers["defender_item"]},
            "abilities": {"attacker": attacker_ability, "defender": defender_ability},
            "hp": {"defender_current_percent": round(defender_hp_percent, 1)},
            "move": {"name": move_name, "type": move_type, "power": power, "damage_class": category},
            "attacker": {"name": attacker.get("jp_name") or attacker.get("api_name") or payload.get("attacker_name", "")},
            "defender": {"name": defender.get("jp_name") or defender.get("api_name") or payload.get("defender_name", ""), "hp": defender_hp},
            "rolls": rolls,
        })
    except Exception as e:
        return jsonify({"error": f"damage calculation failed: {e}"}), 500


load_caches()
ensure_ready_async()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
