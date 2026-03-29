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
from graph_utils import blood_anchor, common_ancestor, expand_with_spouses, find_blood_spouse, find_spouse, is_blood_related
from relationships import compute_vietnamese_kinship


# ----------------------------
# Load GEDCOM
# ----------------------------
@st.cache_resource
def get_gedcom_data():
    return load_gedcom("data/nguyen.ged")

G_full, G_anc, names, genders, birth_years, sib_order = get_gedcom_data()


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
def draw_family_graph(id1, id2, ca, ego_id=None, spouse_overlay=None):
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
    # If a spouse_overlay was passed, connect them by dashed line to their blood spouse
    if spouse_overlay and spouse_overlay not in [s for s, _ in spouse_pairs]:
        overlay_anchor = find_blood_spouse(spouse_overlay, G_full, G_anc)
        if overlay_anchor is None:
            overlay_anchor = id1
        spouse_pairs.append((spouse_overlay, overlay_anchor))

    def find_all_blood_spouses(pid):
        """Return all spouses of pid who exist in G_anc."""
        spouses = []
        for nb in G_full.successors(pid):
            if G_full.edges[pid, nb].get("relation") == "spouse" and G_anc.has_node(nb):
                spouses.append(nb)
        for nb in G_full.predecessors(pid):
            if G_full.edges[nb, pid].get("relation") == "spouse" and G_anc.has_node(nb):
                spouses.append(nb)
        return spouses

    def path_from_ca(ca, target):
        try:
            return nx.shortest_path(G_anc, ca, target)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            # Try all blood spouses of ca — pick the one with a path to target
            for ca_spouse in find_all_blood_spouses(ca):
                try:
                    p = nx.shortest_path(G_anc, ca_spouse, target)
                    # ca → ca_spouse is a spouse link, register as dashed line
                    if (ca_spouse, ca) not in [(s, a) for s, a in spouse_pairs] and \
                       (ca, ca_spouse) not in [(a, s) for s, a in spouse_pairs]:
                        spouse_pairs.append((ca_spouse, ca))
                    return [ca] + p
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
            return [ca]

    path1 = path_from_ca(ca, draw_id1)
    path2 = path_from_ca(ca, draw_id2)

    all_nodes = list(dict.fromkeys(path1 + path2))
    # Always include all spouse overlay nodes
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
        levels[spouse_node] = levels.get(anchor_node, len(path1) - 1)

    # x/y positions
    x_spacing = 220
    y_spacing = 140
    x_positions = {ca: 0}
    for pid in path1[1:]:
        x_positions[pid] = -x_spacing
    for pid in path2[1:]:
        x_positions[pid] = x_spacing
    # Place each married-in/overlay spouse to the left of their blood anchor
    for spouse_node, anchor_node in spouse_pairs:
        anchor_x = x_positions.get(anchor_node, -x_spacing)
        x_positions[spouse_node] = anchor_x - x_spacing
    for pid in all_nodes:
        if pid not in x_positions:
            x_positions[pid] = 0

    y_positions = {pid: levels.get(pid, 0) * y_spacing for pid in all_nodes}

    # highlight_ids: id1 passed in (blood anchor) + spouse_overlay if present
    highlight_ids = {id1, id2}
    if spouse_overlay:
        highlight_ids.add(spouse_overlay)

    # Build vis.js nodes
    vis_nodes = []

    ego_gender    = genders.get(ego_id)

    def reverse_term(kin_term, pid):
        """Return the 'gọi bằng X' address that pid uses toward ego_id."""
        pid_gender = genders.get(pid)
        # Extract base term (before any existing parenthetical)
        base = kin_term.split("(")[0].strip()
        # ego_gender: how pid addresses ego
        # pid_gender: used for terms like Anh/Chị where target gender matters
        table = {
            # Direct blood relatives
            "Bố":        "Con trai"   if ego_gender == "M" else "Con gái",
            "Mẹ":        "Con trai"   if ego_gender == "M" else "Con gái",
            "Ông":       "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Bà":        "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Cụ ông":    "Chắt trai"  if ego_gender == "M" else "Chắt gái",
            "Cụ bà":     "Chắt trai"  if ego_gender == "M" else "Chắt gái",
            "Kỵ ông":    "Chút trai"  if ego_gender == "M" else "Chút gái",
            "Kỵ bà":     "Chút trai"  if ego_gender == "M" else "Chút gái",
            "Anh":       "Em trai"    if ego_gender == "M" else "Em gái",
            "Chị":       "Em trai"    if ego_gender == "M" else "Em gái",
            "Em":        "Anh"        if ego_gender == "M" else "Chị",
            "Em trai":   "Anh"        if ego_gender == "M" else "Chị",
            "Bác":       "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Chú":       "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Cô":        "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Cậu":       "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Dì":        "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Con trai":  "Bố"         if ego_gender == "M" else "Mẹ",
            "Con gái":   "Bố"         if ego_gender == "M" else "Mẹ",
            "Cháu trai": "Ông"        if ego_gender == "M" else "Bà",
            "Cháu gái":  "Ông"        if ego_gender == "M" else "Bà",
            "Chắt trai": "Cụ ông"     if ego_gender == "M" else "Cụ bà",
            "Chắt gái":  "Cụ ông"     if ego_gender == "M" else "Cụ bà",
            # In-law terms — pid calls ego by the reciprocal in-law address
            "Bố chồng":  "Con dâu",
            "Mẹ chồng":  "Con dâu",
            "Bố vợ":     "Con rể",
            "Mẹ vợ":     "Con rể",
            "Anh chồng": "Em trai"    if ego_gender == "M" else "Em gái",
            "Chị chồng": "Em trai"    if ego_gender == "M" else "Em gái",
            "Anh vợ":    "Em trai"    if ego_gender == "M" else "Em gái",
            "Chị vợ":    "Em trai"    if ego_gender == "M" else "Em gái",
            "Em chồng":  "Anh"        if pid_gender == "M" else "Chị",
            "Em vợ":     "Anh"        if pid_gender == "M" else "Chị",
            "Chị dâu":   "Em trai"    if ego_gender == "M" else "Em gái",
            "Anh rể":    "Em trai"    if ego_gender == "M" else "Em gái",
            "Em dâu":    "Anh"        if pid_gender == "M" else "Chị",
            "Em rể":     "Anh"        if pid_gender == "M" else "Chị",
            "Thím":      "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Mợ":        "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Dượng":     "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Chú chồng": "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Cô chồng":  "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Bác chồng": "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Cậu chồng": "Cháu trai"  if ego_gender == "M" else "Cháu gái",
            "Dì chồng":  "Cháu trai"  if ego_gender == "M" else "Cháu gái",
        }
        return table.get(base)

    # Build set of spouse-only overlay nodes (no blood relation to ego_id)
    spouse_only_nodes = {s for s, _ in spouse_pairs if not is_blood_related(ego_id, s, G_anc)}

    # Identify ego's direct spouse node for the special "Mình" label
    ego_direct_spouse = find_spouse(ego_id, G_full)

    def spouse_label(pid):
        """Return the kinship label for ego's direct spouse."""
        pid_gender = genders.get(pid)
        if ego_gender == pid_gender:
            return "Mình (gọi bằng Mình)"
        elif ego_gender == "F" and pid_gender == "M":
            return "Anh (gọi bằng Em / Mình)"
        elif ego_gender == "M" and pid_gender == "F":
            return "Em (gọi bằng Anh / Mình)"
        else:
            return "Mình (gọi bằng Mình)"

    for pid in all_nodes:
        name     = names.get(pid, "Unknown")
        year     = birth_years.get(pid)

        # Special label for ego's direct spouse
        if pid == ego_direct_spouse:
            kin_term = spouse_label(pid)
        else:
            kin_term = compute_vietnamese_kinship(ego_id, pid, G_anc, G_full, genders, birth_years, sib_order)

        # For pure married-in nodes, suppress only the ambiguous fallback term.
        if pid in spouse_only_nodes and pid != ego_direct_spouse and kin_term == "Anh/Chị/Em":
            kin_term = None

        label_parts = [escape(str(name))]
        if year:
            label_parts.append(f"({year})")
        if kin_term and kin_term != "Tôi":
            # If kin_term already contains "gọi bằng", keep it as-is.
            # Otherwise append the reverse address term.
            if "gọi bằng" in kin_term:
                label_parts.append(escape(str(kin_term)))
            else:
                rev = reverse_term(kin_term, pid)
                if rev:
                    label_parts.append(escape(f"{kin_term} (gọi bằng {rev})"))
                else:
                    label_parts.append(escape(str(kin_term)))
        elif kin_term == "Tôi":
            label_parts.append("Tôi")
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
    # Collect all spouse pair node sets for quick lookup
    spouse_edge_pairs = {frozenset([s, a]) for s, a in spouse_pairs}
    for path in [path1, path2]:
        for i in range(len(path) - 1):
            src, dst = path[i], path[i + 1]
            # Skip edges that are actually spouse links (drawn as dashed below)
            if frozenset([src, dst]) in spouse_edge_pairs:
                continue
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
        # First re-anchor id2 if it is a married-in spouse.
        try:
            _id2_lca = nx.lowest_common_ancestor(G_anc, id1, id2)
        except Exception:
            _id2_lca = None
        if _id2_lca is None:
            _anchor2 = find_blood_spouse(id2, G_full, G_anc)
            kinship_target = _anchor2 if _anchor2 else id2
        else:
            kinship_target = id2

        # Then re-anchor id1 if it is a married-in spouse,
        # checking against the already-resolved kinship_target.
        try:
            _id1_lca = nx.lowest_common_ancestor(G_anc, id1, kinship_target)
        except Exception:
            _id1_lca = None
        if _id1_lca is None:
            _anchor1 = find_blood_spouse(id1, G_full, G_anc)
            kinship_ego = _anchor1 if _anchor1 else id1
        else:
            kinship_ego = id1

        st.subheader("Relationship Path")
        for i in range(len(path) - 1):
            p1, p2 = path[i], path[i + 1]
            if G_full.has_edge(p1, p2):
                rel = G_full[p1][p2]["relation"]
            elif G_full.has_edge(p2, p1):
                rel = G_full[p2][p1]["relation"]
            else:
                rel = "related"
            kinship = compute_vietnamese_kinship(id1, p2, G_anc, G_full, genders, birth_years, sib_order, debug=True)
            st.write(f"{names.get(p1, p1)} ({rel}) → {names.get(p2, p2)} ({kinship})")

        ca = common_ancestor(kinship_ego, kinship_target, G_full, G_anc)
        if ca:
            ca_name  = names.get(ca, ca)
            ca_label = f"{ca_name} ({birth_years[ca]})" if birth_years.get(ca) else ca_name
            st.subheader("Closest Common Ancestor")
            st.write(ca_label)
            draw_id1     = kinship_ego    if kinship_ego    != id1 else id1
            draw_id2     = kinship_target if kinship_target != id2 else id2
            overlay_id1  = id1 if kinship_ego    != id1 else None
            overlay_id2  = id2 if kinship_target != id2 else None
            overlay = overlay_id1 or overlay_id2
            print(f"[DRAW] draw_id1={draw_id1} draw_id2={draw_id2} overlay={overlay} ca={ca}")
            if overlay:
                print(f"[DRAW] find_blood_spouse(overlay)={find_blood_spouse(overlay, G_full, G_anc)}")
            draw_family_graph(draw_id1, draw_id2, ca, ego_id=id1, spouse_overlay=overlay)
        else:
            st.info("No common ancestor found — cannot draw graph.")
