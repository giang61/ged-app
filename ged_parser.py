# ged_parser.py

import re
import unicodedata
import networkx as nx
from ged4py.parser import GedcomReader


def extract_birth_year(indi):
    for sub in indi.sub_records:
        if sub.tag == "BIRT":
            for s in sub.sub_records:
                if s.tag == "DATE" and s.value:
                    match = re.search(r"\b(\d{4})\b", str(s.value))
                    if match:
                        return int(match.group(1))
    return None


def extract_gender(indi):
    for sub in indi.sub_records:
        if sub.tag == "SEX":
            return sub.value
    return None


def normalize_name(name):
    """Normalize a name for duplicate detection: lowercase, strip diacritics."""
    if not name:
        return ""
    name = name.lower().strip()
    name = unicodedata.normalize("NFD", name)
    name = "".join(c for c in name if unicodedata.category(c) != "Mn")
    name = name.replace("đ", "d")
    name = re.sub(r" +", " ", name)
    return name


# Words that indicate an unknown/placeholder person — never merge these
PLACEHOLDER_WORDS = {
    "?", "xx", "khong", "biet", "unknown", "", "...", "x"
}

def is_usable_name(name):
    """
    Reject blank, single-word, or placeholder names.
    Name must have at least 2 words and not consist entirely of placeholders.
    """
    if not name:
        return False
    # Use raw normalized name but KEEP diacritics for this check
    # so 'Hưng' and 'Hung' are not confused
    raw = name.strip().lower()
    if not raw:
        return False
    words = raw.split()
    if len(words) < 2:
        return False
    # Reject if any word is a placeholder
    norm_words = [normalize_name(w) for w in words]
    if any(w in PLACEHOLDER_WORDS for w in norm_words):
        return False
    # Reject names that are mostly dots or question marks
    clean = re.sub(r"[.? ]", "", raw)
    if len(clean) < 3:
        return False
    return True

def normalize_name_strict(name):
    """
    Normalize but PRESERVE diacritics distinction — only lowercase and strip spaces.
    Used for actual matching so 'Hùng' != 'Hưng', 'Oanh' != 'Oánh'.
    """
    if not name:
        return ""
    # Lowercase, collapse spaces, strip
    name = name.strip().lower()
    name = re.sub(r" +", " ", name)
    # Replace đ -> d but keep all other Vietnamese diacritics
    name = name.replace("đ", "d")
    return name

def given_name_key_strict(name):
    """
    Extract given name (drop last word = family name in Vietnamese naming convention).
    Uses strict normalization that preserves diacritics.
    E.g. 'Thị Hương Diệp Đỗ'     -> 'thị hương diệp'
         'Thị Hương Diệp Nguyễn'  -> 'thị hương diệp'  ← same key, will merge
         'Thị Hương Giang Nguyễn' -> 'thị hương giang' ← different, will NOT merge
    """
    n = normalize_name_strict(name)
    words = n.split()
    if len(words) >= 3:
        return " ".join(words[:-1])  # drop family name (last word)
    return n

def find_duplicates(names, birth_years):
    """
    Find groups of IDs that appear to be the same person.
    Rules:
      - Name must pass is_usable_name() — no placeholders, min 2 words
      - Diacritics are preserved in matching (Hùng != Hưng, Oanh != Oánh)
      - Match key = (given_name_without_family_name, birth_year)
      - If birth_year missing: require EXACT full name match (stricter)
    """
    groups = {}
    for pid, name in names.items():
        if not is_usable_name(name):
            continue
        given = given_name_key_strict(name)
        birth = birth_years.get(pid)
        if birth is None:
            # Require full exact name match when no birth year —
            # dropping the family name caused false merges (e.g. foreign spouses)
            key = ("exact", normalize_name_strict(name))
        else:
            # Given name (no family name) + birth year
            key = ("given+birth", given, birth)
        groups.setdefault(key, []).append(pid)

    merge_map = {}
    for key, group in groups.items():
        if len(group) > 1:
            canonical = group[0]
            for dup in group[1:]:
                merge_map[dup] = canonical
                print(f"[MERGE] {dup} -> {canonical}  ({names[dup]}, {birth_years.get(dup)})")
    return merge_map


def apply_merge(G_full, G_anc, names, genders, birth_years, merge_map):
    """
    Redirect all edges from duplicate nodes to their canonical node,
    then remove the duplicate nodes.
    """
    for graph in [G_full, G_anc]:
        for dup, canon in merge_map.items():
            if not graph.has_node(dup):
                continue
            # Re-add edges pointing to/from dup, redirected to canon
            for pred in list(graph.predecessors(dup)):
                edge_data = graph.edges[pred, dup]
                if pred != canon and not graph.has_edge(pred, canon):
                    graph.add_edge(pred, canon, **edge_data)
            for succ in list(graph.successors(dup)):
                edge_data = graph.edges[dup, succ]
                if succ != canon and not graph.has_edge(canon, succ):
                    graph.add_edge(canon, succ, **edge_data)
            graph.remove_node(dup)

    # Clean up metadata dicts
    for dup, canon in merge_map.items():
        # Fill in missing data on canonical from duplicate if needed
        if not birth_years.get(canon) and birth_years.get(dup):
            birth_years[canon] = birth_years[dup]
        if not genders.get(canon) and genders.get(dup):
            genders[canon] = genders[dup]
        # Remove duplicate entries
        for d in [names, genders, birth_years]:
            d.pop(dup, None)

    return G_full, G_anc, names, genders, birth_years


def load_gedcom(file_path):

    G_full = nx.DiGraph()
    G_anc = nx.DiGraph()

    names = {}
    genders = {}
    birth_years = {}
    sib_order = {}   # pid -> int: position among siblings (0 = oldest by file order)

    with GedcomReader(file_path) as parser:

        # ---------- Individuals ----------
        for indi in parser.records0("INDI"):
            pid = indi.xref_id
            name = indi.name.format() if indi.name else pid
            gender = extract_gender(indi)
            birth = extract_birth_year(indi)

            names[pid] = name
            genders[pid] = gender
            birth_years[pid] = birth

            G_full.add_node(pid)
            G_anc.add_node(pid)

        # ---------- Families ----------
        for fam in parser.records0("FAM"):
            father = None
            mother = None
            children = []

            for sub in fam.sub_records:
                if sub.tag == "HUSB":
                    father = sub.value
                elif sub.tag == "WIFE":
                    mother = sub.value
                elif sub.tag == "CHIL":
                    children.append(sub.value)

            parents = [p for p in [father, mother] if p]

            for p in parents:
                for c in children:
                    G_full.add_edge(p, c, relation="parent")
                    G_full.add_edge(c, p, relation="child")
                    G_anc.add_edge(p, c)

            if father and mother:
                G_full.add_edge(father, mother, relation="spouse")
                G_full.add_edge(mother, father, relation="spouse")

            # Record sibling order from CHIL file position (0 = oldest)
            for idx, child in enumerate(children):
                sib_order[child] = idx

    # ---------- Merge duplicates ----------
    merge_map = find_duplicates(names, birth_years)
    if merge_map:
        G_full, G_anc, names, genders, birth_years = apply_merge(
            G_full, G_anc, names, genders, birth_years, merge_map
        )
        # Remap sib_order keys for merged duplicates
        for dup, canon in merge_map.items():
            if dup in sib_order:
                if canon not in sib_order:
                    sib_order[canon] = sib_order[dup]
                del sib_order[dup]

    return G_full, G_anc, names, genders, birth_years, sib_order
