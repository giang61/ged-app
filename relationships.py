# relationships.py
#
# Vietnamese kinship term computation.
# Pure kinship logic — no UI, no graph structure concerns.
# Graph traversal helpers are imported from graph_utils.py.

import networkx as nx
from graph_utils import is_blood_related, find_spouse


# -------------------------
# Ancestor terms
# -------------------------
def ancestor_term(gen_diff, gender):
    male   = {1: "Bố", 2: "Ông", 3: "Cụ ông", 4: "Kỵ ông", 5: "Tổ ông"}
    female = {1: "Mẹ", 2: "Bà",  3: "Cụ bà",  4: "Kỵ bà",  5: "Tổ bà"}
    return male.get(gen_diff, "Ông") if gender == "M" else female.get(gen_diff, "Bà")


# -------------------------
# Descendant terms
# -------------------------
def descendant_term(gen_diff, gender):
    male   = {1: "Con trai", 2: "Cháu trai", 3: "Chắt trai", 4: "Chút trai"}
    female = {1: "Con gái",  2: "Cháu gái",  3: "Chắt gái",  4: "Chút gái"}
    return male.get(gen_diff, "Hậu duệ") if gender == "M" else female.get(gen_diff, "Hậu duệ")


# -------------------------
# Same generation fallback
# -------------------------
def same_generation_term(ego, target, genders, births):
    ego_birth    = births.get(ego)
    target_birth = births.get(target)
    gender       = genders.get(target)

    if ego_birth is not None and target_birth is not None:
        if target_birth < ego_birth:
            return "Anh" if gender == "M" else "Chị"
        elif target_birth > ego_birth:
            return "Em trai" if gender == "M" else "Em"

    return "Anh/Chị/Em"


# -------------------------
# In-law term conversion
# -------------------------
def convert_to_inlaw(term, gender):
    mapping = {"Chú": "Thím", "Cậu": "Mợ", "Dì": "Dượng"}
    return mapping.get(term, term)


# -------------------------
# Same generation cousins
# -------------------------
def same_generation_cousin_term(G_anc, ego, target, genders, births):
    try:
        ancestor = nx.lowest_common_ancestor(G_anc, ego, target)
    except Exception:
        ancestor = None

    if not ancestor:
        return same_generation_term(ego, target, genders, births)

    ego_parents    = list(G_anc.predecessors(ego))
    target_parents = list(G_anc.predecessors(target))

    if not ego_parents or not target_parents:
        return same_generation_term(ego, target, genders, births)

    ego_parent_birth    = births.get(ego_parents[0])
    target_parent_birth = births.get(target_parents[0])
    gender              = genders.get(target)

    if ego_parent_birth is not None and target_parent_birth is not None:
        if target_parent_birth < ego_parent_birth:
            return "Anh" if gender == "M" else "Chị"
        elif target_parent_birth > ego_parent_birth:
            return "Em trai" if gender == "M" else "Em"

    return same_generation_term(ego, target, genders, births)


# -------------------------
# Parent generation
# -------------------------
def parent_generation_term(G_anc, ego, target, genders, births):
    ego_parents = list(G_anc.predecessors(ego))
    if not ego_parents:
        return None

    gender = genders.get(target)
    mother = next((p for p in ego_parents if genders.get(p) == "F"), None)
    father = next((p for p in ego_parents if genders.get(p) == "M"), None)

    target_parents = set(G_anc.predecessors(target))

    for parent in ego_parents:
        parent_parents = set(G_anc.predecessors(parent))
        if parent_parents & target_parents:
            parent_birth = births.get(parent)
            target_birth = births.get(target)
            if parent_birth is not None and target_birth is not None:
                if target_birth < parent_birth:
                    return "Bác"
            if parent == mother:
                return "Dì" if gender == "F" else "Cậu"
            else:
                return "Cô" if gender == "F" else "Chú"

    parent = ego_parents[0]
    relation_to_parent = same_generation_cousin_term(G_anc, parent, target, genders, births)

    if relation_to_parent in ["Anh", "Chị"]:
        return "Bác"
    if relation_to_parent in ["Em", "Em trai"]:
        if parent == mother:
            return "Dì" if gender == "F" else "Cậu"
        else:
            return "Cô" if gender == "F" else "Chú"

    parent_birth = births.get(parent)
    target_birth = births.get(target)
    if parent_birth is not None and target_birth is not None:
        if target_birth < parent_birth:
            return "Bác"

    if parent == mother:
        return "Dì" if gender == "F" else "Cậu"
    else:
        return "Cô" if gender == "F" else "Chú"


# -------------------------
# Children of cousins/siblings
# -------------------------
def child_of_cousin_term(ego, target, genders):
    gender = genders.get(target)
    return "Cháu trai" if gender == "M" else "Cháu gái"


