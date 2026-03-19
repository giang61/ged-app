# ged_parser.py

import re
import networkx as nx
from ged4py.parser import GedcomReader


def extract_birth_year(indi):
    """Extract birth year from GEDCOM record."""
    for sub in indi.sub_records:
        if sub.tag == "BIRT":
            for s in sub.sub_records:
                if s.tag == "DATE" and s.value:
                    match = re.search(r"\b(\d{4})\b", str(s.value))
                    if match:
                        return int(match.group(1))
    return None


def extract_gender(indi):
    """Extract gender."""
    for sub in indi.sub_records:
        if sub.tag == "SEX":
            return sub.value
    return None


def load_gedcom(file_path):

    G_full = nx.DiGraph()
    G_anc = nx.DiGraph()

    names = {}
    genders = {}
    birth_years = {}

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

            # parent-child edges
            for p in parents:
                for c in children:

                    G_full.add_edge(p, c, relation="parent")
                    G_full.add_edge(c, p, relation="child")

                    G_anc.add_edge(p, c)

            # spouse edges
            if father and mother:

                G_full.add_edge(father, mother, relation="spouse")
                G_full.add_edge(mother, father, relation="spouse")

    return G_full, G_anc, names, genders, birth_years