import os
import math
import json
import requests
import functions_framework
from flask import jsonify, request
from google.cloud import firestore
from urllib.parse import quote
import re

CAMPINAS_CENTER = (-22.90556, -47.06083)
RMC_CITIES = {
    "campinas", "valinhos", "vinhedo", "hortolândia", "hortolandia",
    "sumaré", "sumare", "paulínia", "paulinia", "indaiatuba",
    "americana", "jaguariúna", "jaguariuna", "cosmópolis", "cosmopolis",
    "monte mor", "louveira", "nova odessa", "santa bárbara d'oeste", "santa barbara d'oeste"
}
UF_SIGLAS = {"sp", "são paulo", "sao paulo"}

CEP_RE = re.compile(r"\b\d{5}-?\d{3}\b")

def _km(a_lat, a_lng, b_lat, b_lng):
    R = 6371.0
    from math import radians, sin, cos, atan2, sqrt
    dlat = radians(b_lat - a_lat)
    dlon = radians(b_lng - a_lng)
    la1, la2 = radians(a_lat), radians(b_lat)
    a = sin(dlat/2)**2 + cos(la1)*cos(la2)*sin(dlon/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1-a))

def _query_is_ambiguous(q: str) -> bool:
    """Sem cidade/UF → considerado ambíguo."""
    if not q: return True
    s = q.lower()
    if CEP_RE.search(s):                      # CEP não é ambíguo
        return False
    # contém alguma cidade da RMC?
    if any(name in s for name in RMC_CITIES):
        return False
    # contém UF ou 'SP'?
    if any(tok in s for tok in UF_SIGLAS):
        return False
    return True

# =========================
# Config & Bounds (Campinas)
# =========================

def _load_bounds():
    """
    Lê a caixa da região:
    - GEOCODE_BOUNDS="west,south,east,north" (recomendado)
    - ou BBOX_SW="lat_sul,lon_oeste" e BBOX_NE="lat_norte,lon_leste"
    - fallback: box ampla da RMC que você passou
    """
    gb = os.getenv("GEOCODE_BOUNDS", "").strip()
    if gb:
        try:
            w, s, e, n = [float(x) for x in gb.split(",")]
            return w, s, e, n
        except Exception:
            pass

    sw = os.getenv("BBOX_SW", "").strip()
    ne = os.getenv("BBOX_NE", "").strip()
    if sw and ne:
        try:
            s_lat, w_lon = [float(x) for x in sw.split(",")]
            n_lat, e_lon = [float(x) for x in ne.split(",")]
            return w_lon, s_lat, e_lon, n_lat
        except Exception:
            pass

    # Default (RM de Campinas)
    return (-47.4485604153, -23.3051443266, -46.546640812, -22.5353721487)

BBOX_W, BBOX_S, BBOX_E, BBOX_N = _load_bounds()
BBOX_SW = (BBOX_S, BBOX_W)  # (lat, lon)
BBOX_NE = (BBOX_N, BBOX_E)  # (lat, lon)

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
if not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("Defina GOOGLE_MAPS_API_KEY nas variáveis de ambiente.")

FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "churches")
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE")  # None => default
db = firestore.Client(database=FIRESTORE_DATABASE) if FIRESTORE_DATABASE else firestore.Client()

# =========================
# Geocoding (Google) enviesado p/ Campinas
# =========================

_GEOCODE_TYPE_PRIORITY = {
    "street_address": 0,
    "premise": 1,
    "subpremise": 2,
    "route": 3,
    "neighborhood": 4,
    "sublocality": 5,
    "locality": 6,
    "political": 9,
}

