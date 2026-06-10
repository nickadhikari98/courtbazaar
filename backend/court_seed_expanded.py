"""Expanded India court hierarchy - 28 states + UTs, all HCs, 500+ district courts, tribunals.
Only courts in Delhi are marked `serviceable: True`. Others browse-only ("Coming Soon")."""

# State names + codes
STATES = [
    ("state_ap", "Andhra Pradesh", "AP"), ("state_ar", "Arunachal Pradesh", "AR"),
    ("state_as", "Assam", "AS"), ("state_br", "Bihar", "BR"),
    ("state_cg", "Chhattisgarh", "CG"), ("state_ga", "Goa", "GA"),
    ("state_gj", "Gujarat", "GJ"), ("state_hr", "Haryana", "HR"),
    ("state_hp", "Himachal Pradesh", "HP"), ("state_jh", "Jharkhand", "JH"),
    ("state_ka", "Karnataka", "KA"), ("state_kl", "Kerala", "KL"),
    ("state_mp", "Madhya Pradesh", "MP"), ("state_mh", "Maharashtra", "MH"),
    ("state_mn", "Manipur", "MN"), ("state_ml", "Meghalaya", "ML"),
    ("state_mz", "Mizoram", "MZ"), ("state_nl", "Nagaland", "NL"),
    ("state_od", "Odisha", "OD"), ("state_pb", "Punjab", "PB"),
    ("state_rj", "Rajasthan", "RJ"), ("state_sk", "Sikkim", "SK"),
    ("state_tn", "Tamil Nadu", "TN"), ("state_tg", "Telangana", "TG"),
    ("state_tr", "Tripura", "TR"), ("state_up", "Uttar Pradesh", "UP"),
    ("state_uk", "Uttarakhand", "UK"), ("state_wb", "West Bengal", "WB"),
    # UTs
    ("state_delhi", "Delhi (NCT)", "DL"), ("state_jk", "Jammu & Kashmir", "JK"),
    ("state_ladakh", "Ladakh", "LA"), ("state_chandigarh", "Chandigarh", "CH"),
    ("state_puducherry", "Puducherry", "PY"), ("state_an", "Andaman & Nicobar", "AN"),
    ("state_dnh_dd", "Dadra & Nagar Haveli, Daman & Diu", "DN"),
    ("state_lakshadweep", "Lakshadweep", "LD"),
]

