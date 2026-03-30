from flask import Flask, jsonify, render_template, request
import sqlite3
import json
from datetime import datetime
import math
import ollama
import google.generativeai as genai
from ultralytics import YOLO
from haversine import haversine
from google.cloud import texttospeech
import base64
import cv2
import numpy as np

genai.configure(api_key="AIzaSyDUr8dfsUpgkIxXcisbk8DkdE4n7-4l75c")
gemini_model = genai.GenerativeModel("gemini-2.5-flash-lite")

app = Flask(__name__)

# =========================
# DATABASE INITIALIZATION
# =========================
bus_crowd_data = {}  

def init_db():
    con = sqlite3.connect("track.db")
    cur = con.cursor()

    # Bus route table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS buses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        bus_no TEXT,
        start_location TEXT,
        stops TEXT,
        destination TEXT
    )
    ''')

    # Bus GPS location table
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bus_location(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bus_no TEXT,
        lat REAL,
        lon REAL,
        time DATETIME
    )
    ''')
    cur.execute('''
    CREATE TABLE IF NOT EXISTS feedback(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        gender TEXT,
        location TEXT,
        rating INTEGER,
        comment TEXT,
        created_at DATETIME
    )
    ''')
    con.commit()
    con.close()

init_db()

# =========================
# HOME PAGE
# =========================

@app.route("/")
def home():
    return render_template("index.html")


# =========================
# DRIVER PAGE
# =========================

@app.route("/driver")
def driver():
    return render_template("driver.html")


# =========================
# ADMIN PAGE
# =========================

@app.route("/admin")
def admin():
    return render_template("admin.html")


# =========================
# ADD BUS ROUTE (ADMIN)
# =========================

@app.route("/add_bus", methods=["POST"])
def add_bus():

    data = request.json

    type = data["type"]
    bus_no = data["busNo"]
    start = data["start"]
    stops = json.dumps(data["stops"])
    destination = data["destination"]

    con = sqlite3.connect("track.db")
    cur = con.cursor()

    cur.execute('''
    INSERT INTO buses(type,bus_no,start_location,stops,destination)
    VALUES(?,?,?,?,?)
    ''',(type,bus_no,start,stops,destination))

    con.commit()
    con.close()

    return jsonify({"message":"Bus added successfully"})


# =========================
# GET ALL BUSES
# =========================

@app.route("/buses")
def get_buses():

    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    buses = cur.execute("SELECT * FROM buses").fetchall()

    result = []

    for bus in buses:
        result.append({
            "bus_no": bus["bus_no"],
            "type": bus["type"],
            "start": bus["start_location"],
            "stops": json.loads(bus["stops"]),
            "destination": bus["destination"]
        })

    con.close()

    return jsonify(result)


# =========================
# SEARCH BUS BY ROUTE
# =========================

@app.route("/search_bus", methods=["POST"])
def search_bus():

    data = request.json
    bus_no = data.get("bus_no")
    start = data.get("start")
    destination = data.get("destination")

    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    buses = cur.execute("SELECT * FROM buses").fetchall()

    matched = []

    for bus in buses:

        stops = json.loads(bus["stops"])

        route = [bus["start_location"]]

        for s in stops:
            route.append(s["name"])

        route.append(bus["destination"])

        # Search by bus number
        if bus_no and bus_no.lower() in bus["bus_no"].lower():
            matched.append({
                "bus_no": bus["bus_no"],
                "type": bus["type"]
            })
            continue

        # Search by destination
        if destination and destination in route:
            matched.append({
                "bus_no": bus["bus_no"],
                "type": bus["type"]
            })
            continue

        # Search by start and destination
        if start and destination:
            if start in route and destination in route:
                if route.index(start) < route.index(destination):
                    matched.append({
                        "bus_no": bus["bus_no"],
                        "type": bus["type"]
                    })

    con.close()

    return jsonify(matched)


# =========================
# UPDATE BUS GPS LOCATION
# =========================

@app.route("/update_location", methods=["POST"])
def update_location():

    data = request.json

    bus_no = data["bus_no"]
    lat = float(data["lat"])
    lon = float(data["lon"])

    con = sqlite3.connect("track.db")
    cur = con.cursor()

    cur.execute('''
    INSERT INTO bus_location(bus_no,lat,lon,time)
    VALUES(?,?,?,?)
    ''',(bus_no,lat,lon,datetime.now()))

    con.commit()
    con.close()

    return jsonify({"status":"location updated"})


