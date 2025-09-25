import os
import json
import math
import requests
import functions_framework
from flask import jsonify, request
from google.cloud import firestore

# ========= Config =========
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
if not GOOGLE_MAPS_API_KEY:
    raise RuntimeError("Defina GOOGLE_MAPS_API_KEY nas variáveis de ambiente.")

FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "churches")
FIRESTORE_DATABASE = os.getenv("FIRESTORE_DATABASE")  # None => (default)

# Firestore client
db = firestore.Client(database=FIRESTORE_DATABASE) if FIRESTORE_DATABASE else firestore.Client()

# ========= Utils =========
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = math.sin(dlat/2)**2 + math.cos(math.radians(float(lat1))) * \
        math.cos(math.radians(float(lat2))) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c

def gmaps_geocode(address_or_cep: str):
    """
    Usa Google Geocoding API com bias para BR.
    Retorna (lat, lon, formatted_address, place_id) ou (None, None, None, None).
    """
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": f"{address_or_cep}, Brasil",
        "key": GOOGLE_MAPS_API_KEY,
        "components": "country:BR",
        "region": "br",
    }
    try:
        r = requests.get(url, params=params, timeout=12)
        data = r.json()
        status = data.get("status")
        if status == "OK":
            res = data["results"][0]
            loc = res["geometry"]["location"]
            return float(loc["lat"]), float(loc["lng"]), res.get("formatted_address"), res.get("place_id")
        # Se falhar, tente sem o “, Brasil” (casos de CEP já completo)
        if status in ("ZERO_RESULTS", "INVALID_REQUEST"):
            params["address"] = address_or_cep
            r2 = requests.get(url, params=params, timeout=12)
            data2 = r2.json()
            if data2.get("status") == "OK":
                res = data2["results"][0]
                loc = res["geometry"]["location"]
                return float(loc["lat"]), float(loc["lng"]), res.get("formatted_address"), res.get("place_id")
    except requests.RequestException:
        pass
    return None, None, None, None

def google_maps_search_url(q: str):
    from urllib.parse import quote
    return f"https://www.google.com/maps/search/?api=1&query={quote(q)}"

def normalize_whatsapp(raw: str) -> str:
    """Deixa só dígitos e retorna com DDI BR (55) se faltar. Útil se quiser expor no backend."""
    if not raw:
        return ""
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) == 10 or len(digits) == 11:
        return f"55{digits}"
    if digits.startswith("55"):
        return digits
    # fallback: se veio com DDI diferente, tenta últimos 11
    if len(digits) > 11:
        return f"55{digits[-11:]}"
    return digits

def load_churches():
    """Lê igrejas ativas do Firestore."""
    churches = []
    for doc in db.collection(FIRESTORE_COLLECTION).where("active", "==", True).stream():
        data = doc.to_dict() or {}
        # só considera as que têm coordenadas
        if data.get("lat") is None or data.get("lon") is None:
            continue
        # opcional: adicione um maps_url baseado no endereço registrado
        addr = data.get("formatted_address") or data.get("address") or ""
        data["maps_url"] = google_maps_search_url(addr) if addr else None
        data["id"] = doc.id
        churches.append(data)
    return churches

# ========= HTTP Function =========
@functions_framework.http
def gmaps_reverse_geocode(lat: float, lon: float):
    """
    Reverse geocoding no Google para exibir endereço interpretado.
    Retorna (formatted_address, place_id) ou (None, None).
    """
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

    headers = {"Access-Control-Allow-Origin": "*"}

    req = request.get_json(silent=True) or {}
    address = (req.get("address") or "").strip()
    cep = (req.get("cep") or "").strip()
    limit = int(req.get("limit") or 3)
    max_distance_km = req.get("max_distance_km")

    # Novo: suportar lat/lon vindos do dispositivo
    lat_in = req.get("lat")
    lon_in = req.get("lon")

    # 1) Obter coordenadas do usuário
    if lat_in is not None and lon_in is not None:
        try:
            user_lat = float(lat_in)
            user_lon = float(lon_in)
        except ValueError:
            return (jsonify({"error": "Parâmetros 'lat' e 'lon' inválidos."}), 400, headers)
        # Reverse geocoding opcional p/ exibir endereço interpretado
        formatted, place_id = gmaps_reverse_geocode(user_lat, user_lon)
    else:
        if not address and not cep:
            return (jsonify({"error": "Forneça 'address'/'cep' ou 'lat' e 'lon'."}), 400, headers)
        user_query = address or cep
        user_lat, user_lon, formatted, place_id = gmaps_geocode(user_query)
        if user_lat is None or user_lon is None:
            return (jsonify({"error": "Não foi possível geocodificar seu endereço/CEP com o Google."}), 404, headers)

    # 2) Carrega igrejas
    churches = load_churches()

    # 3) Calcula distâncias
    scored = []
    for ch in churches:
        d = haversine_km(user_lat, user_lon, ch["lat"], ch["lon"])
        scored.append((d, ch))
    scored.sort(key=lambda x: x[0])

    # 4) Aplica raio se houver
    if max_distance_km is not None:
        try:
            m = float(max_distance_km)
            scored = [item for item in scored if item[0] <= m]
        except Exception:
            pass

    # 5) Limite
    scored = scored[:max(1, min(limit, 20))]

    # 6) Monta resposta
    nearest = []
    for dist_km, ch in scored:
        nearest.append({
            "id": ch["id"],
            "name": ch.get("name"),
            "address": ch.get("formatted_address") or ch.get("address"),
            "cep": ch.get("cep"),
            "day": ch.get("day"),
            "time": ch.get("time"),
            "contact": ch.get("contact"),
            "lat": ch.get("lat"),
            "lon": ch.get("lon"),
            "maps_url": ch.get("maps_url"),
            "distance": round(float(dist_km), 2),
        })

    # Endereço interpretado + link do Maps para a posição do usuário
    input_addr = formatted or (address or cep or f"{user_lat},{user_lon}")
    resp = {
        "query": {
            "input_address": input_addr,
            "maps_url": google_maps_search_url(input_addr),
            "lat": user_lat,
            "lon": user_lon,
            "place_id": place_id,
            "provider": "googlemaps",
        },
        "nearest_churches": nearest,
    }
    return (jsonify(resp), 200, headers)