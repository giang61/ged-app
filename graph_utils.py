# graph_utils.py
#
# Graph traversal utilities shared by relationships.py and main.py.
# No UI code, no kinship term logic — pure graph operations on
# the structures produced by ged_parser.py.

import networkx as nx


# -------------------------
# Blood relationship check
# -------------------------
def is_blood_related(ego, person, G_anc):
    """Return True if ego and person share any common ancestor."""
    if not G_anc.has_node(ego) or not G_anc.has_node(person):
        return False
    if nx.has_path(G_anc, person, ego) or nx.has_path(G_anc, ego, person):
        return True
    ego_ancestors = nx.ancestors(G_anc, ego) | {ego}
    person_ancestors = nx.ancestors(G_anc, person) | {person}
    return bool(ego_ancestors & person_ancestors)


# -------------------------
# Spouse lookup
# -------------------------
def find_spouse(target, G_full):
    """Return the spouse of target in G_full, or None.
    Checks both edge directions since GEDCOM spouse edges may go either way."""
    for nb in G_full.successors(target):
        if G_full.edges[target, nb].get("relation") == "spouse":
            return nb
    for nb in G_full.predecessors(target):
        if G_full.edges[nb, target].get("relation") == "spouse":
            return nb
    return None


def find_blood_spouse(pid, G_full, G_anc):
    """Return the spouse of pid who exists in G_anc, or None.
    Checks both edge directions since GEDCOM spouse edges may go either way."""
    for nb in G_full.successors(pid):
        if G_full.edges[pid, nb].get("relation") == "spouse" and G_anc.has_node(nb):
            return nb
    for nb in G_full.predecessors(pid):
        if G_full.edges[nb, pid].get("relation") == "spouse" and G_anc.has_node(nb):
            return nb
    return None


# -------------------------
# Blood anchor resolution
# -------------------------
def blood_anchor(pid, G_full, G_anc, reference_pid=None):
    """
    If pid is a married-in spouse whose ancestors are not in the main family
    tree, return their blood spouse instead.

    reference_pid: a known member of the main family tree, used to identify
    which subtree of G_anc is the 'main' one. Falls back to all G_anc nodes
    if not provided.
    """
    pid_ancestors = nx.ancestors(G_anc, pid) if G_anc.has_node(pid) else set()

    if not G_anc.has_node(pid):
        spouse = find_blood_spouse(pid, G_full, G_anc)
        return spouse if spouse else pid

    if not pid_ancestors:
        spouse = find_blood_spouse(pid, G_full, G_anc)
        return spouse if spouse else pid

    if reference_pid is not None and G_anc.has_node(reference_pid):
        ref_ancestors = nx.ancestors(G_anc, reference_pid) | {reference_pid}
        ref_descendants = nx.descendants(G_anc, reference_pid) | {reference_pid}
        main_tree_nodes = ref_ancestors | ref_descendants
    else:
        main_tree_nodes = set(G_anc.nodes())

    if pid_ancestors & main_tree_nodes:
        return pid

    for nb in G_full.predecessors(pid):
        if G_full.edges[nb, pid].get("relation") == "spouse" and G_anc.has_node(nb):
            if nx.ancestors(G_anc, nb) & main_tree_nodes:
                return nb
    for nb in G_full.successors(pid):
        if G_full.edges[pid, nb].get("relation") == "spouse" and G_anc.has_node(nb):
            if nx.ancestors(G_anc, nb) & main_tree_nodes:
                return nb

    return pid


# -------------------------
# Ancestor set expansion
# -------------------------
def expand_with_spouses(ancestor_set, G_full):
    """For each ancestor, also include their spouse so that father-only and
    mother-only paths can still find a common couple."""
    expanded = set(ancestor_set)
    for pid in ancestor_set:
        for nb in G_full.successors(pid):
            if G_full.edges[pid, nb].get("relation") == "spouse":
                expanded.add(nb)
        for nb in G_full.predecessors(pid):
            if G_full.edges[nb, pid].get("relation") == "spouse":
                expanded.add(nb)
    return expanded


# -------------------------
# Common ancestor
# -------------------------
def common_ancestor(id1, id2, G_full, G_anc):
    """Return the closest common ancestor of id1 and id2."""
    a1 = blood_anchor(id1, G_full, G_anc, reference_pid=id1)
    a2 = blood_anchor(id2, G_full, G_anc, reference_pid=id1)

    anc1 = nx.ancestors(G_anc, a1) | {a1} if G_anc.has_node(a1) else {a1}
    anc2 = nx.ancestors(G_anc, a2) | {a2} if G_anc.has_node(a2) else {a2}
    anc1 = expand_with_spouses(anc1, G_full)
    anc2 = expand_with_spouses(anc2, G_full)

    common = anc1 & anc2
    if not common:
        return None

    def dist(a):
        try:
            d1 = nx.shortest_path_length(G_anc, a, a1)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            d1 = float("inf")
        try:
            d2 = nx.shortest_path_length(G_anc, a, a2)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            d2 = float("inf")
        if d1 == float("inf"):
            spouse = find_blood_spouse(a, G_full, G_anc)
            if spouse:
                try:
                    d1 = nx.shortest_path_length(G_anc, spouse, a1)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
        if d2 == float("inf"):
            spouse = find_blood_spouse(a, G_full, G_anc)
            if spouse:
                try:
                    d2 = nx.shortest_path_length(G_anc, spouse, a2)
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    pass
        return d1 + d2

    return min(common, key=dist)