# =========================
# GET LIVE BUS LOCATION
# =========================

@app.route("/bus_location/<bus_no>")
def bus_location(bus_no):

    con = sqlite3.connect("track.db")
    cur = con.cursor()

    cur.execute("""
    SELECT lat,lon FROM bus_location
    WHERE bus_no=?
    ORDER BY id DESC
    LIMIT 1
    """,(bus_no,))

    row = cur.fetchone()

    con.close()

    if row:
        return jsonify({
            "lat":row[0],
            "lon":row[1]
        })
    else:
        return jsonify({"error":"No location found"})
# @app.route("/bus/<bus_no>")
# def bus_details(bus_no):

#     con = sqlite3.connect("track.db")
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()

#     bus = cur.execute(
#         "SELECT * FROM buses WHERE bus_no=?",
#         (bus_no,)
#     ).fetchone()

#     con.close()

#     if bus:

#         return render_template(
#             "bus_details.html",
#             bus_no=bus["bus_no"],
#             type=bus["type"],
#             start=bus["start_location"],
#             stops=json.loads(bus["stops"]),
#             destination=bus["destination"]
#         )

#     return "Bus not found"

# ✅ KEEP ONLY THIS — delete the other @app.route("/bus/<bus_no>")
@app.route("/bus/<bus_no>")
def bus_details(bus_no):

    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    bus = cur.execute(
        "SELECT * FROM buses WHERE bus_no=?",
        (bus_no,)
    ).fetchone()

    con.close()

    if bus:
        return render_template(        # ← add return
            "bus_track.html",          # ← your actual template filename
            bus_no=bus["bus_no"],
            type=bus["type"],
            start=bus["start_location"],
            stops=json.loads(bus["stops"]),   # ← pass as list, NOT json.dumps
            destination=bus["destination"]
        )

    return "Bus not found"

# @app.route("/nearest_stop", methods=["POST"])
# def nearest_stop():

#     data = request.json
#     user_lat = float(data["lat"])
#     user_lon = float(data["lon"])

#     con = sqlite3.connect("track.db")
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()

#     buses = cur.execute("SELECT * FROM buses").fetchall()

#     nearest_stop = None
#     nearest_bus = None
#     min_distance = 999999

#     for bus in buses:

#         stops = json.loads(bus["stops"])

#         for s in stops:

#             stop_lat = float(s["lat"])
#             stop_lon = float(s["lon"])

#             # Haversine distance
#             R = 6371

#             dlat = math.radians(stop_lat - user_lat)
#             dlon = math.radians(stop_lon - user_lon)

#             a = math.sin(dlat/2)**2 + math.cos(math.radians(user_lat)) * math.cos(math.radians(stop_lat)) * math.sin(dlon/2)**2
#             c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

#             distance = R * c

#             if distance < min_distance:
#                 min_distance = distance
#                 nearest_stop = s["name"]
#                 nearest_bus = bus["bus_no"]
    
          

#     con.close()

#     if nearest_stop:

#         return jsonify({
#             "bus_no": nearest_bus,
#             "stop": nearest_stop,
#             "distance_km": round(min_distance, 2)
#         })

#     else:
#         return jsonify({
#             "error": "No stops found"
#         })

