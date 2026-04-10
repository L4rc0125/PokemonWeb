const POKEAPI_BASE = "https://pokeapi.co/api/v2";
const SPECIES_LIST_URL = `${POKEAPI_BASE}/pokemon-species?limit=2000`;
const TYPE_ASSET_BASE = "../static/types";

const TYPE_JP_MAP = {
  normal: "ノーマル", fire: "ほのお", water: "みず", electric: "でんき",
  grass: "くさ", ice: "こおり", fighting: "かくとう", poison: "どく",
  ground: "じめん", flying: "ひこう", psychic: "エスパー", bug: "むし",
  rock: "いわ", ghost: "ゴースト", dragon: "ドラゴン", dark: "あく",
  steel: "はがね", fairy: "フェアリー",
};

const MOVE_CLASS_JP_MAP = {
  physical: "物理",
  special: "特殊",
  status: "変化",
};

const TYPE_CHART = {
  ノーマル:{かくとう:2,ゴースト:0},
  ほのお:{みず:2,じめん:2,いわ:2,くさ:0.5,こおり:0.5,むし:0.5,はがね:0.5,フェアリー:0.5},
  みず:{でんき:2,くさ:2,ほのお:0.5,みず:0.5,こおり:0.5,はがね:0.5},
  でんき:{じめん:2,でんき:0.5,ひこう:0.5,はがね:0.5},
  くさ:{ほのお:2,こおり:2,どく:2,ひこう:2,むし:2,みず:0.5,でんき:0.5,くさ:0.5,じめん:0.5},
  こおり:{ほのお:2,かくとう:2,いわ:2,はがね:2,こおり:0.5},
  かくとう:{ひこう:2,エスパー:2,フェアリー:2,むし:0.5,いわ:0.5,あく:0.5},
  どく:{じめん:2,エスパー:2,くさ:0.5,かくとう:0.5,どく:0.5,むし:0.5,フェアリー:0.5},
  じめん:{みず:2,くさ:2,こおり:2,どく:0.5,いわ:0.5},
  ひこう:{でんき:2,こおり:2,いわ:2,くさ:0.5,かくとう:0.5,むし:0.5,じめん:0},
  エスパー:{むし:2,ゴースト:2,あく:2,かくとう:0.5,エスパー:0.5},
  むし:{ほのお:2,ひこう:2,いわ:2,くさ:0.5,かくとう:0.5,じめん:0.5},
  いわ:{みず:2,くさ:2,かくとう:2,じめん:2,はがね:2,ノーマル:0.5,ほのお:0.5,どく:0.5,ひこう:0.5},
  ゴースト:{ゴースト:2,あく:2,どく:0.5,むし:0.5,ノーマル:0,かくとう:0},
  ドラゴン:{こおり:2,ドラゴン:2,フェアリー:2,ほのお:0.5,みず:0.5,でんき:0.5,くさ:0.5},
  あく:{かくとう:2,むし:2,フェアリー:2,ゴースト:0.5,あく:0.5,エスパー:0},
  はがね:{ほのお:2,かくとう:2,じめん:2,ノーマル:0.5,くさ:0.5,こおり:0.5,ひこう:0.5,エスパー:0.5,むし:0.5,いわ:0.5,ドラゴン:0.5,はがね:0.5,フェアリー:0.5,どく:0},
  フェアリー:{どく:2,はがね:2,かくとう:0.5,むし:0.5,あく:0.5,ドラゴン:0},
};

const cache = {
  species: null,
  detail: new Map(),
  resourceName: new Map(),
};

function el(id) {
  return document.getElementById(id);
}

function setStatus(text) {
  el("status").textContent = text;
}

function kataToHira(text){
  return String(text || "").replace(/[ァ-ヶ]/g, s =>
    String.fromCharCode(s.charCodeAt(0) - 0x60)
  );
}

function toAscii(text){
  return String(text || "")
    .replace(/[Ａ-Ｚａ-ｚ０-９]/g, s => String.fromCharCode(s.charCodeAt(0) - 0xFEE0))
    .replace(/×/g, "x");
}

