#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Éditeur de listes de payloads pour PS5 Relapse (relapse/index.html).

L'application gère :
  - les listes principales (catégories) affichées en onglets dans la page,
  - les sous-listes (groupes) de chaque liste principale,
  - les payloads eux-mêmes : fichier .elf choisi dans payloads/, titre et
    description libres, ordre d'affichage.

Elle écrit deux fichiers à la racine du projet :
  - payloads-data.json : le modèle, lisible et versionnable,
  - payloads-data.js   : le même modèle chargé par relapse/index.html
                         (via window.applyPayloadModel).

Utilisation :
    python payloads_editor.py            # ouvre l'interface
    python payloads_editor.py --check    # vérifie les listes sans interface
    python payloads_editor.py --sync     # réécrit les fichiers générés
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MODEL_VERSION = 1
DATA_JSON_NAME = "payloads-data.json"
DATA_JS_NAME = "payloads-data.js"
DEFAULT_CATEGORY_LABELS = {
    "hen": "HEN Loader",
    "linux": "Linux Loader",
    "utility": "Utility",
}
ELF_MAGIC = b"\x7fELF"


class ModelError(Exception):
    """Modèle illisible ou invalide."""


# ---------------------------------------------------------------------------
# Modèle de données
# ---------------------------------------------------------------------------

def blank_model() -> dict:
    return {"version": MODEL_VERSION, "categories": []}


def new_tile(title: str, name: str, desc: str = "") -> dict:
    return {"title": title or Path(name).stem, "name": name, "desc": desc or ""}


def slugify(text: str, fallback: str = "liste") -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or fallback


def unique_id(base: str, taken) -> str:
    taken = set(taken)
    if base not in taken:
        return base
    index = 2
    while f"{base}-{index}" in taken:
        index += 1
    return f"{base}-{index}"


def categories(model: dict) -> list:
    return model.setdefault("categories", [])


def groups_of(category: dict) -> list:
    return category.setdefault("groups", [])


def tiles_of(group: dict) -> list:
    return group.setdefault("tiles", [])


def find_category(model: dict, cat_id: str):
    for category in categories(model):
        if category.get("id") == cat_id:
            return category
    return None


def ensure_category(model: dict, cat_id: str, label: str) -> dict:
    category = find_category(model, cat_id)
    if category is None:
        category = {"id": cat_id, "label": label or cat_id, "groups": []}
        categories(model).append(category)
    return category


def tile_count(category: dict) -> int:
    return sum(len(group.get("tiles") or []) for group in groups_of(category))


def all_tiles(model: dict):
    for category in categories(model):
        for group in groups_of(category):
            for tile in tiles_of(group):
                yield tile


def total_payloads(model: dict) -> int:
    return sum(1 for _ in all_tiles(model))


def total_groups(model: dict) -> int:
    return sum(len(groups_of(category)) for category in categories(model))


# ---------------------------------------------------------------------------
# Fichiers ELF
# ---------------------------------------------------------------------------

def scan_elf_files(payloads_dir: Path) -> list:
    if not payloads_dir.is_dir():
        return []
    return sorted(
        path.name
        for path in payloads_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".elf"
    )


def is_elf(payloads_dir: Path, name: str) -> bool:
    path = payloads_dir / name
    try:
        with path.open("rb") as handle:
            return handle.read(4) == ELF_MAGIC
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Lecture / écriture
# ---------------------------------------------------------------------------

def normalize_model(data) -> dict:
    if not isinstance(data, dict):
        raise ModelError("Le modèle n'est pas un objet JSON.")

    model = blank_model()
    raw_categories = data.get("categories")
    if not isinstance(raw_categories, list):
        raise ModelError("Le modèle ne contient pas de liste « categories ».")

    for raw_category in raw_categories:
        if not isinstance(raw_category, dict):
            continue
        label = str(raw_category.get("label") or raw_category.get("id") or "Liste").strip()
        category = {
            "id": str(raw_category.get("id") or slugify(label)).strip(),
            "label": label,
            "groups": [],
        }

        for raw_group in raw_category.get("groups") or []:
            if not isinstance(raw_group, dict):
                continue
            group_label = str(raw_group.get("label") or raw_group.get("id") or "Payloads").strip()
            group = {
                "id": str(raw_group.get("id") or slugify(group_label)).strip(),
                "label": group_label,
                "tiles": [],
            }
            for raw_tile in raw_group.get("tiles") or []:
                if not isinstance(raw_tile, dict):
                    continue
                name = str(raw_tile.get("name") or "").strip()
                if not name:
                    continue
                group["tiles"].append({
                    "title": str(raw_tile.get("title") or Path(name).stem).strip(),
                    "name": name,
                    "desc": str(raw_tile.get("desc") or raw_tile.get("description") or "").strip(),
                })
            category["groups"].append(group)
        model["categories"].append(category)

    return model