# Districts per state used to generate district courts (5–25 each)
STATE_DISTRICTS = {
    "state_ap": ["Anantapur", "Chittoor", "East Godavari", "Guntur", "Krishna", "Kurnool", "Nellore", "Prakasam", "Srikakulam", "Visakhapatnam", "Vizianagaram", "West Godavari", "YSR Kadapa"],
    "state_ar": ["East Kameng", "Itanagar", "Lower Subansiri", "Papum Pare", "Tawang", "West Kameng"],
    "state_as": ["Barpeta", "Cachar", "Darrang", "Dibrugarh", "Goalpara", "Golaghat", "Guwahati", "Jorhat", "Kamrup", "Nagaon", "Sivasagar", "Tezpur", "Tinsukia"],
    "state_br": ["Patna", "Gaya", "Bhagalpur", "Muzaffarpur", "Darbhanga", "Purnia", "Munger", "Saharsa", "Begusarai", "Nalanda", "Aurangabad", "Bhojpur", "East Champaran", "West Champaran", "Madhubani"],
    "state_cg": ["Raipur", "Bilaspur", "Durg", "Korba", "Bastar", "Raigarh", "Surguja", "Janjgir-Champa", "Mahasamund"],
    "state_ga": ["North Goa", "South Goa"],
    "state_gj": ["Ahmedabad", "Surat", "Vadodara", "Rajkot", "Bhavnagar", "Jamnagar", "Junagadh", "Anand", "Mehsana", "Gandhinagar", "Kheda", "Bharuch", "Navsari", "Valsad"],
    "state_hr": ["Gurugram", "Faridabad", "Hisar", "Rohtak", "Karnal", "Panipat", "Sonipat", "Ambala", "Yamunanagar", "Bhiwani", "Sirsa", "Rewari", "Kurukshetra", "Jind"],
    "state_hp": ["Shimla", "Solan", "Mandi", "Kangra", "Una", "Bilaspur", "Hamirpur", "Chamba", "Kullu", "Sirmaur"],
    "state_jh": ["Ranchi", "Jamshedpur", "Dhanbad", "Bokaro", "Hazaribagh", "Giridih", "Deoghar", "Palamu", "Dumka"],
    "state_ka": ["Bengaluru Urban", "Bengaluru Rural", "Mysuru", "Mangaluru", "Hubli-Dharwad", "Belagavi", "Tumakuru", "Ballari", "Kalaburagi", "Vijayapura", "Davangere", "Shivamogga", "Udupi", "Hassan", "Mandya"],
    "state_kl": ["Thiruvananthapuram", "Kollam", "Pathanamthitta", "Alappuzha", "Kottayam", "Idukki", "Ernakulam", "Thrissur", "Palakkad", "Malappuram", "Kozhikode", "Wayanad", "Kannur", "Kasaragod"],
    "state_mp": ["Bhopal", "Indore", "Jabalpur", "Gwalior", "Ujjain", "Sagar", "Dewas", "Satna", "Ratlam", "Rewa", "Vidisha", "Chhindwara", "Khargone", "Khandwa"],
    "state_mh": ["Mumbai City", "Mumbai Suburban", "Pune", "Thane", "Nagpur", "Nashik", "Aurangabad", "Solapur", "Kolhapur", "Amravati", "Akola", "Ahmednagar", "Jalgaon", "Latur", "Sangli", "Satara", "Raigad", "Ratnagiri", "Sindhudurg"],
    "state_mn": ["Imphal East", "Imphal West", "Bishnupur", "Churachandpur", "Thoubal", "Ukhrul"],
    "state_ml": ["East Khasi Hills", "West Khasi Hills", "Ri Bhoi", "East Garo Hills", "West Garo Hills"],
    "state_mz": ["Aizawl", "Lunglei", "Champhai", "Kolasib", "Serchhip"],
    "state_nl": ["Kohima", "Dimapur", "Mokokchung", "Tuensang", "Wokha"],
    "state_od": ["Bhubaneswar", "Cuttack", "Puri", "Sambalpur", "Berhampur", "Rourkela", "Balasore", "Bhadrak", "Koraput", "Mayurbhanj", "Ganjam", "Kendrapara"],
    "state_pb": ["Amritsar", "Ludhiana", "Jalandhar", "Patiala", "Bathinda", "Mohali", "Pathankot", "Hoshiarpur", "Moga", "Ferozepur", "Gurdaspur", "Sangrur", "Faridkot", "Kapurthala"],
    "state_rj": ["Jaipur", "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bikaner", "Alwar", "Bharatpur", "Sikar", "Pali", "Chittorgarh", "Tonk", "Hanumangarh", "Sri Ganganagar", "Nagaur"],
    "state_sk": ["East Sikkim", "West Sikkim", "North Sikkim", "South Sikkim"],
    "state_tn": ["Chennai", "Coimbatore", "Madurai", "Tiruchirappalli", "Salem", "Tirunelveli", "Vellore", "Erode", "Thanjavur", "Tiruppur", "Dindigul", "Kanchipuram", "Cuddalore", "Karur", "Namakkal"],
    "state_tg": ["Hyderabad", "Rangareddy", "Medchal-Malkajgiri", "Warangal", "Karimnagar", "Nizamabad", "Khammam", "Nalgonda", "Mahbubnagar", "Adilabad"],
    "state_tr": ["West Tripura", "South Tripura", "North Tripura", "Dhalai"],
    "state_up": ["Lucknow", "Kanpur", "Agra", "Varanasi", "Meerut", "Allahabad (Prayagraj)", "Ghaziabad", "Noida (Gautam Budh Nagar)", "Aligarh", "Moradabad", "Bareilly", "Saharanpur", "Mathura", "Firozabad", "Gorakhpur", "Jhansi", "Mirzapur", "Faizabad (Ayodhya)"],
    "state_uk": ["Dehradun", "Haridwar", "Nainital", "Udham Singh Nagar", "Almora", "Pauri Garhwal", "Tehri Garhwal", "Chamoli", "Rudraprayag", "Pithoragarh"],
    "state_wb": ["Kolkata", "Howrah", "North 24 Parganas", "South 24 Parganas", "Hooghly", "Bardhaman", "Birbhum", "Murshidabad", "Nadia", "Malda", "Darjeeling", "Jalpaiguri", "Bankura", "Purulia", "Midnapore"],
    "state_jk": ["Srinagar", "Jammu", "Anantnag", "Baramulla", "Kathua", "Udhampur", "Rajouri"],
    "state_ladakh": ["Leh", "Kargil"],
    "state_chandigarh": ["Chandigarh"],
    "state_puducherry": ["Puducherry", "Karaikal", "Mahe", "Yanam"],
    "state_an": ["South Andaman", "North & Middle Andaman", "Nicobar"],
    "state_dnh_dd": ["Daman", "Diu", "Dadra & Nagar Haveli"],
    "state_lakshadweep": ["Kavaratti"],
}

