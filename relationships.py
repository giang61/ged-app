# relationships.py
#
# Vietnamese kinship term computation.
# Pure kinship logic — no UI, no graph structure concerns.
# Graph traversal helpers are imported from graph_utils.py.

import re
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
def same_generation_term(ego, target, genders, births, sib_order=None):
    ego_birth    = births.get(ego)
    target_birth = births.get(target)
    gender       = genders.get(target)

    if ego_birth is not None and target_birth is not None:
        if target_birth < ego_birth:
            return "Anh" if gender == "M" else "Chị"
        elif target_birth > ego_birth:
            return "Em trai" if gender == "M" else "Em"

    # Fallback: use sibling order from GEDCOM file position
    if sib_order is not None:
        ego_idx    = sib_order.get(ego)
        target_idx = sib_order.get(target)
        if ego_idx is not None and target_idx is not None:
            if target_idx < ego_idx:
                return "Anh" if gender == "M" else "Chị"
            elif target_idx > ego_idx:
                return "Em trai" if gender == "M" else "Em"

    return "Anh/Chị/Em"


# -------------------------
# In-law term conversion
# -------------------------
def convert_to_inlaw(term, gender):
    mapping = {"Chú": "Thím", "Cậu": "Mợ", "Dì": "Dượng"}
    return mapping.get(term, term)


# -------------------------
# LCA branch helper
# -------------------------
def lca_branch_child(G_anc, lca, descendant):
    """
    Return the child of lca that is an ancestor of (or equal to) descendant.
    This is the 'branch' that descendant belongs to under lca.
    """
    if descendant == lca:
        return lca
    try:
        path = nx.shortest_path(G_anc, lca, descendant)
        if len(path) >= 2:
            return path[1]
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        pass
    return None


def branch_seniority(G_anc, lca, node_a, node_b, births, sib_order):
    """
    Compare the seniority of two nodes by tracing back to their respective
    branches directly off lca, then comparing those branch children by
    birth year first, sib_order second.
    Returns -1 if branch_a is older (senior), +1 if branch_b is older, 0 if unknown.
    """
    branch_a = lca_branch_child(G_anc, lca, node_a)
    branch_b = lca_branch_child(G_anc, lca, node_b)

    if branch_a is None or branch_b is None or branch_a == branch_b:
        return 0

    # 1. Direct birth year comparison
    birth_a = births.get(branch_a)
    birth_b = births.get(branch_b)
    if birth_a is not None and birth_b is not None:
        if birth_a < birth_b:
            return -1
        elif birth_a > birth_b:
            return 1
        return 0

    # 2. sib_order (GEDCOM file position)
    if sib_order is not None:
        idx_a = sib_order.get(branch_a)
        idx_b = sib_order.get(branch_b)
        if idx_a is not None and idx_b is not None:
            if idx_a < idx_b:
                return -1
            elif idx_a > idx_b:
                return 1

    # 3. Proxy: use earliest known birth year among all descendants of each branch.
    #    Older branches tend to have older descendants on average; more importantly,
    #    if one branch's earliest descendant predates the other's, that branch is likely senior.
    def earliest_descendant_birth(branch):
        candidates = [births.get(branch)] + [births.get(d) for d in nx.descendants(G_anc, branch)]
        valid = [y for y in candidates if y is not None]
        return min(valid) if valid else None

    earliest_a = earliest_descendant_birth(branch_a)
    earliest_b = earliest_descendant_birth(branch_b)
    if earliest_a is not None and earliest_b is not None:
        if earliest_a < earliest_b:
            return -1
        elif earliest_a > earliest_b:
            return 1

    return 0


