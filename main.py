# main.py
#
# Streamlit UI and family graph visualization.
# Data loading:      ged_parser.py
# Graph traversal:   graph_utils.py
# Kinship terms:     relationships.py

import json
import unicodedata
from html import escape

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components

from ged_parser import load_gedcom
from graph_utils import blood_anchor, common_ancestor, expand_with_spouses, find_blood_spouse
from relationships import compute_vietnamese_kinship


# ----------------------------
# Load GEDCOM
# ----------------------------
@st.cache_resource
def get_gedcom_data():
    return load_gedcom("data/nguyen.ged")

G_full, G_anc, names, genders, birth_years = get_gedcom_data()


# ----------------------------
# Name search helpers
# ----------------------------
def normalize(text):
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d")
    return text

search_names = {pid: normalize(name) for pid, name in names.items()}

def find_person(query):
    q_words = normalize(query).split()
    matches = []
    for pid, name in search_names.items():
        if all(word in name.split() for word in q_words):
            matches.append(pid)
    return matches


# ----------------------------
# Family graph visualization
# ----------------------------
def draw_family_graph(id1, id2, ca, ego_id=None):
    if ego_id is None:
        ego_id = id1

    # Resolve married-in spouses to their blood anchor
    draw_id1 = blood_anchor(id1, G_full, G_anc, reference_pid=id1)
    draw_id2 = blood_anchor(id2, G_full, G_anc, reference_pid=id1)

    # Track which original IDs were married-in (spouse_node, blood_anchor)
    spouse_pairs = []
    if draw_id1 != id1:
        spouse_pairs.append((id1, draw_id1))
    if draw_id2 != id2:
        spouse_pairs.append((id2, draw_id2))

    def path_from_ca(ca, target):
        try:
            return nx.shortest_path(G_anc, ca, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            ca_spouse = find_blood_spouse(ca, G_full, G_anc)
            if ca_spouse:
                try:
                    p = nx.shortest_path(G_anc, ca_spouse, target)
                    return [ca] + p
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
            return [ca]

    path1 = path_from_ca(ca, draw_id1)
    path2 = path_from_ca(ca, draw_id2)

    all_nodes = list(dict.fromkeys(path1 + path2))
    for spouse_node, _ in spouse_pairs:
        if spouse_node not in all_nodes:
            all_nodes.append(spouse_node)

    # Generation levels
    levels = {ca: 0}
    for i, pid in enumerate(path1):
        levels[pid] = i
    for i, pid in enumerate(path2):
        levels[pid] = i
    for spouse_node, anchor_node in spouse_pairs:
        levels[spouse_node] = levels.get(anchor_node, 1)

    # x/y positions
    x_spacing = 220
    y_spacing = 140
    x_positions = {ca: 0}
    for pid in path1[1:]:
        x_positions[pid] = -x_spacing
    for pid in path2[1:]:
        x_positions[pid] = x_spacing
    for spouse_node, anchor_node in spouse_pairs:
        anchor_x = x_positions.get(anchor_node, x_spacing)
        x_positions[spouse_node] = anchor_x + x_spacing
    for pid in all_nodes:
        if pid not in x_positions:
            x_positions[pid] = 0

    y_positions = {pid: levels.get(pid, 0) * y_spacing for pid in all_nodes}

    # Build vis.js nodes
    vis_nodes = []
    highlight_ids = {id1, id2}

    for pid in all_nodes:
        name     = names.get(pid, "Unknown")
        year     = birth_years.get(pid)
        kin_term = compute_vietnamese_kinship(ego_id, pid, G_anc, G_full, genders, birth_years)

        label_parts = [escape(str(name))]
        if year:
            label_parts.append(f"({year})")
        if kin_term:
            label_parts.append(escape(str(kin_term)))
        label = "\n".join(label_parts)

        if pid == ca:
            border, bg = "#cc0000", "#ffcccc"
        elif pid in highlight_ids:
            border, bg = "#0055cc", "#cce5ff"
        else:
            border, bg = "#cc7700", "#ffe5b4"

        vis_nodes.append({
            "id":    pid,
            "label": label,
            "shape": "box",
            "x":     x_positions[pid],
            "y":     y_positions[pid],
            "fixed": True,
            "font":  {"size": 16, "face": "arial"},
            "color": {"border": border, "background": bg},
            "widthConstraint": {"minimum": 120, "maximum": 200},
        })

    # Build vis.js edges — solid arrows for ancestry
    vis_edges = []
    seen_edges = set()
    for path in [path1, path2]:
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            if (src, dst) not in seen_edges:
                seen_edges.add((src, dst))
                vis_edges.append({
                    "from":   src,
                    "to":     dst,
                    "arrows": "to",
                    "color":  {"color": "#555555"},
                    "width":  2,
                    "dashes": False,
                })

    # Dashed gray lines for married-in spouses
    for spouse_node, anchor_node in spouse_pairs:
        vis_edges.append({
            "from":   anchor_node,
            "to":     spouse_node,
            "arrows": "",
            "color":  {"color": "#999999"},
            "width":  2,
            "dashes": [8, 4],
        })

    nodes_json = json.dumps(vis_nodes)
    edges_json = json.dumps(vis_edges)

    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css">
  <style>
    body {{ margin: 0; padding: 0; }}
    #network {{ width: 100%; height: 650px; border: 1px solid #ddd; background: #fff; }}
  </style>
</head>
<body>
  <div id="network"></div>
  <script>
    var nodes = new vis.DataSet({nodes_json});
    var edges = new vis.DataSet({edges_json});
    var container = document.getElementById("network");
    var options = {{
      physics: {{ enabled: false }},
      nodes: {{ margin: 10 }},
      edges: {{ smooth: {{ enabled: false }} }},
      interaction: {{ dragNodes: true, zoomView: true, dragView: true }}
    }};
    var network = new vis.Network(container, {{ nodes: nodes, edges: edges }}, options);
    network.fit();
  </script>
</body>
</html>
"""
    components.html(html, height=670)


# ----------------------------
# Streamlit UI
# ----------------------------
st.title("Genealogy Explorer")
st.subheader("Select two people to find their relationship")

for key in ["id1", "id2"]:
    if key not in st.session_state:
        st.session_state[key] = None

# Person 1
name1_input = st.text_input("Person 1")
if name1_input:
    matches1 = find_person(name1_input)
    if matches1:
        options1 = [f"{names[p]} ({birth_years[p]})" if birth_years[p] else names[p]
                    for p in matches1]
        sel1 = st.selectbox("Select Person 1", options1)
        st.session_state.id1 = matches1[options1.index(sel1)]
    else:
        st.warning("No match found for Person 1.")
        st.session_state.id1 = None

# Person 2
name2_input = st.text_input("Person 2")
if name2_input:
    matches2 = find_person(name2_input)
    if matches2:
        options2 = [f"{names[p]} ({birth_years[p]})" if birth_years[p] else names[p]
                    for p in matches2]
        sel2 = st.selectbox("Select Person 2", options2)
        st.session_state.id2 = matches2[options2.index(sel2)]
    else:
        st.warning("No match found for Person 2.")
        st.session_state.id2 = None

# Find relationship
if st.session_state.id1 and st.session_state.id2 and st.button("Find relationship"):
    id1 = st.session_state.id1
    id2 = st.session_state.id2

    try:
        path = nx.shortest_path(G_full.to_undirected(), id1, id2)
    except nx.NetworkXNoPath:
        st.error("No relationship found")
    else:
        st.subheader("Relationship Path")
        for i in range(len(path) - 1):
            p1, p2 = path[i], path[i + 1]
            if G_full.has_edge(p1, p2):
                rel = G_full[p1][p2]["relation"]
            elif G_full.has_edge(p2, p1):
                rel = G_full[p2][p1]["relation"]
            else:
                rel = "related"
            kinship = compute_vietnamese_kinship(id1, p2, G_anc, G_full, genders, birth_years, debug=True)
            st.write(f"{names.get(p1, p1)} ({rel}) → {names.get(p2, p2)} ({kinship})")

        ca = common_ancestor(id1, id2, G_full, G_anc)
        if ca:
            ca_name  = names.get(ca, ca)
            ca_label = f"{ca_name} ({birth_years[ca]})" if birth_years.get(ca) else ca_name
            st.subheader("Closest Common Ancestor")
            st.write(ca_label)
            draw_family_graph(id1, id2, ca)
        else:
            st.info("No common ancestor found — cannot draw graph.")