# -------------------------
# Main function
# -------------------------
def compute_vietnamese_kinship(ego, target, G_anc, G_full, genders, births,
                               debug=False, skip_spouse=False):

    def dbg(msg):
        if debug:
            print(msg)

    if ego == target:
        return "Tôi"

    # -------------------------
    # SPOUSE DETECTION
    # -------------------------
    if not skip_spouse:
        if not is_blood_related(ego, target, G_anc):
            spouse = find_spouse(target, G_full)
            if spouse and spouse != ego:
                if is_blood_related(ego, spouse, G_anc):
                    dbg(f"[CASE] spouse via edge: {spouse}")
                    base_relation = compute_vietnamese_kinship(
                        ego, spouse, G_anc, G_full, genders, births,
                        debug=False, skip_spouse=True
                    )
                    dbg(f"[INFO] base_relation={base_relation}")
                    mapping = {
                        "Chú":  "Thím",
                        "Cậu":  "Mợ",
                        "Dì":   "Dượng",
                        "Anh":  "Chị dâu",
                        "Em":   "Em dâu",
                        "Chị":  "Anh rể",
                    }
                    return mapping.get(base_relation, base_relation)

    dbg(f"\n=== COMPUTE RELATION ===")
    dbg(f"ego={ego}, target={target}")

    gender      = genders.get(target)
    ego_parents = set(G_anc.predecessors(ego))
    tar_parents = set(G_anc.predecessors(target))

    dbg(f"ego_parents={list(ego_parents)}")
    dbg(f"tar_parents={list(tar_parents)}")

    # Sibling detection
    if ego_parents and (ego_parents & tar_parents):
        dbg("[CASE] sibling")
        ego_birth    = births.get(ego)
        target_birth = births.get(target)
        if ego_birth is not None and target_birth is not None:
            if target_birth < ego_birth:
                return "Anh" if gender == "M" else "Chị"
            elif target_birth > ego_birth:
                return "Em"
        return "Anh/Chị/Em"

    try:
        ancestor = nx.lowest_common_ancestor(G_anc, ego, target)
    except Exception:
        ancestor = None

    dbg(f"ancestor={ancestor}")

    if not ancestor:
        dbg("[CASE] no ancestor fallback")
        return same_generation_term(ego, target, genders, births)

    ego_depth = nx.shortest_path_length(G_anc, ancestor, ego)
    tar_depth = nx.shortest_path_length(G_anc, ancestor, target)
    gen_diff  = tar_depth - ego_depth

    dbg(f"ego_depth={ego_depth}, tar_depth={tar_depth}, gen_diff={gen_diff}")

    ego_parents = list(G_anc.predecessors(ego))
    tar_parents = list(G_anc.predecessors(target))

    # Direct parent / child
    if target in ego_parents:
        dbg("[CASE] parent")
        return "Bố" if gender == "M" else "Mẹ"

    if ego in tar_parents:
        dbg("[CASE] child")
        return "Con trai" if gender == "M" else "Con gái"

    # -------------------------
    # Children of cousins / siblings  (gen_diff == 1)
    # -------------------------
    if tar_parents and gen_diff == 1:
        dbg("[CASE] child of cousin/sibling")

        ego_parents_set = set(G_anc.predecessors(ego))
        ego_birth       = births.get(ego)
        ego_gender      = genders.get(ego)
        base            = child_of_cousin_term(ego, target, genders)

        dbg(f"base={base}, tar_parents={tar_parents}")

        # Find the correct parent among tar_parents — prefer blood-related parent
        true_parent = None

        # First pass: find a parent who is blood-related to ego
        for tp in tar_parents:
            if is_blood_related(ego, tp, G_anc):
                true_parent = tp
                break

        # Second pass: fall back to shared-grandparent check
        if true_parent is None:
            for tp in tar_parents:
                tp_parents = set(G_anc.predecessors(tp))
                if ego_parents_set and tp_parents and (ego_parents_set & tp_parents):
                    true_parent = tp
                    break

        # Last resort
        if true_parent is None:
            true_parent = tar_parents[0]

        tp_birth  = births.get(true_parent)
        tp_gender = genders.get(true_parent)

        dbg(f"true_parent={true_parent}, ego_birth={ego_birth}, tp_birth={tp_birth}")

        tp_parents_set = set(G_anc.predecessors(true_parent))
        is_sibling     = bool(ego_parents_set and tp_parents_set
                              and (ego_parents_set & tp_parents_set))

        dbg(f"is_sibling={is_sibling}")

        if is_sibling:
            dbg("[SUBCASE] sibling child")
            if tp_birth is not None and ego_birth is not None:
                if ego_birth < tp_birth:
                    address = "Bác"
                else:
                    address = ("Dì" if ego_gender == "F" else "Cậu") if tp_gender == "F" \
                              else ("Cô" if ego_gender == "F" else "Chú")
            else:
                address = "Bác"
        else:
            dbg("[SUBCASE] cousin child")
            relation = same_generation_cousin_term(G_anc, ego, true_parent, genders, births)
            dbg(f"relation_to_parent={relation}")
            if tp_birth is not None and ego_birth is not None:
                if ego_birth < tp_birth:
                    address = "Bác"
                else:
                    address = ("Dì" if ego_gender == "F" else "Cậu") if tp_gender == "F" \
                              else ("Cô" if ego_gender == "F" else "Chú")
            else:
                if relation and ("Anh" in relation or "Chị" in relation):
                    address = "Cô" if ego_gender == "F" else "Chú"
                else:
                    address = "Dì" if ego_gender == "F" else "Cậu"

        final_address = address
        if not is_blood_related(ego, true_parent, G_anc):
            final_address = convert_to_inlaw(address, tp_gender)

        dbg(f"[FINAL] {base} (gọi bằng {final_address})")
        return f"{base} (gọi bằng {final_address})"

    # Ancestors
    if gen_diff <= -2:
        dbg("[CASE] ancestor")
        return ancestor_term(abs(gen_diff), gender)

    # Descendants
    if gen_diff >= 2:
        dbg("[CASE] descendant")
        return descendant_term(gen_diff, gender)

    # Parent generation
    if gen_diff == -1:
        dbg("[CASE] parent generation")
        return parent_generation_term(G_anc, ego, target, genders, births)

    # Same generation
    if gen_diff == 0:
        dbg("[CASE] same generation cousin")
        return same_generation_cousin_term(G_anc, ego, target, genders, births)

    dbg("[CASE] fallback same generation")
    return same_generation_term(ego, target, genders, births)