# -------------------------
# Same generation cousins
# -------------------------
def same_generation_cousin_term(G_anc, ego, target, genders, births, sib_order=None, debug=False):
    try:
        ancestor = nx.lowest_common_ancestor(G_anc, ego, target)
    except Exception:
        ancestor = None

    gender = genders.get(target)

    if not ancestor:
        return same_generation_term(ego, target, genders, births, sib_order)

    ego_parents    = list(G_anc.predecessors(ego))
    target_parents = list(G_anc.predecessors(target))

    if not ego_parents or not target_parents:
        return same_generation_term(ego, target, genders, births, sib_order)

    branch_a = lca_branch_child(G_anc, ancestor, ego)
    branch_b = lca_branch_child(G_anc, ancestor, target)
    if debug:
        print(f"  [sgct] ancestor={ancestor}, branch_a={branch_a}, branch_b={branch_b}")
        print(f"  [sgct] birth_a={births.get(branch_a)}, birth_b={births.get(branch_b)}")
        print(f"  [sgct] sib_a={sib_order.get(branch_a) if sib_order else None}, sib_b={sib_order.get(branch_b) if sib_order else None}")

    # Always compare via LCA branches for correctness at any depth
    # cmp == -1 means ego's branch is older (senior) → target is younger → Em
    # cmp == +1 means target's branch is older (senior) → target is Anh/Chị
    cmp = branch_seniority(G_anc, ancestor, ego, target, births, sib_order)
    if debug:
        print(f"  [sgct] cmp={cmp}")
    if cmp == -1:
        return "Em trai" if gender == "M" else "Em"
    elif cmp == 1:
        return "Anh" if gender == "M" else "Chị"

    return same_generation_term(ego, target, genders, births, sib_order)