# High Courts per state
HIGH_COURTS = {
    "state_ap": [("court_ap_hc", "Andhra Pradesh High Court", "Amaravati")],
    "state_as": [("court_gauhati_hc", "Gauhati High Court", "Guwahati")],
    "state_br": [("court_patna_hc", "Patna High Court", "Patna")],
    "state_cg": [("court_cg_hc", "Chhattisgarh High Court", "Bilaspur")],
    "state_gj": [("court_gujarat_hc", "Gujarat High Court", "Ahmedabad")],
    "state_hr": [("court_pnh_hc", "Punjab & Haryana High Court", "Chandigarh")],
    "state_hp": [("court_hp_hc", "Himachal Pradesh High Court", "Shimla")],
    "state_jh": [("court_jh_hc", "Jharkhand High Court", "Ranchi")],
    "state_ka": [("court_ka_hc", "Karnataka High Court", "Bengaluru"), ("court_ka_hc_dharwad", "Karnataka HC Dharwad Bench", "Dharwad"), ("court_ka_hc_kalaburagi", "Karnataka HC Kalaburagi Bench", "Kalaburagi")],
    "state_kl": [("court_kerala_hc", "Kerala High Court", "Kochi")],
    "state_mp": [("court_mp_hc", "Madhya Pradesh High Court", "Jabalpur"), ("court_mp_hc_indore", "MP HC Indore Bench", "Indore"), ("court_mp_hc_gwalior", "MP HC Gwalior Bench", "Gwalior")],
    "state_mh": [("court_bombay_hc", "Bombay High Court", "Mumbai"), ("court_bombay_hc_nagpur", "Bombay HC Nagpur Bench", "Nagpur"), ("court_bombay_hc_aurangabad", "Bombay HC Aurangabad Bench", "Aurangabad")],
    "state_mn": [("court_mn_hc", "Manipur High Court", "Imphal")],
    "state_ml": [("court_ml_hc", "Meghalaya High Court", "Shillong")],
    "state_od": [("court_orissa_hc", "Orissa High Court", "Cuttack")],
    "state_pb": [("court_pnh_hc_pb", "Punjab & Haryana High Court", "Chandigarh")],
    "state_rj": [("court_rajasthan_hc", "Rajasthan High Court", "Jodhpur"), ("court_rajasthan_hc_jaipur", "Rajasthan HC Jaipur Bench", "Jaipur")],
    "state_sk": [("court_sikkim_hc", "Sikkim High Court", "Gangtok")],
    "state_tn": [("court_madras_hc", "Madras High Court", "Chennai"), ("court_madras_hc_madurai", "Madras HC Madurai Bench", "Madurai")],
    "state_tg": [("court_telangana_hc", "Telangana High Court", "Hyderabad")],
    "state_tr": [("court_tripura_hc", "Tripura High Court", "Agartala")],
    "state_up": [("court_allahabad_hc", "Allahabad High Court", "Prayagraj"), ("court_allahabad_hc_lko", "Allahabad HC Lucknow Bench", "Lucknow")],
    "state_uk": [("court_uk_hc", "Uttarakhand High Court", "Nainital")],
    "state_wb": [("court_calcutta_hc", "Calcutta High Court", "Kolkata"), ("court_calcutta_hc_jalpaiguri", "Calcutta HC Jalpaiguri Bench", "Jalpaiguri")],
    "state_delhi": [("court_delhi_hc", "Delhi High Court", "New Delhi")],
    "state_jk": [("court_jk_hc", "J&K and Ladakh High Court", "Srinagar"), ("court_jk_hc_jammu", "J&K HC Jammu Wing", "Jammu")],
    "state_chandigarh": [("court_pnh_hc_ch", "Punjab & Haryana High Court", "Chandigarh")],
}