def seed_model(root: Path, payloads_dir: Path) -> dict:
    """Premier lancement : les trois listes principales et les ELF du dossier.

    Les fichiers de payloads/ arrivent dans « Linux Loader › À classer » ;
    ils se répartissent ensuite depuis l'éditeur.
    """
    model = blank_model()
    for cat_id, label in DEFAULT_CATEGORY_LABELS.items():
        ensure_category(model, cat_id, label)

    files = scan_elf_files(payloads_dir)
    if files:
        groups_of(find_category(model, "linux")).append({
            "id": "a-classer",
            "label": "À classer",
            "tiles": [new_tile(Path(name).stem, name) for name in files],
        })

    return model


def load_model(paths: "Paths") -> tuple:
    """Renvoie (modèle, origine) en privilégiant le JSON puis le JS généré."""
    if paths.json.is_file():
        try:
            data = json.loads(paths.json.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ModelError(f"Impossible de lire {paths.json.name} : {exc}") from exc
        return normalize_model(data), paths.json.name

    if paths.js.is_file():
        text = paths.js.read_text(encoding="utf-8", errors="replace")
        marker = text.find("window.PAYLOAD_MODEL")
        if marker >= 0:
            brace = text.find("{", marker)
            if brace >= 0:
                try:
                    data, _ = json.JSONDecoder().raw_decode(text[brace:])
                    return normalize_model(data), paths.js.name
                except ValueError:
                    pass

    return seed_model(paths.root, paths.payloads), "nouveau modèle depuis payloads/"


JS_HEADER = """/* Généré par payloads_editor.py — ne pas modifier à la main.
   Source : {json_name} */
window.PAYLOAD_MODEL = """

JS_FOOTER = """;

(function () {
  var model = window.PAYLOAD_MODEL;
  if (!model || !model.categories || !model.categories.length) return;

  if (typeof window.applyPayloadModel === "function") {
    window.applyPayloadModel(model);
    return;
  }

  /* Page sans gestion de modèle : liste plate de secours. */
  var flat = [];
  for (var i = 0; i < model.categories.length; i++) {
    var groups = model.categories[i].groups || [];
    for (var j = 0; j < groups.length; j++) {
      flat = flat.concat(groups[j].tiles || []);
    }
  }
  window.PAYLOAD_TILES = flat;
})();
"""


def render_js(model: dict, json_name: str) -> str:
    payload = json.dumps(model, ensure_ascii=False, indent=2)
    return JS_HEADER.format(json_name=json_name) + payload + JS_FOOTER


def write_outputs(model: dict, paths: "Paths") -> None:
    paths.json.write_text(
        json.dumps(model, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    paths.js.write_text(render_js(model, paths.json.name), encoding="utf-8")


def validate_model(model: dict, payloads_dir: Path) -> list:
    problems = []
    available = set(scan_elf_files(payloads_dir))
    listed = set()

    if not categories(model):
        problems.append("Le modèle ne contient aucune liste principale.")

    for category in categories(model):
        if not groups_of(category):
            problems.append(f"Liste « {category.get('label')} » : aucune sous-liste.")
        for group in groups_of(category):
            if not tiles_of(group):
                problems.append(
                    f"« {category.get('label')} / {group.get('label')} » : aucun payload."
                )
            for tile in tiles_of(group):
                name = tile.get("name", "")
                listed.add(name)
                if name not in available:
                    problems.append(f"Fichier absent de payloads/ : {name}")
                elif not is_elf(payloads_dir, name):
                    problems.append(f"Fichier qui n'est pas un ELF valide : {name}")

    if not payloads_dir.is_dir():
        problems.append(f"Dossier introuvable : {payloads_dir}")

    unused = sorted(available - listed)
    if unused:
        problems.append(
            f"{len(unused)} fichier(s) de payloads/ non classé(s) : "
            + ", ".join(unused[:5])
            + ("…" if len(unused) > 5 else "")
        )
    return problems


@dataclass
class Paths:
    root: Path
    payloads: Path
    json: Path
    js: Path

    @property
    def json_name(self) -> str:
        return self.json.name


def resolve_paths(args) -> Paths:
    root = Path(args.root).expanduser().resolve() if args.root else Path(__file__).resolve().parent
    payloads = Path(args.payloads).expanduser().resolve() if args.payloads else root / "payloads"
    json_path = Path(args.json).expanduser().resolve() if args.json else root / DATA_JSON_NAME
    js_path = Path(args.js).expanduser().resolve() if args.js else root / DATA_JS_NAME
    return Paths(root=root, payloads=payloads, json=json_path, js=js_path)


# ---------------------------------------------------------------------------
# Interface graphique
# ---------------------------------------------------------------------------

try:
    import tkinter as tk
    from tkinter import messagebox, simpledialog, ttk
except Exception as _tk_error:  # pragma: no cover - dépend de l'installation
    tk = None
    ttk = None
    messagebox = None
    simpledialog = None
    TK_ERROR = _tk_error
else:
    TK_ERROR = None


if tk is not None:

    class PayloadPicker(tk.Toplevel):
        """Choix d'un ou plusieurs ELF de payloads/ + titre et description."""

        def __init__(self, master, files, used_names):
            super().__init__(master)
            self.title("Ajouter des payloads")
            self.result = []
            self.files = list(files)
            self.transient(master)
            self.minsize(560, 420)

            body = ttk.Frame(self, padding=12)
            body.pack(fill="both", expand=True)

            ttk.Label(
                body,
                text="Fichiers .elf disponibles dans payloads/ (Ctrl+clic pour plusieurs) :",
            ).pack(anchor="w")

            list_frame = ttk.Frame(body)
            list_frame.pack(fill="both", expand=True, pady=(6, 10))
            self.file_list = tk.Listbox(
                list_frame, selectmode="extended", exportselection=False, activestyle="none"
            )
            scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
            self.file_list.configure(yscrollcommand=scroll.set)
            self.file_list.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")

            for name in self.files:
                suffix = "   (déjà listé)" if name in used_names else ""
                self.file_list.insert("end", name + suffix)

            form = ttk.Frame(body)
            form.pack(fill="x")
            form.columnconfigure(0, weight=1)

            self.title_var = tk.StringVar()
            self.desc_var = tk.StringVar()
            ttk.Label(form, text="Titre (vide = nom du fichier) :").grid(row=0, column=0, sticky="w")
            ttk.Entry(form, textvariable=self.title_var).grid(
                row=1, column=0, sticky="ew", pady=(2, 8)
            )
            ttk.Label(form, text="Description (facultatif) :").grid(row=2, column=0, sticky="w")
            ttk.Entry(form, textvariable=self.desc_var).grid(
                row=3, column=0, sticky="ew", pady=(2, 0)
            )

            buttons = ttk.Frame(body)
            buttons.pack(fill="x", pady=(14, 0))
            ttk.Button(buttons, text="Ajouter", command=self._on_add).pack(side="right")
            ttk.Button(buttons, text="Annuler", command=self.destroy).pack(
                side="right", padx=(0, 8)
            )

            self.bind("<Return>", lambda event: self._on_add())
            self.bind("<Escape>", lambda event: self.destroy())
            self.file_list.focus_set()

        def _on_add(self):
            picks = [self.files[index] for index in self.file_list.curselection()]
            if not picks:
                messagebox.showinfo(
                    "Aucune sélection", "Sélectionnez au moins un fichier .elf.", parent=self
                )
                return
            title = self.title_var.get().strip()
            desc = self.desc_var.get().strip()
            single = len(picks) == 1
            self.result = [
                {
                    "title": title if single and title else Path(name).stem,
                    "name": name,
                    "desc": desc,
                }
                for name in picks
            ]
            self.destroy()

    class PayloadDialog(tk.Toplevel):
        """Modification d'une entrée de payload."""

        def __init__(self, master, tile, files):
            super().__init__(master)
            self.title("Modifier le payload")
            self.result = None
            self.transient(master)
            self.resizable(False, False)

            body = ttk.Frame(self, padding=12)
            body.pack(fill="both", expand=True)
            body.columnconfigure(1, weight=1)

            self.file_var = tk.StringVar(value=tile.get("name", ""))
            self.title_var = tk.StringVar(value=tile.get("title", ""))
            self.desc_var = tk.StringVar(value=tile.get("desc", ""))

            ttk.Label(body, text="Fichier ELF :").grid(row=0, column=0, sticky="w", pady=2)
            ttk.Combobox(
                body, textvariable=self.file_var, values=list(files), width=44
            ).grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)

            ttk.Label(body, text="Titre :").grid(row=1, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=self.title_var, width=44).grid(
                row=1, column=1, sticky="ew", padx=(8, 0), pady=2
            )

            ttk.Label(body, text="Description :").grid(row=2, column=0, sticky="w", pady=2)
            ttk.Entry(body, textvariable=self.desc_var, width=44).grid(
                row=2, column=1, sticky="ew", padx=(8, 0), pady=2
            )

            buttons = ttk.Frame(body)
            buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(12, 0))
            ttk.Button(buttons, text="Valider", command=self._on_ok).pack(side="right")
            ttk.Button(buttons, text="Annuler", command=self.destroy).pack(
                side="right", padx=(0, 8)
            )

            self.bind("<Return>", lambda event: self._on_ok())
            self.bind("<Escape>", lambda event: self.destroy())
            self.focus_set()

        def _on_ok(self):
            name = self.file_var.get().strip()
            if not name:
                messagebox.showinfo("Fichier manquant", "Choisissez un fichier ELF.", parent=self)
                return
            self.result = {
                "title": self.title_var.get().strip() or Path(name).stem,
                "name": name,
                "desc": self.desc_var.get().strip(),
            }
            self.destroy()

    class PayloadsEditor(tk.Tk):
        def __init__(self, paths: Paths):
            super().__init__()
            self.paths = paths
            self.model = blank_model()
            self.dirty = False
            self.category_index = 0
            self.group_index = 0
            self.tile_index = 0
            self._refreshing = False

            self.title("Éditeur de listes — PS5 Relapse")
            self.geometry("1180x680")
            self.minsize(980, 560)

            self._build_ui()
            self._load_initial_model()
            self.refresh_all()
            self.bind("<Control-s>", lambda event: self.save())
            self.bind("<Control-S>", lambda event: self.save())
            self.protocol("WM_DELETE_WINDOW", self.on_close)

        # -- construction ---------------------------------------------------
        def _build_ui(self):
            outer = ttk.Frame(self, padding=10)
            outer.pack(fill="both", expand=True)

            toolbar = ttk.Frame(outer)
            toolbar.pack(fill="x", pady=(0, 8))
            ttk.Button(toolbar, text="Enregistrer", command=self.save).pack(side="left")
            ttk.Button(toolbar, text="Recharger", command=self.reload_model).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(toolbar, text="Vérifier", command=self.verify).pack(
                side="left", padx=(6, 0)
            )
            self.status_var = tk.StringVar(value="")
            ttk.Label(toolbar, textvariable=self.status_var).pack(side="right")

            paned = ttk.Panedwindow(outer, orient="horizontal")
            paned.pack(fill="both", expand=True)

            # -- listes principales
            left = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(left, weight=2)
            ttk.Label(left, text="Listes principales (onglets de la page)").pack(anchor="w")
            self.category_list = self._make_listbox(left)
            self._make_list_buttons(
                left,
                on_add=self.add_category,
                on_rename=self.rename_category,
                on_delete=self.delete_category,
                on_move=self.move_category,
            )
            self.category_list.bind("<<ListboxSelect>>", self._on_category_select)

            # -- sous-listes
            middle = ttk.Frame(paned, padding=(0, 0, 6, 0))
            paned.add(middle, weight=2)
            ttk.Label(middle, text="Sous-listes (classement)").pack(anchor="w")
            self.group_list = self._make_listbox(middle)
            self._make_list_buttons(
                middle,
                on_add=self.add_group,
                on_rename=self.rename_group,
                on_delete=self.delete_group,
                on_move=self.move_group,
            )
            self.group_list.bind("<<ListboxSelect>>", self._on_group_select)

            # -- payloads
            right = ttk.Frame(paned)
            paned.add(right, weight=5)
            ttk.Label(right, text="Payloads de la sous-liste").pack(anchor="w")

            tree_frame = ttk.Frame(right)
            tree_frame.pack(fill="both", expand=True, pady=(4, 6))
            self.payload_tree = ttk.Treeview(
                tree_frame,
                columns=("title", "name", "desc", "state"),
                show="headings",
                selectmode="browse",
            )
            for column, heading, width in (
                ("title", "Titre", 210),
                ("name", "Fichier ELF", 250),
                ("desc", "Description", 170),
                ("state", "État", 80),
            ):
                self.payload_tree.heading(column, text=heading)
                self.payload_tree.column(column, width=width, anchor="w")
            tree_scroll = ttk.Scrollbar(
                tree_frame, orient="vertical", command=self.payload_tree.yview
            )
            self.payload_tree.configure(yscrollcommand=tree_scroll.set)
            self.payload_tree.pack(side="left", fill="both", expand=True)
            tree_scroll.pack(side="right", fill="y")

            payload_buttons = ttk.Frame(right)
            payload_buttons.pack(fill="x")
            ttk.Button(
                payload_buttons, text="Ajouter un ELF…", command=self.add_payloads
            ).pack(side="left")
            ttk.Button(
                payload_buttons, text="Ajouter les non classés", command=self.add_unused_payloads
            ).pack(side="left", padx=(6, 0))
            ttk.Button(payload_buttons, text="Modifier…", command=self.edit_payload).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(payload_buttons, text="Retirer", command=self.delete_payload).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(payload_buttons, text="↑", width=3, command=lambda: self.move_payload(-1)).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(payload_buttons, text="↓", width=3, command=lambda: self.move_payload(1)).pack(
                side="left", padx=(2, 0)
            )

            self.payload_tree.bind("<<TreeviewSelect>>", self._on_payload_select)
            self.payload_tree.bind("<Double-1>", lambda event: self.edit_payload())
            self.payload_tree.bind("<Delete>", lambda event: self.delete_payload())

            self.update_title()

        def _make_listbox(self, parent):
            frame = ttk.Frame(parent)
            frame.pack(fill="both", expand=True, pady=(4, 6))
            listbox = tk.Listbox(frame, exportselection=False, activestyle="none")
            scroll = ttk.Scrollbar(frame, orient="vertical", command=listbox.yview)
            listbox.configure(yscrollcommand=scroll.set)
            listbox.pack(side="left", fill="both", expand=True)
            scroll.pack(side="right", fill="y")
            return listbox

        def _make_list_buttons(self, parent, on_add, on_rename, on_delete, on_move):
            buttons = ttk.Frame(parent)
            buttons.pack(fill="x")
            ttk.Button(buttons, text="Ajouter…", command=on_add).pack(side="left")
            ttk.Button(buttons, text="Renommer…", command=on_rename).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(buttons, text="Supprimer", command=on_delete).pack(
                side="left", padx=(6, 0)
            )
            ttk.Button(
                buttons, text="↑", width=3, command=lambda: on_move(-1)
            ).pack(side="left", padx=(6, 0))
            ttk.Button(
                buttons, text="↓", width=3, command=lambda: on_move(1)
            ).pack(side="left", padx=(2, 0))

        # -- modèle ---------------------------------------------------------
        def _load_initial_model(self):
            try:
                model, origin = load_model(self.paths)
                self.model = model
                self.set_status(f"Modèle chargé depuis {origin}.")
            except ModelError as exc:
                self.model = seed_model(self.paths.root, self.paths.payloads)
                messagebox.showerror(
                    "Modèle illisible",
                    f"{exc}\n\nUn modèle neuf a été reconstruit depuis les listes existantes.",
                    parent=self,
                )

        def current_category(self):
            cats = categories(self.model)
            if not cats:
                return None
            self.category_index = max(0, min(self.category_index, len(cats) - 1))
            return cats[self.category_index]

        def current_group(self):
            category = self.current_category()
            if category is None:
                return None
            groups = groups_of(category)
            if not groups:
                return None
            self.group_index = max(0, min(self.group_index, len(groups) - 1))
            return groups[self.group_index]

        def current_tile(self):
            group = self.current_group()
            if group is None:
                return None
            tiles = tiles_of(group)
            if not tiles:
                return None
            self.tile_index = max(0, min(self.tile_index, len(tiles) - 1))
            return tiles[self.tile_index]

        # -- rafraîchissement ----------------------------------------------
        def refresh_all(self):
            self.refresh_categories()
            self.refresh_groups()
            self.refresh_payloads()
            self.refresh_status()

        def refresh_categories(self):
            self._refreshing = True
            self.category_list.delete(0, "end")
            for category in categories(self.model):
                self.category_list.insert(
                    "end", f"{category.get('label', '?')}  ({tile_count(category)})"
                )
            self._refreshing = False
            if self.category_list.size():
                index = min(self.category_index, self.category_list.size() - 1)
                self.category_list.selection_clear(0, "end")
                self.category_list.selection_set(index)
                self.category_list.activate(index)
                self.category_index = index

        def refresh_groups(self):
            self._refreshing = True
            self.group_list.delete(0, "end")
            category = self.current_category()
            if category is not None:
                for group in groups_of(category):
                    self.group_list.insert(
                        "end", f"{group.get('label', '?')}  ({len(tiles_of(group))})"
                    )
            self._refreshing = False
            if self.group_list.size():
                index = min(self.group_index, self.group_list.size() - 1)
                self.group_list.selection_clear(0, "end")
                self.group_list.selection_set(index)
                self.group_list.activate(index)
                self.group_index = index
            else:
                self.group_index = 0

        def refresh_payloads(self):
            self._refreshing = True
            for item in self.payload_tree.get_children():
                self.payload_tree.delete(item)
            group = self.current_group()
            if group is not None:
                for index, tile in enumerate(tiles_of(group)):
                    self.payload_tree.insert(
                        "", "end", iid=str(index),
                        values=(
                            tile.get("title", ""),
                            tile.get("name", ""),
                            tile.get("desc", ""),
                            self._payload_state(tile.get("name", "")),
                        ),
                    )
            self._refreshing = False

            children = self.payload_tree.get_children()
            if children:
                index = min(self.tile_index, len(children) - 1)
                self.payload_tree.selection_set(children[index])
                self.payload_tree.focus(children[index])
                self.tile_index = index

        def _payload_state(self, name):
            if not name:
                return "vide"
            if not (self.paths.payloads / name).is_file():
                return "manquant"
            if not is_elf(self.paths.payloads, name):
                return "non-ELF"
            return "ok"

        def refresh_status(self):
            unused = [
                name for name in scan_elf_files(self.paths.payloads)
                if name not in {tile.get("name") for tile in all_tiles(self.model)}
            ]
            self.status_var.set(
                f"{len(categories(self.model))} liste(s) · {total_groups(self.model)} "
                f"sous-liste(s) · {total_payloads(self.model)} payload(s) · "
                f"{len(unused)} ELF non classé(s)"
            )

        def update_title(self):
            suffix = " *" if self.dirty else ""
            self.title(f"Éditeur de listes — PS5 Relapse{suffix}")

        def set_status(self, text):
            if hasattr(self, "status_var"):
                self.status_var.set(text)

        def touch(self):
            self.dirty = True
            self.update_title()
            self.refresh_all()

        # -- sélections -----------------------------------------------------
        def _on_category_select(self, _event=None):
            if self._refreshing:
                return
            selection = self.category_list.curselection()
            if not selection:
                return
            self.category_index = selection[0]
            self.group_index = 0
            self.tile_index = 0
            self.refresh_groups()
            self.refresh_payloads()

        def _on_group_select(self, _event=None):
            if self._refreshing:
                return
            selection = self.group_list.curselection()
            if not selection:
                return
            self.group_index = selection[0]
            self.tile_index = 0
            self.refresh_payloads()

        def _on_payload_select(self, _event=None):
            if self._refreshing:
                return
            selection = self.payload_tree.selection()
            if selection:
                try:
                    self.tile_index = int(selection[0])
                except ValueError:
                    pass

        # -- listes principales --------------------------------------------
        def add_category(self):
            label = simpledialog.askstring(
                "Nouvelle liste", "Nom de la liste principale :", parent=self
            )
            if not label or not label.strip():
                return
            label = label.strip()
            taken = {category.get("id") for category in categories(self.model)}
            categories(self.model).append({
                "id": unique_id(slugify(label, "liste"), taken),
                "label": label,
                "groups": [],
            })
            self.category_index = len(categories(self.model)) - 1
            self.group_index = 0
            self.tile_index = 0
            self.touch()

        def rename_category(self):
            category = self.current_category()
            if category is None:
                return
            label = simpledialog.askstring(
                "Renommer la liste", "Nom de la liste principale :",
                initialvalue=category.get("label", ""), parent=self,
            )
            if not label or not label.strip():
                return
            category["label"] = label.strip()
            self.touch()

        def delete_category(self):
            category = self.current_category()
            if category is None:
                return
            if not messagebox.askyesno(
                "Supprimer la liste",
                f"Supprimer « {category.get('label')} » et ses "
                f"{len(groups_of(category))} sous-liste(s) ?",
                parent=self,
            ):
                return
            categories(self.model).remove(category)
            self.category_index = max(0, self.category_index - 1)
            self.group_index = 0
            self.tile_index = 0
            self.touch()

        def move_category(self, delta):
            cats = categories(self.model)
            index = self.category_index
            target = index + delta
            if index < 0 or index >= len(cats) or target < 0 or target >= len(cats):
                return
            cats[index], cats[target] = cats[target], cats[index]
            self.category_index = target
            self.touch()

        # -- sous-listes ----------------------------------------------------
        def add_group(self):
            category = self.current_category()
            if category is None:
                messagebox.showinfo(
                    "Aucune liste", "Créez d'abord une liste principale.", parent=self
                )
                return
            label = simpledialog.askstring(
                "Nouvelle sous-liste", "Nom de la sous-liste :", parent=self
            )
            if not label or not label.strip():
                return
            label = label.strip()
            taken = {group.get("id") for group in groups_of(category)}
            groups_of(category).append({
                "id": unique_id(slugify(label, "groupe"), taken),
                "label": label,
                "tiles": [],
            })
            self.group_index = len(groups_of(category)) - 1
            self.tile_index = 0
            self.touch()

        def rename_group(self):
            group = self.current_group()
            if group is None:
                return
            label = simpledialog.askstring(
                "Renommer la sous-liste", "Nom de la sous-liste :",
                initialvalue=group.get("label", ""), parent=self,
            )
            if not label or not label.strip():
                return
            group["label"] = label.strip()
            self.touch()

        def delete_group(self):
            group = self.current_group()
            category = self.current_category()
            if group is None or category is None:
                return
            if not messagebox.askyesno(
                "Supprimer la sous-liste",
                f"Supprimer « {group.get('label')} » et ses "
                f"{len(tiles_of(group))} payload(s) ?",
                parent=self,
            ):
                return
            groups_of(category).remove(group)
            self.group_index = max(0, self.group_index - 1)
            self.tile_index = 0
            self.touch()

        def move_group(self, delta):
            category = self.current_category()
            if category is None:
                return
            groups = groups_of(category)
            index = self.group_index
            target = index + delta
            if index < 0 or index >= len(groups) or target < 0 or target >= len(groups):
                return
            groups[index], groups[target] = groups[target], groups[index]
            self.group_index = target
            self.touch()

        # -- payloads -------------------------------------------------------
        def add_payloads(self):
            group = self.current_group()
            if group is None:
                messagebox.showinfo(
                    "Aucune sous-liste",
                    "Sélectionnez ou créez une sous-liste avant d'ajouter des payloads.",
                    parent=self,
                )
                return
            files = scan_elf_files(self.paths.payloads)
            if not files:
                messagebox.showwarning(
                    "Dossier vide",
                    f"Aucun fichier .elf trouvé dans :\n{self.paths.payloads}",
                    parent=self,
                )
                return
            used = {tile.get("name") for tile in all_tiles(self.model)}
            dialog = PayloadPicker(self, files, used)
            self.wait_window(dialog)
            if not dialog.result:
                return
            tiles_of(group).extend(dialog.result)
            self.tile_index = max(0, len(tiles_of(group)) - len(dialog.result))
            self.touch()

        def add_unused_payloads(self):
            group = self.current_group()
            if group is None:
                messagebox.showinfo(
                    "Aucune sous-liste", "Sélectionnez une sous-liste.", parent=self
                )
                return
            listed = {tile.get("name") for tile in all_tiles(self.model)}
            extra = [name for name in scan_elf_files(self.paths.payloads) if name not in listed]
            if not extra:
                messagebox.showinfo(
                    "Rien à ajouter",
                    "Tous les fichiers .elf de payloads/ sont déjà classés.",
                    parent=self,
                )
                return
            preview = "\n".join(extra[:10]) + ("…" if len(extra) > 10 else "")
            if not messagebox.askyesno(
                "Ajouter les non classés",
                f"Ajouter {len(extra)} fichier(s) à « {group.get('label')} » ?\n\n{preview}",
                parent=self,
            ):
                return
            for name in extra:
                tiles_of(group).append(new_tile(Path(name).stem, name))
            self.touch()

        def edit_payload(self):
            tile = self.current_tile()
            if tile is None:
                return
            dialog = PayloadDialog(self, tile, scan_elf_files(self.paths.payloads))
            self.wait_window(dialog)
            if not dialog.result:
                return
            tile.update(dialog.result)
            self.touch()

        def delete_payload(self):
            group = self.current_group()
            tile = self.current_tile()
            if group is None or tile is None:
                return
            if not messagebox.askyesno(
                "Retirer le payload",
                f"Retirer « {tile.get('title')} » de cette sous-liste ?\n"
                "(le fichier .elf n'est pas supprimé)",
                parent=self,
            ):
                return
            tiles_of(group).remove(tile)
            self.tile_index = max(0, self.tile_index - 1)
            self.touch()

        def move_payload(self, delta):
            group = self.current_group()
            if group is None:
                return
            tiles = tiles_of(group)
            index = self.tile_index
            target = index + delta
            if index < 0 or index >= len(tiles) or target < 0 or target >= len(tiles):
                return
            tiles[index], tiles[target] = tiles[target], tiles[index]
            self.tile_index = target
            self.touch()

        # -- fichiers -------------------------------------------------------
        def save(self):
            problems = validate_model(self.model, self.paths.payloads)
            blocking = [p for p in problems if "non classé" not in p]
            if blocking or problems:
                text = "\n".join(problems[:12])
                if len(problems) > 12:
                    text += f"\n… et {len(problems) - 12} autre(s)"
                if not messagebox.askyesno(
                    "Vérification",
                    f"Points à vérifier :\n\n{text}\n\nEnregistrer quand même ?",
                    parent=self,
                ):
                    return
            try:
                write_outputs(self.model, self.paths)
            except OSError as exc:
                messagebox.showerror(
                    "Écriture impossible", f"{exc}", parent=self
                )
                return
            self.dirty = False
            self.update_title()
            self.refresh_status()
            self.set_status(
                f"Enregistré : {self.paths.js.name} + {self.paths.json.name} — "
                "rechargez la page Relapse."
            )

        def reload_model(self):
            if self.dirty and not messagebox.askyesno(
                "Recharger",
                "Des modifications ne sont pas enregistrées. Les perdre ?",
                parent=self,
            ):
                return
            self._load_initial_model()
            self.category_index = 0
            self.group_index = 0
            self.tile_index = 0
            self.dirty = False
            self.update_title()
            self.refresh_all()

        def verify(self):
            problems = validate_model(self.model, self.paths.payloads)
            if not problems:
                messagebox.showinfo(
                    "Vérification",
                    "Tout est cohérent : fichiers présents, ELF valides, "
                    "aucun fichier non classé.",
                    parent=self,
                )
                return
            messagebox.showwarning(
                "Vérification",
                "\n".join(problems[:20])
                + (f"\n… et {len(problems) - 20} autre(s)" if len(problems) > 20 else ""),
                parent=self,
            )

        def on_close(self):
            if self.dirty and not messagebox.askyesno(
                "Quitter",
                "Des modifications ne sont pas enregistrées. Quitter quand même ?",
                parent=self,
            ):
                return
            self.destroy()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def check_only(paths: Paths) -> int:
    try:
        model, origin = load_model(paths)
    except ModelError as exc:
        print(f"Modèle illisible : {exc}", file=sys.stderr)
        return 2

    print(f"Modèle : {origin}")
    for category in categories(model):
        print(f"  {category.get('label')} ({tile_count(category)} payloads)")
        for group in groups_of(category):
            print(f"    - {group.get('label')} : {len(tiles_of(group))}")
    print(f"Total : {total_groups(model)} sous-listes, {total_payloads(model)} payloads")

    problems = validate_model(model, paths.payloads)
    if problems:
        print("\nPoints à vérifier :")
        for problem in problems:
            print(f"  ! {problem}")
        return 1
    print("\nAucun problème détecté.")
    return 0


def sync_only(paths: Paths) -> int:
    try:
        model, origin = load_model(paths)
    except ModelError as exc:
        print(f"Modèle illisible : {exc}", file=sys.stderr)
        return 2
    write_outputs(model, paths)
    print(f"Modèle ({origin}) réécrit dans {paths.json.name} et {paths.js.name}.")
    return 0


def run_gui(paths: Paths) -> int:
    if tk is None:
        print(
            "Tkinter est introuvable dans cette installation Python.\n"
            "Installez Python depuis python.org (Tkinter est inclus) puis relancez.\n"
            f"Détail : {TK_ERROR}",
            file=sys.stderr,
        )
        return 2
    app = PayloadsEditor(paths)
    app.mainloop()
    return 0


def _configure_stdout() -> None:
    """Sortie UTF-8 : évite les accents cassés dans les consoles Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def main(argv=None) -> int:
    _configure_stdout()
    parser = argparse.ArgumentParser(
        description="Éditeur de listes de payloads pour PS5 Relapse."
    )
    parser.add_argument("--root", help="racine du projet (défaut : dossier du script)")
    parser.add_argument("--payloads", help="dossier des fichiers .elf")
    parser.add_argument("--json", help=f"modèle JSON (défaut : {DATA_JSON_NAME})")
    parser.add_argument("--js", help=f"fichier généré (défaut : {DATA_JS_NAME})")
    parser.add_argument("--check", action="store_true", help="vérifie les listes sans interface")
    parser.add_argument("--sync", action="store_true", help="réécrit les fichiers générés")
    args = parser.parse_args(argv)

    paths = resolve_paths(args)
    if args.check:
        return check_only(paths)
    if args.sync:
        return sync_only(paths)
    return run_gui(paths)


if __name__ == "__main__":
    sys.exit(main())