function normalizeName(text){
  return kataToHira(toAscii(String(text || "")))
    .toLowerCase()
    .replace(/[\s　._\-・/]/g, "")
    .replace(/[()（）[\]【】]/g, "")
    .replace(/のすがた/g, "")
    .replace(/すがた/g, "")
    .replace(/ひすいちほう/g, "ひすい")
    .replace(/ー/g, "");
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function pickJapaneseName(entries) {
  if (!Array.isArray(entries)) return "";
  for (const lang of ["ja-Hrkt", "ja"]) {
    const found = entries.find(item => item.language && item.language.name === lang && item.name);
    if (found) return String(found.name).trim();
  }
  return "";
}

async function loadSpeciesList() {
  const stored = localStorage.getItem("pokemon_static_species_v1");
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      if (Array.isArray(parsed) && parsed.length > 100) {
        cache.species = parsed;
        return parsed;
      }
    } catch (e) {}
  }

  setStatus("PokeAPIから一覧取得中...");
  const list = await fetchJson(SPECIES_LIST_URL);
  const results = list.results || [];
  const entries = [];
  let done = 0;

  for (const item of results) {
    try {
      const species = await fetchJson(item.url);
      const jpName = pickJapaneseName(species.names);
      const apiName = ((species.varieties || []).find(v => v.is_default)?.pokemon?.name) || species.name;
      if (jpName && apiName) {
        entries.push({
          jp_name: jpName,
          api_name: apiName,
          species_name: species.name,
        });
      }
    } catch (e) {}
    done += 1;
    if (done % 25 === 0) setStatus(`PokeAPIから一覧取得中... ${done}/${results.length}`);
  }

  entries.sort((a, b) => a.jp_name.localeCompare(b.jp_name, "ja"));
  localStorage.setItem("pokemon_static_species_v1", JSON.stringify(entries));
  cache.species = entries;
  return entries;
}

function searchSpecies(query) {
  const q = normalizeName(query);
  const species = cache.species || [];
  if (!q) return species.slice(0, 20);

  const starts = [];
  const contains = [];
  for (const item of species) {
    const aliases = [item.jp_name, item.api_name, item.species_name].filter(Boolean).map(normalizeName);
    if (aliases.some(alias => alias.startsWith(q))) starts.push(item);
    else if (aliases.some(alias => alias.includes(q))) contains.push(item);
  }
  return starts.concat(contains).slice(0, 20);
}

async function localizeResourceName(url) {
  if (!url) return "";
  if (cache.resourceName.has(url)) return cache.resourceName.get(url);
  try {
    const data = await fetchJson(url);
    const name = pickJapaneseName(data.names) || data.name || "";
    cache.resourceName.set(url, name);
    return name;
  } catch (e) {
    return "";
  }
}

function calcActualStat(base, isHp = false) {
  const b = Number(base || 0);
  if (isHp) return Math.floor(((b * 2 + 31) * 50) / 100) + 60;
  return Math.floor(((b * 2 + 31) * 50) / 100) + 5;
}

async function loadPokemonDetail(name) {
  const species = cache.species || [];
  const q = normalizeName(name);
  const entry = species.find(item => [item.jp_name, item.api_name, item.species_name].some(alias => normalizeName(alias) === q))
    || searchSpecies(name)[0];
  if (!entry) throw new Error(`${name} が見つかりません`);

  if (cache.detail.has(entry.api_name)) return cache.detail.get(entry.api_name);

  const pokemon = await fetchJson(`${POKEAPI_BASE}/pokemon/${entry.api_name}`);
  const types = (pokemon.types || [])
    .sort((a, b) => Number(a.slot || 0) - Number(b.slot || 0))
    .map(item => TYPE_JP_MAP[item.type?.name] || item.type?.name || "");

  const abilities = [];
  for (const item of pokemon.abilities || []) {
    const name = await localizeResourceName(item.ability && item.ability.url);
    if (name) abilities.push(name);
  }

  const moves = [];
  for (const item of (pokemon.moves || []).slice(0, 200)) {
    try {
      const move = await fetchJson(item.move.url);
      const damageClass = move.damage_class?.name || "";
      moves.push({
        name: pickJapaneseName(move.names) || move.name,
        type: TYPE_JP_MAP[move.type?.name] || move.type?.name || "",
        power: move.power,
        class: MOVE_CLASS_JP_MAP[damageClass] || "",
      });
    } catch (e) {}
  }
  moves.sort((a, b) => a.name.localeCompare(b.name, "ja"));

  const statMap = {};
  for (const item of pokemon.stats || []) {
    statMap[item.stat.name] = Number(item.base_stat || 0);
  }

  const detail = {
    jp_name: entry.jp_name,
    api_name: entry.api_name,
    sprite: pokemon.sprites?.front_default || pokemon.sprites?.other?.["official-artwork"]?.front_default || "",
    types,
    abilities: [...new Set(abilities)],
    moves,
    stats: {
      hp: calcActualStat(statMap.hp, true),
      attack: calcActualStat(statMap.attack),
      defense: calcActualStat(statMap.defense),
      special_attack: calcActualStat(statMap["special-attack"]),
      special_defense: calcActualStat(statMap["special-defense"]),
      speed: calcActualStat(statMap.speed),
    },
  };
  cache.detail.set(entry.api_name, detail);
  return detail;
}

function typeIconPath(typeName) {
  return `${TYPE_ASSET_BASE}/${encodeURIComponent(typeName)}.png`;
}