@app.route("/nearest_stop", methods=["POST"])
def nearest_stop():
    user_start_lat = float(request.args.get("start_lat"))
    user_start_lon = float(request.args.get("start_lon"))
    user_dest_lat = float(request.args.get("dest_lat"))
    user_dest_lon = float(request.args.get("dest_lon"))

    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    buses = cur.execute("SELECT * FROM buses").fetchall()
    result = []

    R = 6371  # Earth radius

    def haversine(lat1, lon1, lat2, lon2):
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        return R * c

    for bus in buses:
        stops = json.loads(bus["stops"])

        # Find closest stop to start
        start_distances = [haversine(user_start_lat, user_start_lon, s["lat"], s["lon"]) for s in stops]
        end_distances = [haversine(user_dest_lat, user_dest_lon, s["lat"], s["lon"]) for s in stops]

        start_idx = start_distances.index(min(start_distances))
        end_idx = end_distances.index(min(end_distances))

        # Ensure correct direction
        if start_idx > end_idx:
            start_idx, end_idx = end_idx, start_idx

        # Consider only stops along the route from start to destination
        segment_stops = stops[start_idx:end_idx+1]

        # Find nearest stop along this segment to the user's starting point
        nearest_stop = min(
            segment_stops,
            key=lambda s: haversine(user_start_lat, user_start_lon, s["lat"], s["lon"])
        )

        result.append({
            "bus_no": bus["bus_no"],
            "nearest_stop": {
                "name": nearest_stop["name"],
                "lat": nearest_stop["lat"],
                "lon": nearest_stop["lon"],
                "distance_km": round(haversine(user_start_lat, user_start_lon, nearest_stop["lat"], nearest_stop["lon"]), 4)
            }
        })

    con.close()
    return jsonify(result)