# -------------------------
# Parent generation
# -------------------------
def parent_generation_term(G_anc, ego, target, genders, births, sib_order=None):
    ego_parents = list(G_anc.predecessors(ego))
    if not ego_parents:
        return None

    gender = genders.get(target)
    mother = next((p for p in ego_parents if genders.get(p) == "F"), None)
    father = next((p for p in ego_parents if genders.get(p) == "M"), None)

    # Find the LCA between ego and target
    try:
        ancestor = nx.lowest_common_ancestor(G_anc, ego, target)
    except Exception:
        ancestor = None

    # Determine which of ego's parents is the one in target's lineage
    # (i.e. which ego_parent is a descendant of the LCA's branch that target is on)
    ego_side_parent = None
    if ancestor:
        for p in ego_parents:
            try:
                nx.shortest_path(G_anc, ancestor, p)
                ego_side_parent = p
                break
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                pass
    if ego_side_parent is None:
        ego_side_parent = ego_parents[0]

    is_maternal = (ego_side_parent == mother)

    # Compare seniority via LCA branches:
    # ego's branch is represented by ego_side_parent; target's branch is target itself.
    # We need to know if target's branch off the LCA is older or younger than ego's branch.
    if ancestor:
        cmp = branch_seniority(G_anc, ancestor, ego_side_parent, target, births, sib_order)
        if cmp == -1:
            # ego's parent's branch is older → target is on a younger branch → Cô/Chú/Dì/Cậu
            return "Dì" if (gender == "F" and is_maternal) else \
                   "Cậu" if (gender == "M" and is_maternal) else \
                   "Cô" if gender == "F" else "Chú"
        elif cmp == 1:
            # target's branch is older → target is Bác
            return "Bác"

    # Fallback: direct sibling check (LCA is shared grandparent)
    target_parents = set(G_anc.predecessors(target))
    for parent in ego_parents:
        parent_parents = set(G_anc.predecessors(parent))
        if parent_parents & target_parents:
            parent_birth = births.get(parent)
            target_birth = births.get(target)
            if parent_birth is not None and target_birth is not None:
                if target_birth < parent_birth:
                    return "Bác"
            elif sib_order is not None:
                p_idx = sib_order.get(parent)
                t_idx = sib_order.get(target)
                if p_idx is not None and t_idx is not None and t_idx < p_idx:
                    return "Bác"
            if parent == mother:
                return "Dì" if gender == "F" else "Cậu"
            else:
                return "Cô" if gender == "F" else "Chú"

    # Last resort: ask how ego's parent relates to target as same-generation cousins
    relation_to_parent = same_generation_cousin_term(G_anc, ego_side_parent, target, genders, births, sib_order)
    if relation_to_parent in ["Anh", "Chị"]:
        return "Bác"
    if relation_to_parent in ["Em", "Em trai"]:
        return "Dì" if (gender == "F" and is_maternal) else \
               "Cậu" if (gender == "M" and is_maternal) else \
               "Cô" if gender == "F" else "Chú"

    return "Dì" if (gender == "F" and is_maternal) else \
           "Cậu" if (gender == "M" and is_maternal) else \
           "Cô" if gender == "F" else "Chú"


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
                               sib_order=None, debug=False, skip_spouse=False):

    def dbg(msg):
        if debug:
            print(msg)

    if ego == target:
        return "Tôi"

    # -------------------------
    # SPOUSE DETECTION
    # -------------------------
    if not skip_spouse:
        # Trigger spouse resolution if ego and target share no *meaningful* common
        # ancestor. A "foreign" LCA (one that is not an ancestor of the target)
        # means ego is from a different family tree — treat them as married-in.
        try:
            _lca_check = nx.lowest_common_ancestor(G_anc, ego, target)
        except Exception:
            _lca_check = None

        # Discard the LCA if it is a foreign node — i.e. it has no path DOWN to
        # ego in G_anc. A genuine LCA must be an ancestor of ego (path lca→ego exists).
        # Sarah's parents (@I500@,@I501@) can reach Sarah but NOT Anna, so they get discarded.
        if _lca_check is not None:
            try:
                nx.shortest_path(G_anc, _lca_check, ego)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                _lca_check = None

        _blood = is_blood_related(ego, target, G_anc)
        print(f"[DIAG] ego={ego} target={target} _lca_check={_lca_check} is_blood={_blood} skip_spouse={skip_spouse}")
        if not _blood or _lca_check is None:
            # Look for a spouse OF EGO who is blood-related to target.
            # e.g. ego=Sarah (married-in), ego_spouse=Đức Thắng (blood member),
            # then compute Đức Thắng's relation to target and map to in-law term.
            ego_spouse = find_spouse(ego, G_full)
            dbg(f"[SPOUSE CHECK] ego={ego}, ego_spouse={ego_spouse}, "
                f"spouse_in_G_anc={G_anc.has_node(ego_spouse) if ego_spouse else None}, "
                f"blood_related={is_blood_related(ego_spouse, target, G_anc) if ego_spouse else None}")
            if ego_spouse and ego_spouse != target:
                if is_blood_related(ego_spouse, target, G_anc):
                    dbg(f"[CASE] ego's spouse is blood-related to target: {ego_spouse}")
                    base_relation = compute_vietnamese_kinship(
                        ego_spouse, target, G_anc, G_full, genders, births,
                        sib_order=sib_order, debug=debug, skip_spouse=True
                    )
                    dbg(f"[INFO] base_relation={base_relation}")
                    ego_gender = genders.get(ego)
                    #   Female ego (wife): husband's relatives get "chồng" suffix
                    #   Male ego (husband): wife's relatives get "vợ" suffix
                    if ego_gender == "F":
                        mapping = {
                            "Bố":       "Bố chồng",
                            "Mẹ":       "Mẹ chồng",
                            "Ông":      "Ông chồng",
                            "Bà":       "Bà chồng",
                            "Anh":      "Anh chồng",
                            "Chị":      "Chị chồng",
                            "Em":       "Em chồng",
                            "Em trai":  "Em chồng",
                            "Chú":      "Chú chồng",
                            "Cô":       "Cô chồng",
                            "Bác":      "Bác chồng",
                            "Cậu":      "Cậu chồng",
                            "Dì":       "Dì chồng",
                            "Con trai": "Con trai",
                            "Con gái":  "Con dâu",
                            "Cháu trai":"Cháu trai",
                            "Cháu gái": "Cháu gái",
                        }
                    else:
                        mapping = {
                            "Bố":       "Bố vợ",
                            "Mẹ":       "Mẹ vợ",
                            "Ông":      "Ông vợ",
                            "Bà":       "Bà vợ",
                            "Anh":      "Anh vợ",
                            "Chị":      "Chị vợ",
                            "Em":       "Em vợ",
                            "Em trai":  "Em vợ",
                            "Chú":      "Chú vợ",
                            "Cô":       "Cô vợ",
                            "Bác":      "Bác vợ",
                            "Cậu":      "Cậu vợ",
                            "Dì":       "Dì vợ",
                            "Con trai": "Con rể",
                            "Con gái":  "Con gái",
                            "Cháu trai":"Cháu trai",
                            "Cháu gái": "Cháu gái",
                        }

                    # Direct lookup (simple terms like "Bố", "Anh", etc.)
                    result = mapping.get(base_relation)
                    if result:
                        return result

                    # Compound term: "Cháu gái (gọi bằng Cậu)" → "Cháu gái (gọi bằng Mợ)"
                    # The inner gọi bằng term is an address term — use traditional
                    # in-law address mappings, NOT the "chồng/vợ" suffix pattern.
                    if ego_gender == "F":
                        inlaw_address = {
                            "Chú":  "Thím",
                            "Cậu":  "Mợ",
                            "Bác":  "Bác",
                            "Cô":   "Cô",
                            "Dì":   "Dì",
                            "Anh":  "Chị dâu",
                            "Chị":  "Anh rể",
                            "Em":   "Em dâu",
                        }
                    else:
                        inlaw_address = {
                            "Chú":  "Thím",
                            "Cậu":  "Mợ",
                            "Bác":  "Bác",
                            "Cô":   "Cô",
                            "Dì":   "Dì",
                            "Anh":  "Chị dâu",
                            "Chị":  "Anh rể",
                            "Em":   "Em rể",
                        }
                    m = re.search(r"^(.*?)\s*\(gọi bằng (.+?)\)$", base_relation)
                    dbg(f"[REGEX] match={m}, groups={m.groups() if m else None}")
                    if m:
                        prefix = m.group(1).strip()
                        inner  = m.group(2).strip()
                        mapped = inlaw_address.get(inner)
                        if mapped:
                            return f"{prefix} (gọi bằng {mapped})"

                    return base_relation

            # Second path: target is the married-in spouse.
            # Find target's blood spouse, compute ego's relation to that blood spouse,
            # then convert to the appropriate in-law term from ego's perspective.
            # e.g. ego=Anna, target=Sarah → target_spouse=Đức Chí
            #      Anna's relation to Đức Chí = "Cậu" → Sarah is "Mợ" to Anna.
            target_spouse = find_spouse(target, G_full)
            dbg(f"[SPOUSE CHECK target] target={target}, target_spouse={target_spouse}, "
                f"blood_related={is_blood_related(ego, target_spouse, G_anc) if target_spouse else None}")
            if target_spouse and target_spouse != ego:
                if is_blood_related(ego, target_spouse, G_anc):
                    dbg(f"[CASE] target's spouse is blood-related to ego: {target_spouse}")
                    # What is target_spouse to ego?
                    base_relation = compute_vietnamese_kinship(
                        ego, target_spouse, G_anc, G_full, genders, births,
                        sib_order=sib_order, debug=debug, skip_spouse=True
                    )
                    dbg(f"[INFO] base_relation (ego→target_spouse)={base_relation}")
                    target_gender = genders.get(target)
                    # Map: "what is target_spouse to ego" → "what is target to ego"
                    # Rule: vợ/rể suffix ONLY applies to relatives of ego's OWN spouse.
                    # For other married-in people, use plain seniority terms.
                    if target_gender == "F":
                        # target is female; target_spouse is her husband (blood relative of ego)
                        mapping = {
                            "Bố":      "Mẹ chồng",
                            "Mẹ":      "Bố chồng",
                            "Anh":     "Chị dâu",
                            "Chị":     "Anh rể",
                            "Em":      "Em dâu",
                            "Em trai": "Em dâu",
                            "Chú":     "Thím",
                            "Cậu":     "Mợ",
                            "Bác":     "Bác",
                            "Cô":      "Cô",
                            "Dì":      "Dì",
                            "Con trai":"Con dâu",
                            "Con gái": "Con gái",
                        }
                    else:
                        # target is male; target_spouse is his wife (blood relative of ego)
                        # Use plain seniority — no vợ/rể since this is not ego's own spouse's family
                        mapping = {
                            "Bố":      "Bố vợ",
                            "Mẹ":      "Mẹ vợ",
                            "Chị":     "Anh",        # wife is senior (Chị) → husband is Anh
                            "Em":      "Em",         # wife is junior (Em) → husband is Em
                            "Em trai": "Em",
                            "Chú":     "Chú",
                            "Cậu":     "Cậu",
                            "Bác":     "Bác",
                            "Cô":      "Cô",
                            "Dì":      "Dì",
                            "Con trai":"Con rể",
                            "Con gái": "Con gái",
                        }
                    result = mapping.get(base_relation)
                    if result:
                        return result
                    return base_relation
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
        # Fallback to sibling order
        if sib_order is not None:
            ego_idx    = sib_order.get(ego)
            target_idx = sib_order.get(target)
            if ego_idx is not None and target_idx is not None:
                if target_idx < ego_idx:
                    return "Anh" if gender == "M" else "Chị"
                elif target_idx > ego_idx:
                    return "Em"
        return "Anh/Chị/Em"

    try:
        ancestor = nx.lowest_common_ancestor(G_anc, ego, target)
    except Exception:
        ancestor = None

    dbg(f"ancestor={ancestor}")

    if not ancestor:
        dbg("[CASE] no ancestor fallback")
        return same_generation_term(ego, target, genders, births, sib_order)

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
            elif sib_order is not None:
                ego_idx = sib_order.get(ego)
                tp_idx  = sib_order.get(true_parent)
                if ego_idx is not None and tp_idx is not None:
                    if ego_idx < tp_idx:
                        address = "Bác"
                    else:
                        address = ("Dì" if ego_gender == "F" else "Cậu") if tp_gender == "F" \
                                  else ("Cô" if ego_gender == "F" else "Chú")
                else:
                    address = "Bác"
            else:
                address = "Bác"
        else:
            dbg("[SUBCASE] cousin child")
            relation = same_generation_cousin_term(G_anc, ego, true_parent, genders, births, sib_order)
            dbg(f"relation_to_parent={relation}")

            # Find the LCA between ego and true_parent, then compare their branches
            try:
                cousin_lca = nx.lowest_common_ancestor(G_anc, ego, true_parent)
            except Exception:
                cousin_lca = None

            if cousin_lca:
                cmp = branch_seniority(G_anc, cousin_lca, ego, true_parent, births, sib_order)
                dbg(f"cousin_lca={cousin_lca}, branch_seniority={cmp}")
                if cmp == -1:
                    # ego's branch is older → ego is Bác to true_parent's child
                    address = "Bác"
                elif cmp == 1:
                    # true_parent's branch is older → ego is Cô/Chú/Dì/Cậu
                    address = ("Dì" if ego_gender == "F" else "Cậu") if tp_gender == "F" \
                              else ("Cô" if ego_gender == "F" else "Chú")
                else:
                    # Unknown — fall back to relation string
                    if relation and ("Anh" in relation or "Chị" in relation):
                        address = ("Dì" if ego_gender == "F" else "Cậu") if tp_gender == "F" \
                                  else ("Cô" if ego_gender == "F" else "Chú")
                    else:
                        address = "Bác"
            else:
                if relation and ("Anh" in relation or "Chị" in relation):
                    address = ("Dì" if ego_gender == "F" else "Cậu") if tp_gender == "F" \
                              else ("Cô" if ego_gender == "F" else "Chú")
                else:
                    address = "Bác"

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
        return parent_generation_term(G_anc, ego, target, genders, births, sib_order)

    # Same generation
    if gen_diff == 0:
        dbg("[CASE] same generation cousin")
        return same_generation_cousin_term(G_anc, ego, target, genders, births, sib_order, debug=debug)

    dbg("[CASE] fallback same generation")
    return same_generation_term(ego, target, genders, births, sib_order)