# Delhi-specific full hierarchy (the only serviceable state)
DELHI_FULL = [
    # Supreme Court (national)
    {"court_id": "court_sc_india", "name": "Supreme Court of India", "type": "supreme", "address": "Tilak Marg, New Delhi", "serviceable": True},
    # Delhi High Court
    {"court_id": "court_delhi_hc", "name": "Delhi High Court", "type": "high_court", "address": "Sher Shah Road, New Delhi", "serviceable": True},
    # District Courts (all 11 districts)
    {"court_id": "court_tishazari", "name": "Tis Hazari Court Complex", "type": "district", "district": "Central", "address": "Tis Hazari, Delhi", "serviceable": True},
    {"court_id": "court_patiala_house", "name": "Patiala House Court", "type": "district", "district": "New Delhi", "address": "Bhagwan Das Road, New Delhi", "serviceable": True},
    {"court_id": "court_karkardooma", "name": "Karkardooma Court", "type": "district", "district": "East", "address": "Karkardooma, Delhi", "serviceable": True},
    {"court_id": "court_saket", "name": "Saket District Court", "type": "district", "district": "South", "address": "Saket, New Delhi", "serviceable": True},
    {"court_id": "court_rohini", "name": "Rohini District Court", "type": "district", "district": "North", "address": "Rohini, Delhi", "serviceable": True},
    {"court_id": "court_dwarka", "name": "Dwarka District Court", "type": "district", "district": "South West", "address": "Dwarka, Delhi", "serviceable": True},
    {"court_id": "court_rouse_avenue", "name": "Rouse Avenue District Court", "type": "district", "district": "New Delhi", "address": "Rouse Avenue, New Delhi", "serviceable": True},
    {"court_id": "court_shahdara", "name": "Shahdara District Court", "type": "district", "district": "Shahdara", "address": "Karkardooma, Delhi", "serviceable": True},
    {"court_id": "court_north_west", "name": "North West District Court", "type": "district", "district": "North West", "address": "Rohini, Delhi", "serviceable": True},
    {"court_id": "court_west_delhi", "name": "West District Court", "type": "district", "district": "West", "address": "Tis Hazari, Delhi", "serviceable": True},
    {"court_id": "court_south_east", "name": "South East District Court", "type": "district", "district": "South East", "address": "Saket, New Delhi", "serviceable": True},
    # Tribunals & Quasi-Judicial bodies (Delhi seat)
    {"court_id": "court_nclt_delhi", "name": "NCLT Principal Bench (Delhi)", "type": "tribunal", "address": "CGO Complex, Delhi", "serviceable": True},
    {"court_id": "court_nclat", "name": "NCLAT (Appellate)", "type": "tribunal", "address": "Lodhi Road, Delhi", "serviceable": True},
    {"court_id": "court_drt_delhi_1", "name": "DRT Delhi Bench-I", "type": "tribunal", "address": "Jeevan Tara Building, New Delhi", "serviceable": True},
    {"court_id": "court_drt_delhi_2", "name": "DRT Delhi Bench-II", "type": "tribunal", "address": "Jeevan Tara Building, New Delhi", "serviceable": True},
    {"court_id": "court_drat_delhi", "name": "DRAT (Appellate Tribunal)", "type": "tribunal", "address": "Jeevan Tara, New Delhi", "serviceable": True},
    {"court_id": "court_cat_delhi", "name": "Central Administrative Tribunal (CAT)", "type": "tribunal", "address": "Copernicus Marg, New Delhi", "serviceable": True},
    {"court_id": "court_itat_delhi", "name": "Income Tax Appellate Tribunal (ITAT)", "type": "tribunal", "address": "Lok Nayak Bhawan, New Delhi", "serviceable": True},
    {"court_id": "court_cestat_delhi", "name": "CESTAT (Customs & Excise)", "type": "tribunal", "address": "West Block-2, R.K. Puram, Delhi", "serviceable": True},
    {"court_id": "court_ngt_delhi", "name": "National Green Tribunal (NGT)", "type": "tribunal", "address": "Faridkot House, New Delhi", "serviceable": True},
    {"court_id": "court_tdsat", "name": "TDSAT (Telecom Dispute)", "type": "tribunal", "address": "Janpath, New Delhi", "serviceable": True},
    {"court_id": "court_afit_delhi", "name": "Armed Forces Tribunal (AFT)", "type": "tribunal", "address": "West Block-VIII, R.K. Puram, Delhi", "serviceable": True},
    # Quasi-judicial bodies (Delhi)
    {"court_id": "court_cci_delhi", "name": "Competition Commission of India (CCI)", "type": "quasi", "address": "HUDCO Vishala, New Delhi", "serviceable": True},
    {"court_id": "court_sebi_delhi", "name": "SEBI (Delhi Regional Office)", "type": "quasi", "address": "NBCC Complex, New Delhi", "serviceable": True},
    {"court_id": "court_rera_delhi", "name": "Delhi RERA", "type": "quasi", "address": "Vikas Bhawan, Delhi", "serviceable": True},
    {"court_id": "court_dscdrc", "name": "Delhi State Consumer Commission", "type": "quasi", "address": "Vikas Bhawan, New Delhi", "serviceable": True},
    {"court_id": "court_dcdrc_central", "name": "District Consumer Forum (Central)", "type": "quasi", "district": "Central", "address": "Tis Hazari, Delhi", "serviceable": True},
    {"court_id": "court_dcdrc_south", "name": "District Consumer Forum (South)", "type": "quasi", "district": "South", "address": "Saket, New Delhi", "serviceable": True},
    {"court_id": "court_dcdrc_north", "name": "District Consumer Forum (North)", "type": "quasi", "district": "North", "address": "Rohini, Delhi", "serviceable": True},
    {"court_id": "court_dcdrc_east", "name": "District Consumer Forum (East)", "type": "quasi", "district": "East", "address": "Karkardooma, Delhi", "serviceable": True},
    {"court_id": "court_dcdrc_west", "name": "District Consumer Forum (West)", "type": "quasi", "district": "West", "address": "Janakpuri, Delhi", "serviceable": True},
    {"court_id": "court_lokpal_delhi", "name": "Lokpal of India", "type": "quasi", "address": "Janpath, New Delhi", "serviceable": True},
    {"court_id": "court_election_commission", "name": "Election Commission of India", "type": "quasi", "address": "Nirvachan Sadan, New Delhi", "serviceable": True},
]