@app.route("/route_suggestions", methods=["POST"])
def route_suggestions():

    data = request.json

    user_lat = float(data["lat"])
    user_lon = float(data["lon"])
    destination = data["destination"]

    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    buses = cur.execute("SELECT * FROM buses").fetchall()

    fastest = None
    cheapest = None

    min_time = 999999
    min_cost = 999999

    for bus in buses:

        stops = json.loads(bus["stops"])

        for s in stops:

            stop_lat = float(s["lat"])
            stop_lon = float(s["lon"])

            # distance calculation
            R = 6371

            dlat = math.radians(stop_lat - user_lat)
            dlon = math.radians(stop_lon - user_lon)

            a = math.sin(dlat/2)**2 + math.cos(math.radians(user_lat)) * math.cos(math.radians(stop_lat)) * math.sin(dlon/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

            distance = R * c

            # assume bus speed 30km/h
            time_minutes = (distance / 30) * 60

            # assume ₹5 per km
            cost = distance * 5

            if time_minutes < min_time:
                min_time = time_minutes
                fastest = {
                    "bus": bus["bus_no"],
                    "time": round(time_minutes)
                }

            if cost < min_cost:
                min_cost = cost
                cheapest = {
                    "bus": bus["bus_no"],
                    "cost": round(cost)
                }

    con.close()

    return jsonify({
        "fastest": fastest,
        "cheapest": cheapest
    })
# @app.route("/plan_trip", methods=["POST"])
# def plan_trip():

#     data = request.json

#     start = data["start"].strip().lower()
#     destination = data["destination"].strip().lower()

#     con = sqlite3.connect("track.db")
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()

#     buses = cur.execute("SELECT * FROM buses").fetchall()

#     direct_routes = []
#     transfer_routes = []

#     # Convert buses to route lists
#     routes = []

#     for bus in buses:

#         stops = json.loads(bus["stops"])

#         route = [bus["start_location"].lower()]

#         for s in stops:
#             route.append(s["name"].lower())

#         route.append(bus["destination"].lower())

#         routes.append({
#             "bus": bus["bus_no"],
#             "route": route
#         })

#     # DIRECT BUS
#     for r in routes:

#         if start in r["route"] and destination in r["route"]:

#             if r["route"].index(start) < r["route"].index(destination):

#                 direct_routes.append({
#                     "bus": r["bus"]
#                 })

#     # TRANSFER BUS
#     for r1 in routes:

#         if start in r1["route"]:

#             for transfer in r1["route"]:

#                 for r2 in routes:

#                     if transfer in r2["route"] and destination in r2["route"]:

#                         if r2["route"].index(transfer) < r2["route"].index(destination):

#                             transfer_routes.append({
#                                 "bus1": r1["bus"],
#                                 "bus2": r2["bus"],
#                                 "transfer": transfer
#                             })

#     con.close()

#     return jsonify({
#         "direct": direct_routes,
#         "transfer": transfer_routes
#     })
# @app.route("/ai_chat", methods=["POST"])
# def ai_chat():

#     data=request.json
#     message=data["message"]

#     con=sqlite3.connect("track.db")
#     con.row_factory=sqlite3.Row
#     cur=con.cursor()

#     buses=cur.execute("SELECT * FROM buses").fetchall()

#     routes=[]

#     for bus in buses:

#         stops=json.loads(bus["stops"])

#         route=[bus["start_location"]]

#         for s in stops:
#             route.append(s["name"])

#         route.append(bus["destination"])

#         routes.append({
#             "bus":bus["bus_no"],
#             "route":route
#         })

#     prompt=f"""
# You are a bus travel assistant.

# Bus routes:
# {routes}

# User question:
# {message}

# Explain how the user can travel using buses.
# If no direct bus exists suggest nearest stop and transfer.
# """

#     response=ollama.chat(
#         model="phi3",
#         messages=[{"role":"user","content":prompt}]
#     )

#     return jsonify({
#         "reply":response["message"]["content"]
#     })
# @app.route("/ai_page")
# def ai_page():

#     message = request.args.get("message")

#     con = sqlite3.connect("track.db")
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()

#     buses = cur.execute("SELECT * FROM buses").fetchall()

#     routes = []

#     for bus in buses:

#         stops = json.loads(bus["stops"])

#         route = [bus["start_location"]]

#         for s in stops:
#             route.append(s["name"])

#         route.append(bus["destination"])

#         routes.append({
#             "bus": bus["bus_no"],
#             "route": route
#         })

#     prompt=f"""
# You are a smart bus assistant.

# Bus routes:
# {routes}

# User question:
# {message}

# Explain clearly how the user can travel.
# If no direct bus exists suggest transfer buses.
# """

#     response = ollama.chat(
#         model="phi3",
#         messages=[{"role":"user","content":prompt}]
#     )

#     answer = response["message"]["content"]

#     return render_template(
#         "ai.html",
#         question=message,
#         answer=answer

#     )


# @app.route("/askAi", methods=["POST"])
# def askAi():

#     data = request.json
#     message = data["message"]

#     con = sqlite3.connect("track.db")
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()

#     buses = cur.execute("SELECT * FROM buses").fetchall()

#     routes = []

#     for bus in buses:

#         stops = json.loads(bus["stops"])

#         route = [bus["start_location"]]

#         for s in stops:
#             route.append(s["name"])

#         route.append(bus["destination"])

#         routes.append({
#             "bus": bus["bus_no"],
#             "route": route
#         })

#     prompt = f"""
# You are a smart bus assistant.

# Bus routes:
# {routes}

# User question:
# {message}

# Explain clearly how the user can travel.
# If no direct bus exists suggest transfer buses.
# """

#     response = model.generate_content(prompt)

#     return jsonify({
#         "reply": response.text
#     })


# def text_to_speech(text):
#     client = texttospeech.TextToSpeechClient()

#     synthesis_input = texttospeech.SynthesisInput(text=text)

#     voice = texttospeech.VoiceSelectionParams(
#         language_code="en-IN",
#         name="en-IN-Wavenet-D"   # 🔥 natural voice
#     )

#     audio_config = texttospeech.AudioConfig(
#         audio_encoding=texttospeech.AudioEncoding.MP3
#     )

#     response = client.synthesize_speech(
#         input=synthesis_input,
#         voice=voice,
#         audio_config=audio_config
#     )

#     return base64.b64encode(response.audio_content).decode("utf-8")
@app.route("/askAi", methods=["POST"])
def askAi():

    data = request.json
    message = data.get("message","")

    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    buses = cur.execute("SELECT * FROM buses").fetchall()

    routes = []

    for bus in buses:

        stops = json.loads(bus["stops"])

        route = [bus["start_location"]]

        for s in stops:
            route.append(s["name"])

        route.append(bus["destination"])

        routes.append({
            "bus": bus["bus_no"],
            "route": route
        })

    prompt = f"""
You are a smart bus assistant.

Bus routes:
{routes}

User question:
{message}

Give a SHORT and CLEAR answer.

Rules:
- No long explanations
- No extra details
- Be direct and simple
- Use bullet points if needed

Output format (STRICTLY follow this):
🚌 Bus Option 1
Bus No: <bus number>
Route: <From> → <To>
'\\n\\n'
Stops: <stop1 → stop2 → stop3 → ...>
'\\n\\n'

🚌 Bus Option 2
Bus No: <bus number>
Route: <From> → <To>
Stops: <stop1 → stop2 → ...>
(blank line)

🚌 Bus Option 3
Bus No: <bus number>
Route: <From> → <To>
Stops: <...>

(continue for all buses)

🔁 If transfer required:
Transfer at: <stop name>

   1️⃣ Bus No: <bus number>
   Route: <From> → <To>

   2️⃣ Bus No: <bus number>
   Route: <From> → <To>

Important:
- Do NOT limit number of buses
- Show all matching buses
- Keep stops minimal (only important stops)
- Maintain clean spacing between options
- No extra explanation text

If no route found:
❌ No direct or simple route available

"""

    try:

        response = gemini_model.generate_content(prompt)

        reply = response.text if response.text else "I couldn't generate a response."

    except Exception as e:
        reply = "AI error: " + str(e)
     

    return jsonify({
        "reply": reply,

    })    
    
 
yolo_model = YOLO("yolo26n.pt")

@app.route("/update_occupancy", methods=["POST"])
def update_occupancy():

    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    bus_no = request.form.get("bus_no", "unknown")

    file = request.files['image']

    # Convert image to OpenCV format
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Run YOLO inference (detect only people -> class 0)
    results = yolo_model.predict(
        source=img,
        classes=[0],      # 0 = person
        conf=0.30,
        iou=0.45,
        device="cpu",
        verbose=False
    )

    # Extract detected boxes
    boxes = results[0].boxes

    # Count number of people
    if boxes is not None:
        passenger_count = len(boxes)
    else:
        passenger_count = 0

    # Crowd status logic
    if passenger_count <= 15:
        status = "Low"
    elif passenger_count <= 30:
        status = "Medium"
    else:
        status = "High / Crowded"
    # Save YOLO result for this bus
    bus_crowd_data[bus_no] = {
        "passenger_count": passenger_count,
        "status": status
    }

    return jsonify({
        "bus_no": bus_no,
        "passenger_count": passenger_count,
        "status": status
    })
    # return jsonify({
    #     "bus_no": bus_no,
    #     "passenger_count": passenger_count,
    #     "status": status
    # })


@app.route("/bus_status/<bus_no>")
def bus_status(bus_no):
        if bus_no in bus_crowd_data:
            return jsonify(bus_crowd_data[bus_no])
        return jsonify({
    "passenger_count": 0,
    "status": "Unknown"
    })
 
 
@app.route("/plan_trip", methods=["POST"])
def plan_trip():
    import sqlite3, json, math
    from flask import request, jsonify

    # ---- HAVERSINE FUNCTION ----
    def haversine(lat1, lon1, lat2, lon2):
        R = 6371  # km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c

    # ---- FARE FUNCTION ----
    def calculate_fare(distance, bus_type):
        distance = float(distance or 0)
        bus_type = (bus_type or "ordinary").lower()

        if bus_type == "ordinary":
            rate = 5
        elif bus_type == "express":
            rate = 8
        else:
            rate = 6

        return round(distance * rate)

    # ---- INPUT ----
    data = request.json
    start = data["start"].strip().lower()
    destination = data["destination"].strip().lower()

    # ---- DB ----
    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    buses = cur.execute("SELECT * FROM buses").fetchall()

    direct_routes = []
    transfer_routes = []
    routes = []

    # ---- PREPARE ROUTES ----
    for bus in buses:
        stops = json.loads(bus["stops"])

        all_stops = (
            [{"name": bus["start_location"], "lat": stops[0]["lat"] if stops else 0, "lon": stops[0]["lon"] if stops else 0}]
            + stops +
            [{"name": bus["destination"], "lat": stops[-1]["lat"] if stops else 0, "lon": stops[-1]["lon"] if stops else 0}]
        )

        route_names = [s["name"].strip().lower() for s in all_stops]

        routes.append({
            "bus": bus["bus_no"],
            "type": bus["type"],
            "route": route_names,
            "all_stops": all_stops
        })

    # =========================
    # 🚍 DIRECT BUS
    # =========================
    for r in routes:
        if start in r["route"] and destination in r["route"]:
            si = r["route"].index(start)
            di = r["route"].index(destination)

            if si < di:
                segment = r["all_stops"][si:di+1]

                total_km = 0.0
                for i in range(len(segment)-1):
                    a, b = segment[i], segment[i+1]
                    try:
                        total_km += haversine(float(a["lat"]), float(a["lon"]),
                                              float(b["lat"]), float(b["lon"]))
                    except:
                        pass

                fare = calculate_fare(total_km, r["type"])
                est_mins = round((total_km / 30) * 60)

                # direct_routes.append({
                #     "bus": r["bus"],
                #     "type": r["type"],
                #     "distance": round(total_km, 2),
                #     "fare": fare,
                #     "est_mins": est_mins,
                #     "from": r["all_stops"][si]["name"],
                #     "to": r["all_stops"][di]["name"]
                # })
                direct_routes.append({
                    "bus": r["bus"],
                    "distance": total_km,
                    "fare": round(total_km * 1),   # ₹1 per km (as you wanted earlier)
                    "est_mins": est_mins
                    })

    # =========================
    # 🔁 TRANSFER BUS
    # =========================
    for r1 in routes:
        if start not in r1["route"]:
            continue

        si1 = r1["route"].index(start)

        for transfer_name in r1["route"][si1:]:
            for r2 in routes:

                if r1["bus"] == r2["bus"]:
                    continue

                if transfer_name not in r2["route"] or destination not in r2["route"]:
                    continue

                ti2 = r2["route"].index(transfer_name)
                di2 = r2["route"].index(destination)

                if ti2 >= di2:
                    continue

                # ---- LEG 1 ----
                segment1 = r1["all_stops"][si1 : r1["route"].index(transfer_name)+1]
                dist1 = 0.0

                for i in range(len(segment1)-1):
                    a, b = segment1[i], segment1[i+1]
                    try:
                        dist1 += haversine(float(a["lat"]), float(a["lon"]),
                                           float(b["lat"]), float(b["lon"]))
                    except:
                        pass

                fare1 = calculate_fare(dist1, r1["type"])

                # ---- LEG 2 ----
                segment2 = r2["all_stops"][ti2 : di2+1]
                dist2 = 0.0

                for i in range(len(segment2)-1):
                    a, b = segment2[i], segment2[i+1]
                    try:
                        dist2 += haversine(float(a["lat"]), float(a["lon"]),
                                           float(b["lat"]), float(b["lon"]))
                    except:
                        pass

                fare2 = calculate_fare(dist2, r2["type"])

                total_distance = round(dist1 + dist2, 2)
                total_fare = fare1 + fare2

                #est_time = round((total_km / 30) * 60) if total_km else 0
                est_time = round((total_distance / 30) * 60)

                transfer_routes.append({
                    "bus1": r1["bus"],
                    "bus2": r2["bus"],
                    "transfer": transfer_name,
                    "distance": total_distance,
                    "total_fare": round(total_distance * 1),  # ₹1 per km
                    "est_mins": est_time
})
                # est_mins = round((total_distance / 30) * 60)

                # transfer_routes.append({
                #     "bus1": r1["bus"],
                #     "bus2": r2["bus"],
                #     "transfer": transfer_name,
                #     "distance": total_distance,
                #     "total_fare": total_fare,
                #     "est_mins": est_mins
                # })

    con.close()

    return jsonify({
        "direct": direct_routes,
        "transfer": transfer_routes
    }) 
@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    data     = request.json
    name     = data.get("name", "").strip()
    gender   = data.get("gender", "").strip()
    location = data.get("location", "").strip()
    rating   = int(data.get("rating", 0))
    comment  = data.get("comment", "").strip()

    if not name or not rating:
        return jsonify({"error": "Name and rating are required"}), 400

    con = sqlite3.connect("track.db")
    cur = con.cursor()
    cur.execute(
        "INSERT INTO feedback(name,gender,location,rating,comment,created_at) VALUES(?,?,?,?,?,?)",
        (name, gender, location, rating, comment, datetime.now())
    )
    con.commit()
    con.close()
    return jsonify({"message": "Feedback submitted successfully"})


@app.route("/get_feedback")
def get_feedback():
    con = sqlite3.connect("track.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute("SELECT * FROM feedback ORDER BY created_at DESC").fetchall()
    con.close()
    return jsonify([{
        "id": r["id"], "name": r["name"], "gender": r["gender"],
        "location": r["location"], "rating": r["rating"],
        "comment": r["comment"], "created_at": str(r["created_at"])
    } for r in rows])

    

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