function renderTypes(side, types) {
  const wrap = el(`${side}_types`);
  wrap.innerHTML = "";
  for (const type of types || []) {
    const img = document.createElement("img");
    img.className = "type-icon";
    img.alt = type;
    img.src = typeIconPath(type);
    img.onerror = () => {
      img.remove();
      const fallback = document.createElement("span");
      fallback.className = "type-fallback";
      fallback.textContent = type;
      wrap.appendChild(fallback);
    };
    wrap.appendChild(img);
  }
}

function renderStats(side, stats) {
  const wrap = el(`${side}_stats`);
  wrap.innerHTML = "";
  const rows = [
    ["hp", "H"], ["attack", "A"], ["defense", "B"],
    ["special_attack", "C"], ["special_defense", "D"], ["speed", "S"],
  ];
  for (const [key, label] of rows) {
    const chip = document.createElement("span");
    chip.className = "stat-chip";
    chip.textContent = `${label}${Number(stats[key] || 0)}`;
    wrap.appendChild(chip);
  }
}

function calcWeakness(types) {
  const result = {};
  for (const attackType of Object.keys(TYPE_CHART)) {
    let mult = 1;
    for (const defType of types || []) {
      mult *= (TYPE_CHART[defType] || {})[attackType] ?? 1;
    }
    if (mult !== 1) result[attackType] = mult;
  }
  return result;
}

function renderWeakness(side, types) {
  const wrap = el(`${side}_weakness`);
  wrap.innerHTML = "";
  const weak = calcWeakness(types);
  for (const mult of [4, 2, 0.5, 0.25, 0]) {
    const typeNames = Object.entries(weak).filter(([, v]) => v === mult).map(([k]) => k);
    if (!typeNames.length) continue;

    const chip = document.createElement("span");
    chip.className = "weakness-chip";
    chip.textContent = mult === 0 ? "無効:" : `${mult}:`;
    for (const type of typeNames) {
      const img = document.createElement("img");
      img.src = typeIconPath(type);
      img.alt = type;
      chip.appendChild(img);
    }
    wrap.appendChild(chip);
  }
}

function renderAbilities(side, abilities) {
  const wrap = el(`${side}_abilities`);
  wrap.innerHTML = "";
  for (const ability of abilities || []) {
    const chip = document.createElement("span");
    chip.className = "ability-chip";
    chip.textContent = ability;
    wrap.appendChild(chip);
  }
}

function renderMoves(side, moves) {
  const select = el(`${side}_moves`);
  select.innerHTML = "";
  for (const move of moves || []) {
    const opt = document.createElement("option");
    opt.value = move.name;
    opt.textContent = `${move.name} / ${move.type} / ${move.power ?? "-"} / ${move.class}`;
    select.appendChild(opt);
  }
}

async function loadSide(side, name) {
  setStatus(`${name} 読み込み中...`);
  const detail = await loadPokemonDetail(name);
  el(`${side}_search`).value = detail.jp_name;
  el(`${side}_sprite`).src = detail.sprite;
  el(`${side}_sprite`).alt = detail.jp_name;
  renderTypes(side, detail.types);
  renderStats(side, detail.stats);
  renderWeakness(side, detail.types);
  renderAbilities(side, detail.abilities);
  renderMoves(side, detail.moves);
  setStatus(`準備完了: ${detail.jp_name}`);
}

function hideSuggest(side) {
  const box = el(`${side}_suggest`);
  box.style.display = "none";
  box.innerHTML = "";
}

function showSuggest(side, items) {
  const box = el(`${side}_suggest`);
  box.innerHTML = "";
  if (!items.length) {
    hideSuggest(side);
    return;
  }
  for (const item of items) {
    const row = document.createElement("div");
    row.className = "suggest-item";
    row.textContent = item.jp_name;
    row.addEventListener("mousedown", event => {
      event.preventDefault();
      hideSuggest(side);
      loadSide(side, item.jp_name).catch(error => setStatus(error.message));
    });
    box.appendChild(row);
  }
  box.style.display = "block";
}

function bindSearch(side) {
  const input = el(`${side}_search`);
  input.addEventListener("input", () => showSuggest(side, searchSpecies(input.value)));
  input.addEventListener("focus", () => showSuggest(side, searchSpecies(input.value)));
  input.addEventListener("keydown", event => {
    if (event.key === "Enter") {
      event.preventDefault();
      hideSuggest(side);
      loadSide(side, input.value).catch(error => setStatus(error.message));
    }
    if (event.key === "Escape") hideSuggest(side);
  });
  input.addEventListener("blur", () => setTimeout(() => hideSuggest(side), 120));
}

async function init() {
  bindSearch("attacker");
  bindSearch("defender");
  await loadSpeciesList();
  setStatus(`準備完了 (${cache.species.length}件)`);
  await Promise.allSettled([
    loadSide("attacker", "ガブリアス"),
    loadSide("defender", "カイリュー"),
  ]);
}

init().catch(error => setStatus(error.message));
