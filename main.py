# main.py
from graphviz import Digraph
import streamlit as st
from pyvis.network import Network
import streamlit.components.v1 as components
import networkx as nx
from html import escape
from ged_parser import load_gedcom
from relationships import compute_vietnamese_kinship

# ----------------------------
# Load GEDCOM
# ----------------------------
G_full, G_anc, names, genders, birth_years = load_gedcom("data/nguyen.ged")

# ----------------------------
# Normalize names for search
# ----------------------------
import unicodedata
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
# Common ancestor function
# ----------------------------
def common_ancestor(id1, id2):
    anc1 = nx.ancestors(G_anc, id1) | {id1}
    anc2 = nx.ancestors(G_anc, id2) | {id2}
    common = anc1 & anc2
    if not common:
        return None
    def dist(a):
        try:
            return nx.shortest_path_length(G_anc, a, id1) + \
                   nx.shortest_path_length(G_anc, a, id2)
        except nx.NetworkXNoPath:
            return float("inf")
    return min(common, key=dist)

# ----------------------------
# Draw family graph (intact)
# ----------------------------
from graphviz import Digraph

from pyvis.network import Network
from html import escape
import networkx as nx

def draw_family_graph(id1, id2, ca):
    """
    Draw family graph using PyVis with three-argument signature:
    id1, id2 = two people of interest
    ca = common ancestor
    """
    ego_id = id1  # reference person for kinship terms

    net = Network(height="700px", width="100%", directed=True)

    # Disable physics and hierarchical layout for fixed positions
    net.set_options("""
    {
      "layout": {"hierarchical": {"enabled": false}},
      "nodes": {"font": {"size": 36, "face": "arial"}},
      "physics": {"enabled": false}
    }
    """)

    # Paths from common ancestor
    path1 = nx.shortest_path(G_anc, ca, id1)
    path2 = nx.shortest_path(G_anc, ca, id2)

    all_nodes = list(dict.fromkeys(path1 + path2))
    id_map = {pid: f"n{i}" for i, pid in enumerate(all_nodes)}

    # Vertical levels (generation)
    levels = {}
    for i, pid in enumerate(path1):
        levels[pid] = i
    for i, pid in enumerate(path2):
        levels[pid] = i
    levels[ca] = 0  # common ancestor at top

    # Vertical spacing
    y_spacing = 150
    y_positions = {pid: (levels[pid] + 1) * y_spacing for pid in all_nodes if pid != ca}
    y_positions[ca] = 0

    # Horizontal spacing
    x_spacing = 300
    center_x = 0
    x_positions = {}
    x_positions[ca] = center_x

    for pid in path1[1:]:
        x_positions[pid] = center_x - x_spacing
    for pid in path2[1:]:
        x_positions[pid] = center_x + x_spacing

    # Auto-center horizontally
    min_x = min(x_positions.values())
    max_x = max(x_positions.values())
    offset = (min_x + max_x) / 2
    for pid in x_positions:
        x_positions[pid] -= offset

    for pid in all_nodes:
        name = names.get(pid, "Unknown")
        year = birth_years.get(pid)
        kin_term = compute_vietnamese_kinship(ego_id, pid, G_anc, genders, birth_years)

        label_lines = [str(name)]
        if year:
            label_lines.append(f"({year})")
        if kin_term:
            label_lines.append(str(kin_term))

        # Join lines using \n for PyVis
        label_text = "\n".join(label_lines)

        # Node color
        if pid == ca:
            color = {"border": "red", "background": "#ffcccc"}  # CA
        elif pid in [id1, id2]:
            color = {"border": "blue", "background": "#cce5ff"}  # targets
        else:
            color = {"border": "orange", "background": "#ffe5b4"}  # others

        net.add_node(
            id_map[pid],
            label=label_text,
            title=label_text,
            shape="box",
            x=x_positions[pid],
            y=y_positions[pid],
            fixed=True,
            color=color,
            font={"size": 36}
        )

    # Add edges along both paths
    for path in [path1, path2]:
        for i in range(len(path) - 1):
            src = path[i]
            dst = path[i + 1]
            if src in id_map and dst in id_map:
                net.add_edge(id_map[src], id_map[dst], arrows="to")

    # Render HTML in Streamlit
    html_file = "family_tree.html"
    net.write_html(html_file)
    with open(html_file, "r", encoding="utf-8") as f:
        import streamlit.components.v1 as components
        components.html(f.read(), height=700)
# ----------------------------
# Streamlit UI
# ----------------------------
st.title("Genealogy Explorer")
st.subheader("Select two people to find their relationship")

# ----------------------------
# Initialize IDs
# ----------------------------
id1 = None
id2 = None

# ----------------------------
# Person 1
# ----------------------------
name1_input = st.text_input("Person 1")
if name1_input:
    matches = find_person(name1_input)
    if matches:
        options = [f"{names[p]} ({birth_years[p]})" if birth_years[p] else names[p] for p in matches]
        sel = st.selectbox("Select Person 1", options)
        id1 = matches[options.index(sel)]

# ----------------------------
# Person 2
# ----------------------------
name2_input = st.text_input("Person 2")
if name2_input:
    matches = find_person(name2_input)
    if matches:
        options = [f"{names[p]} ({birth_years[p]})" if birth_years[p] else names[p] for p in matches]
        sel = st.selectbox("Select Person 2", options)
        id2 = matches[options.index(sel)]

# ----------------------------
# Find relationship button
# ----------------------------
if id1 and id2 and st.button("Find relationship"):
    try:
        path = nx.shortest_path(G_full.to_undirected(), id1, id2)
    except nx.NetworkXNoPath:
        st.error("No relationship found")
    else:
        st.subheader("Relationship Path")
        for i in range(len(path)-1):
            p1, p2 = path[i], path[i+1]
            if G_full.has_edge(p1, p2):
                rel = G_full[p1][p2]["relation"]
            elif G_full.has_edge(p2, p1):
                rel = G_full[p2][p1]["relation"]
            else:
                rel = "related"
            kinship = compute_vietnamese_kinship(id1, p2, G_anc, genders, birth_years)
            st.write(f"{names.get(p1, p1)} ({rel}) → {names.get(p2, p2)} ({kinship})")

        # ----------------------------
        # Common ancestor
        # ----------------------------
        ca = common_ancestor(id1, id2)

        if ca:
            ca_name = names.get(ca, ca)

            if birth_years.get(ca):
                ca_label = f"{ca_name} ({birth_years[ca]})"
            else:
                ca_label = ca_name

            st.subheader("Closest Common Ancestor")
            st.write(ca_label)

            draw_family_graph(id1, id2, ca)