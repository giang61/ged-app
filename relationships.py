import networkx as nx

# -------------------------
# Ancestor terms
# -------------------------
def ancestor_term(gen_diff, gender):
    male = {1:"Bố",2:"Ông",3:"Cụ ông",4:"Kỵ ông",5:"Tổ ông"}
    female = {1:"Mẹ",2:"Bà",3:"Cụ bà",4:"Kỵ bà",5:"Tổ bà"}
    return male.get(gen_diff,"Ông") if gender=="M" else female.get(gen_diff,"Bà")

# -------------------------
# Descendant terms
# -------------------------
def descendant_term(gen_diff, gender):
    male = {1:"Con trai",2:"Cháu trai",3:"Chắt trai",4:"Chút trai"}
    female = {1:"Con gái",2:"Cháu gái",3:"Chắt gái",4:"Chút gái"}
    return male.get(gen_diff,"Hậu duệ") if gender=="M" else female.get(gen_diff,"Hậu duệ")

# -------------------------
# Same generation fallback
# -------------------------
def same_generation_term(ego, target, genders, births):
    ego_birth = births.get(ego)
    target_birth = births.get(target)
    gender = genders.get(target)

    if ego_birth is not None and target_birth is not None:
        if target_birth < ego_birth:
            return "Anh" if gender=="M" else "Chị"
        elif target_birth > ego_birth:
            return "Em trai" if gender=="M" else "Em"

    return "Anh/Chị/Em"

# -------------------------
# Parent generation
# -------------------------
def parent_generation_term(G, ego, target, genders, births):
    ego_parents = list(G.predecessors(ego))
    if not ego_parents:
        return None

    gender = genders.get(target)

    mother = next((p for p in ego_parents if genders.get(p) == "F"), None)
    father = next((p for p in ego_parents if genders.get(p) == "M"), None)

    target_parents = set(G.predecessors(target))

    # CASE 1: true sibling of parent
    for parent in ego_parents:
        parent_parents = set(G.predecessors(parent))
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

    # CASE 2: cousin of parent
    parent = ego_parents[0]
    relation_to_parent = same_generation_cousin_term(G, parent, target, genders, births)

    if relation_to_parent in ["Anh", "Chị"]:
        return "Bác"

    if relation_to_parent in ["Em", "Em trai"]:
        if parent == mother:
            return "Dì" if gender == "F" else "Cậu"
        else:
            return "Cô" if gender == "F" else "Chú"

    # fallback
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
# Children of cousins
# -------------------------
def child_of_cousin_term(G, ego, target, genders):
    gender = genders.get(target)
    return "Cháu trai" if gender=="M" else "Cháu gái"

# -------------------------
# Same generation cousins
# -------------------------
def same_generation_cousin_term(G, ego, target, genders, births):
    try:
        ancestor = nx.lowest_common_ancestor(G, ego, target)
    except:
        ancestor = None

    if not ancestor:
        return same_generation_term(ego, target, genders, births)

    ego_parents = list(G.predecessors(ego))
    target_parents = list(G.predecessors(target))

    if not ego_parents or not target_parents:
        return same_generation_term(ego, target, genders, births)

    ego_parent = ego_parents[0]
    target_parent = target_parents[0]

    gender = genders.get(target)

    ego_parent_birth = births.get(ego_parent)
    target_parent_birth = births.get(target_parent)

    if ego_parent_birth is not None and target_parent_birth is not None:
        if target_parent_birth < ego_parent_birth:
            return "Anh" if gender == "M" else "Chị"
        elif target_parent_birth > ego_parent_birth:
            return "Em trai" if gender == "M" else "Em"

    return same_generation_term(ego, target, genders, births)

# -------------------------
# Main function
# -------------------------
def compute_vietnamese_kinship(ego, target, G, genders, births):

    if ego == target:
        return "Tôi"

    gender = genders.get(target)

    # sibling detection
    ego_parents = set(G.predecessors(ego))
    target_parents = set(G.predecessors(target))

    if ego_parents and (ego_parents & target_parents):
        ego_birth = births.get(ego)
        target_birth = births.get(target)

        if ego_birth is not None and target_birth is not None:
            if target_birth < ego_birth:
                return "Anh" if gender == "M" else "Chị"
            elif target_birth > ego_birth:
                return "Em"

        return "Anh/Chị/Em"

    try:
        ancestor = nx.lowest_common_ancestor(G, ego, target)
    except:
        ancestor = None

    if not ancestor:
        return same_generation_term(ego, target, genders, births)

    ego_depth = nx.shortest_path_length(G, ancestor, ego)
    tar_depth = nx.shortest_path_length(G, ancestor, target)
    gen_diff = tar_depth - ego_depth

    ego_parents = list(G.predecessors(ego))
    tar_parents = list(G.predecessors(target))

    # direct parent/child
    if target in ego_parents:
        return "Bố" if gender == "M" else "Mẹ"

    if ego in tar_parents:
        return "Con trai" if gender == "M" else "Con gái"

    # -------------------------
    # Children of cousins (FIXED)
    # -------------------------
    if tar_parents and gen_diff == 1:
        for tp in tar_parents:
            relation = same_generation_cousin_term(G, ego, tp, genders, births)

            # ✅ robust detection
            if relation and any(x in relation for x in ["Anh", "Chị", "Em"]):

                base = child_of_cousin_term(G, ego, target, genders)

                tp_birth = births.get(tp)
                ego_birth = births.get(ego)
                ego_gender = genders.get(ego)

                address = None

                if tp_birth is not None and ego_birth is not None:

                    # ✅ RULE 1: older than parent → ALWAYS BÁC
                    if ego_birth < tp_birth:
                        address = "Bác"
                    else:
                        parent_gender = genders.get(tp)
                        if parent_gender == "F":
                            address = "Dì" if ego_gender == "F" else "Cậu"
                        else:
                            address = "Cô" if ego_gender == "F" else "Chú"

                if address is None:
                    if "Anh" in relation or "Chị" in relation:
                        address = "Cô" if ego_gender == "F" else "Chú"
                    else:
                        address = "Dì" if ego_gender == "F" else "Cậu"

                if address:
                    return f"{base} (gọi bằng {address})"

                return base

    # ancestors
    if gen_diff <= -2:
        return ancestor_term(abs(gen_diff), gender)

    # descendants
    if gen_diff >= 2:
        return descendant_term(gen_diff, gender)

    # parent generation
    if gen_diff == -1:
        return parent_generation_term(G, ego, target, genders, births)

    # same generation
    if gen_diff == 0:
        return same_generation_cousin_term(G, ego, target, genders, births)

    return same_generation_term(ego, target, genders, births)