def _score_geocode_result(res):
    """
    Score menor = melhor.
    - Prioriza tipo (street_address < route < …)
    - Bônus se estiver dentro do BBox
    - Penaliza distância ao centro de Campinas (até +2 pts)
    """
    types = res.get("types", [])
    base = min((_GEOCODE_TYPE_PRIORITY.get(t, 8) for t in types), default=8)
    try:
        loc = res["geometry"]["location"]
        lat, lng = float(loc["lat"]), float(loc["lng"])
        # bônus por cair dentro do retângulo
        in_bbox = (BBOX_S <= lat <= BBOX_N) and (BBOX_W <= lng <= BBOX_E)
        if in_bbox:
            base -= 0.5
        # penalidade gradual por distância ao centro
        d_km = _km(CAMPINAS_CENTER[0], CAMPINAS_CENTER[1], lat, lng)
        base += min(d_km / 50.0, 2.0)  # até +2
    except Exception:
        pass
    return base


def geocode_google_biased(q: str):
    """
    Ordem de tentativas:
      A) (se ambígua) address = "<q>, Campinas - SP", components=locality:Campinas|administrative_area:SP|country:BR
      B) address = q, components=country:BR|administrative_area:SP, bounds=Campinas
      C) address = q, components=country:BR|administrative_area:SP
      D) address = q, components=country:BR
    Retorna (lat, lon, formatted_address, place_id) ou (None, None, None, None)
    """
    if not GOOGLE_MAPS_API_KEY or not q:
        return None, None, None, None

    url = "https://maps.googleapis.com/maps/api/geocode/json"

    def call(params):
        try:
            r = requests.get(url, params=params, timeout=12)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            return {"status":"REQUEST_FAILED","results":[]}

    def pick_best(data):
        if data.get("status") == "OK" and data.get("results"):
            best = sorted(data["results"], key=_score_geocode_result)[0]
            loc = best["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"]), best.get("formatted_address"), best.get("place_id")
        return None

    # CEP → deixe o Google trabalhar sem “colar Campinas”
    if CEP_RE.search(q):
        base = {"address": q, "key": GOOGLE_MAPS_API_KEY, "region": "br", "components": "country:BR"}
        got = pick_best(call(base))
        if got: return got

    # A) se ambígua, força Campinas na address + components
    if _query_is_ambiguous(q):
        a = {
            "address": f"{q}, Campinas - SP",
            "key": GOOGLE_MAPS_API_KEY,
            "region": "br",
            "components": "locality:Campinas|administrative_area:SP|country:BR",
        }
        got = pick_best(call(a))
        if got: return got

    # B) SP + bounds (Campinas)
    b = {
        "address": q,
        "key": GOOGLE_MAPS_API_KEY,
        "region": "br",
        "components": "country:BR|administrative_area:SP",
        "bounds": f"{BBOX_SW[0]},{BBOX_SW[1]}|{BBOX_NE[0]},{BBOX_NE[1]}",
    }
    got = pick_best(call(b))
    if got: return got

    # C) SP
    c = {"address": q, "key": GOOGLE_MAPS_API_KEY, "region": "br", "components": "country:BR|administrative_area:SP"}
    got = pick_best(call(c))
    if got: return got

    # D) BR
    d = {"address": q, "key": GOOGLE_MAPS_API_KEY, "region": "br", "components": "country:BR"}
    got = pick_best(call(d))
    if got: return got

    return None, None, None, None


