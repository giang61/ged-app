import streamlit as st
import unicodedata
import networkx as nx
from ged4py.parser import GedcomReader
import re
from pyvis.network import Network
import streamlit.components.v1 as components

GED_FILE = "data/nguyen.ged"  # relative path to your GEDCOM file

# -------- normalize Vietnamese names --------
def normalize(text):
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d")
    return text

# -------- load GEDCOM --------
@st.cache_resource
def load_tree():
    G_full = nx.DiGraph()  # full graph for shortest path display
    G_anc = nx.DiGraph()   # parent->child graph for correct common ancestor
    names = {}
    search_names = {}
    birth_years = {}

    def get_birth_year(indi):
        for sub in indi.sub_records:
            if sub.tag == "BIRT":
                for s in sub.sub_records:
                    if s.tag == "DATE" and s.value is not None:
                        date_str = str(s.value)
                        match = re.search(r"\b(\d{4})\b", date_str)
                        if match:
                            return match.group(1)
        return ""

    with GedcomReader(GED_FILE) as parser:
        for indi in parser.records0("INDI"):
            pid = indi.xref_id
            name = indi.name.format() if indi.name else pid
            names[pid] = name
            search_names[pid] = normalize(name)
            birth_years[pid] = get_birth_year(indi)
            G_full.add_node(pid)
            G_anc.add_node(pid)

        for fam in parser.records0("FAM"):
            parents = []
            children = []
            for sub in fam.sub_records:
                if sub.tag in ["HUSB", "WIFE"]:
                    parents.append(sub.value)
                if sub.tag == "CHIL":
                    children.append(sub.value)

            # parent-child edges
            for p in parents:
                for c in children:
                    G_full.add_edge(p, c, relation="parent")
                    G_full.add_edge(c, p, relation="child")
                    G_anc.add_edge(p, c, relation="parent")

            # spouse edges
            if len(parents) == 2:
                G_full.add_edge(parents[0], parents[1], relation="spouse")
                G_full.add_edge(parents[1], parents[0], relation="spouse")

    return G_full, G_anc, names, search_names, birth_years

G_full, G_anc, names, search_names, birth_years = load_tree()

# -------- improved person search --------
def find_person(query):
    q_words = normalize(query).split()
    matches = []
    for pid, name in search_names.items():
        n_words = normalize(name).split()
        if all(word in n_words for word in q_words):
            matches.append(pid)
    matches.sort(key=lambda pid: normalize(names[pid]).find(normalize(query)))
    return matches

# -------- closest common ancestor --------
def common_ancestor(id1, id2):
    anc1 = nx.ancestors(G_anc, id1) | {id1}
    anc2 = nx.ancestors(G_anc, id2) | {id2}
    common = anc1 & anc2
    if not common:
        return None
    best = min(common, key=lambda a: nx.shortest_path_length(G_anc, a, id1) + nx.shortest_path_length(G_anc, a, id2))
    return best

# -------- PyVis interactive graph with colors --------
def draw_family_path(path, id1, id2):
    net = Network(height="600px", width="100%", directed=True)

    # find siblings along the path
    siblings = set()
    for node in path:
        for neighbor in G_full.neighbors(node):
            if G_full[node][neighbor]['relation'] == 'child' and neighbor != node:
                siblings.add(neighbor)

    # add nodes with colors
    for pid in path:
        label = f"{names[pid]} ({birth_years[pid]})" if birth_years.get(pid) else names[pid]
        if pid == id1 or pid == id2:
            color = "red"
        elif pid in siblings:
            color = "orange"
        else:
            color = "lightblue"
        net.add_node(pid, label=label, title=label, color=color)

    # add edges
    for i in range(len(path)-1):
        net.add_edge(path[i], path[i+1], arrows="to")

    # **Write HTML and embed in Streamlit**
    html_file = "family_path.html"
    net.write_html(html_file)  # <-- no net.show()
    with open(html_file, "r", encoding="utf-8") as f:
        components.html(f.read(), height=650)
# -------- Streamlit UI --------
st.title("Genealogy Relationship Finder")
st.write("Search your GEDCOM family tree (Vietnamese names supported)")

# Inputs
name1_input = st.text_input("Person 1")
name2_input = st.text_input("Person 2")

id1, id2 = None, None

if name1_input:
    matches1 = find_person(name1_input)
    if matches1:
        options1 = [
            f"{names[pid]} ({birth_years[pid]})" if birth_years[pid] else names[pid]
            for pid in matches1
        ]
        sel1 = st.selectbox("Select Person 1", options1)
        id1 = matches1[options1.index(sel1)]
    else:
        st.warning("Person 1 not found")

if name2_input:
    matches2 = find_person(name2_input)
    if matches2:
        options2 = [
            f"{names[pid]} ({birth_years[pid]})" if birth_years[pid] else names[pid]
            for pid in matches2
        ]
        sel2 = st.selectbox("Select Person 2", options2)
        id2 = matches2[options2.index(sel2)]
    else:
        st.warning("Person 2 not found")

# Compute relationship
if st.button("Find relationship") and id1 and id2:
    try:
        path = nx.shortest_path(G_full, id1, id2)
    except nx.NetworkXNoPath:
        st.error("No relationship path found")
    else:
        st.subheader("Relationship Path")
        for i in range(len(path)-1):
            p1, p2 = path[i], path[i+1]
            rel = G_full[p1][p2]["relation"]
            if rel == "parent":
                text = f"{names[p1]} is parent of {names[p2]}"
            elif rel == "child":
                text = f"{names[p1]} is child of {names[p2]}"
            elif rel == "spouse":
                text = f"{names[p1]} is spouse of {names[p2]}"
            else:
                text = f"{names[p1]} related to {names[p2]}"
            st.write(text)

        # closest common ancestor
        ca = common_ancestor(id1, id2)
        if ca:
            st.subheader("Closest Common Ancestor")
            st.write(f"{names[ca]} ({birth_years[ca]})" if birth_years[ca] else names[ca])
            if nx.has_path(G_anc, ca, id1) and nx.has_path(G_anc, ca, id2):
                path_len1 = nx.shortest_path_length(G_anc, ca, id1)
                path_len2 = nx.shortest_path_length(G_anc, ca, id2)
                if path_len1 == 1 and path_len2 == 1:
                    st.info(f"{names[id1]} and {names[id2]} are siblings")

        # draw interactive graph
        draw_family_path(path, id1, id2)