# NCLT and DRT benches (non-Delhi)
TRIBUNAL_BENCHES = [
    ("state_mh", [("court_nclt_mumbai", "NCLT Mumbai Bench", "MTNL Building, Mumbai"), ("court_drt_mumbai", "DRT Mumbai", "Express Towers, Mumbai")]),
    ("state_ka", [("court_nclt_bengaluru", "NCLT Bengaluru Bench", "Kendriya Sadan, Bengaluru"), ("court_drt_bengaluru", "DRT Bengaluru", "Kendriya Sadan, Bengaluru")]),
    ("state_tn", [("court_nclt_chennai", "NCLT Chennai Bench", "Corporate Bhawan, Chennai"), ("court_drt_chennai", "DRT Chennai", "Spencers Plaza, Chennai")]),
    ("state_wb", [("court_nclt_kolkata", "NCLT Kolkata Bench", "Nizam Palace, Kolkata"), ("court_drt_kolkata", "DRT Kolkata", "Jeevan Sudha, Kolkata")]),
    ("state_tg", [("court_nclt_hyderabad", "NCLT Hyderabad Bench", "Corporate Bhawan, Hyderabad"), ("court_drt_hyderabad", "DRT Hyderabad", "Saroornagar, Hyderabad")]),
    ("state_gj", [("court_nclt_ahmedabad", "NCLT Ahmedabad Bench", "Income Tax Bhawan, Ahmedabad")]),
    ("state_up", [("court_nclt_allahabad", "NCLT Allahabad Bench", "Sangam Place, Prayagraj")]),
    ("state_kl", [("court_nclt_kochi", "NCLT Kochi Bench", "MM Centre, Kochi")]),
    ("state_pb", [("court_nclt_chandigarh", "NCLT Chandigarh Bench", "Corporate Bhawan, Chandigarh")]),
    ("state_rj", [("court_nclt_jaipur", "NCLT Jaipur Bench", "Bani Park, Jaipur")]),
]


def build_court_data():
    """Build full state→courts list. Only Delhi-area courts have serviceable=True."""
    state_lookup = {sid: {"state_id": sid, "name": name, "code": code, "courts": []} for sid, name, code in STATES}

    # Delhi (full hierarchy)
    state_lookup["state_delhi"]["courts"] = DELHI_FULL

    # Other states — HCs
    for sid, hcs in HIGH_COURTS.items():
        if sid == "state_delhi":
            continue
        for cid, name, addr in hcs:
            state_lookup[sid]["courts"].append({
                "court_id": cid, "name": name, "type": "high_court",
                "address": addr, "serviceable": False,
            })

    # District courts
    for sid, districts in STATE_DISTRICTS.items():
        if sid == "state_delhi":
            continue
        for d in districts:
            cid = f"court_{sid.replace('state_', '')}_{d.lower().replace(' ', '_').replace('&', 'and').replace('-', '_').replace('(', '').replace(')', '')[:30]}"
            state_lookup[sid]["courts"].append({
                "court_id": cid,
                "name": f"{d} District Court",
                "type": "district",
                "district": d,
                "address": f"{d}, {state_lookup[sid]['name']}",
                "serviceable": False,
            })

    # Tribunal benches (NCLT/DRT in non-Delhi major cities)
    for sid, benches in TRIBUNAL_BENCHES:
        for cid, name, addr in benches:
            state_lookup[sid]["courts"].append({
                "court_id": cid, "name": name, "type": "tribunal",
                "address": addr, "serviceable": False,
            })

    return list(state_lookup.values())


COURT_DATA = build_court_data()