def gmaps_reverse_geocode(lat: float, lon: float):
    """Reverse geocoding simples para exibir endereço interpretado."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "latlng": f"{lat},{lon}",
        "key": GOOGLE_MAPS_API_KEY,
        "result_type": "street_address|premise|route|sublocality|locality",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        data = r.json()
        if data.get("status") == "OK" and data.get("results"):
            res = data["results"][0]
            return res.get("formatted_address"), res.get("place_id")
    except requests.RequestException:
        pass
    return None, None

# =========================
# Utils
# =========================

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = math.sin(dlat/2)**2 + math.cos(math.radians(float(lat1))) * \
        math.cos(math.radians(float(lat2))) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def google_maps_search_url(q: str):
    return f"https://www.google.com/maps/search/?api=1&query={quote(str(q))}"

def normalize_whatsapp(raw: str) -> str:
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10 or len(digits) == 11:
        return f"55{digits}"
    if digits.startswith("55"):
        return digits
    if len(digits) > 11:
        return f"55{digits[-11:]}"
    return digits

def load_churches():
    churches = []
    for doc in db.collection(FIRESTORE_COLLECTION).where("active", "==", True).stream():
        data = doc.to_dict() or {}
        lat = data.get("lat")
        lon = data.get("lon")
        if lat is None or lon is None:
            continue
        item = {
            "id": doc.id,
            "name": data.get("name", ""),
            "address": data.get("address", ""),
            "formatted_address": data.get("formatted_address", ""),
            "cep": data.get("cep", ""),
            "day": data.get("day", ""),
            "time": data.get("time", ""),
            "contact": data.get("contact", ""),
            "lat": float(lat),
            "lon": float(lon),
            "active": bool(data.get("active", True)),
        }
        # Maps: usa coordenadas (mais preciso)
        item["maps_url"] = f"https://www.google.com/maps/search/?api=1&query={item['lat']},{item['lon']}"
        churches.append(item)
    return churches

def _ok(obj, status=200):
    return jsonify(obj), status, {"Access-Control-Allow-Origin": "*"}

def _err(msg, status=400):
    return jsonify({"error": msg}), status, {"Access-Control-Allow-Origin": "*"}

# =========================
# HTTP Handler (Cloud Run)
# =========================

@functions_framework.http
def geocode_and_find_nearest_2(request):
    # CORS preflight
    if request.method == "OPTIONS":
        headers = {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Max-Age": "3600",
        }
        return ("", 204, headers)

    req = request.get_json(silent=True) or {}

    # filtros
    limit = int(req.get("limit") or 3)
    limit = max(1, min(limit, 20))
    max_distance_km = req.get("max_distance_km")
    try:
        max_distance_km = float(max_distance_km) if max_distance_km is not None else None
    except Exception:
        max_distance_km = None

    # entrada do usuário
    lat_in = req.get("lat")
    lon_in = req.get("lon")
    address = (req.get("address") or "").strip()
    cep = (req.get("cep") or "").strip()

    # 1) origem do usuário
    user_lat = user_lon = None
    formatted = None
    place_id = None

    if isinstance(lat_in, (int, float)) and isinstance(lon_in, (int, float)):
        user_lat, user_lon = float(lat_in), float(lon_in)
        formatted, place_id = gmaps_reverse_geocode(user_lat, user_lon)
        if not formatted:
            formatted = "Localização do dispositivo"
    else:
        if not address and not cep:
            return _err("Forneça 'address'/'cep' ou 'lat' e 'lon'.", 400)
        query = address or cep
        user_lat, user_lon, formatted, place_id = geocode_google_biased(query)
        if user_lat is None or user_lon is None:
            return _err("Endereço não encontrado. Tente incluir número/bairro/CEP.", 404)

    # 2) igrejas
    churches = load_churches()

    # 3) distâncias + raio
    scored = []
    for ch in churches:
        d = haversine_km(user_lat, user_lon, ch["lat"], ch["lon"])
        if (max_distance_km is not None) and (d > max_distance_km):
            continue
        scored.append((d, ch))

    scored.sort(key=lambda x: x[0])
    top = scored[:limit]

    # 4) resposta
    nearest = []
    for dist_km, ch in top:
        nearest.append({
            "id": ch["id"],
            "name": ch["name"],
            "address": ch["formatted_address"] or ch["address"],
            "cep": ch["cep"],
            "day": ch["day"],
            "time": ch["time"],
            "contact": ch["contact"],
            "lat": ch["lat"],
            "lon": ch["lon"],
            "maps_url": ch["maps_url"],
            "distance_km": round(dist_km, 2),
            "distance": round(dist_km, 2),  # compat
        })

    resp = {
        "query": {
            "input_address": formatted or (address or cep or f"{user_lat},{user_lon}"),
            "lat": user_lat,
            "lon": user_lon,
            "place_id": place_id,
            "maps_url": f"https://www.google.com/maps/search/?api=1&query={user_lat},{user_lon}",
            "provider": "googlemaps",
        },
        "nearest_churches": nearest,
    }
    return _ok(resp, 200)
