from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional
import pandas as pd
import uvicorn
import json
import os
import io
from datetime import datetime

# PDF / Excel exports
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# http://localhost:8010

app = FastAPI()

DATA_FILE    = "tracker_data.json"
HISTORY_FILE = "tracker_history.json"
SNAPSHOT_FILE= "tracker_snapshots.json"
LOGO_PATH    = r"C:\Users\gdllguer\AppData\Roaming\JetBrains\PyCharmCE2024.2\scratches\Logo_Flex.jpg"

# ─────────────────────────────────────────────
# PERSISTENCE
# ─────────────────────────────────────────────
def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(tracker_db, f, indent=2)

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return None

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return []

def save_history(log):
    with open(HISTORY_FILE, "w") as f:
        json.dump(log, f, indent=2)

def load_snapshots():
    if os.path.exists(SNAPSHOT_FILE):
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return []

def save_snapshots(snaps):
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snaps, f, indent=2)

def take_daily_snapshot():
    """Save one efficiency snapshot per calendar day (idempotent)."""
    snaps = load_snapshots()
    today = datetime.now().strftime("%Y-%m-%d")
    if snaps and snaps[-1]["date"] == today:
        return
    items = tracker_db["items"]
    aps   = set(i["assembly_part_id"] for i in items)
    comp  = set(i["assembly_part_id"] for i in items if i["status"] == "Completado")
    eff   = round(len(comp)/len(aps)*100, 1) if aps else 0
    # WIP per process
    processes = list(dict.fromkeys(i["process"] for i in items))
    wip_by_proc = {}
    for p in processes:
        pi = [i for i in items if i["process"] == p]
        wip_by_proc[p] = sum(1 for i in pi if i["status"] in ("En Proceso","Sin Iniciar"))
    snaps.append({"date": today, "efficiency": eff, "wip": wip_by_proc})
    # keep last 90 days
    if len(snaps) > 90:
        snaps = snaps[-90:]
    save_snapshots(snaps)

# ─────────────────────────────────────────────
# LOGO
# ─────────────────────────────────────────────
@app.get("/logo")
def logo():
    return FileResponse(LOGO_PATH)

# ─────────────────────────────────────────────
# DATA MODEL
#
#   Client -> Project -> Assembly (el "ensamble", número de parte principal)
#                            -> AssemblyPart (línea de BOM: une un Ensamble
#                               con una Parte del catálogo global + su cantidad)
#                               -> Items (pasos de proceso, atados a esa línea)
#
#   "parts" es un catálogo GLOBAL: la misma parte (mismo part_number) puede
#   asignarse a varios ensambles / proyectos distintos (piezas comunes), y
#   cada asignación (AssemblyPart) da seguimiento independiente a su avance.
# ─────────────────────────────────────────────
tracker_db = {
    "items": [], "clients": [], "projects": [],
    "assemblies": [], "parts": [], "assembly_parts": [], "processes": [],
}

def next_id(collection):
    return max([x["id"] for x in collection], default=0) + 1

def init_data():
    tracker_db["clients"] = [
        {"id": 1, "name": "Cliente General", "contact": "", "notes": "", "active": True},
    ]
    tracker_db["projects"] = [
        {"id": 1, "client_id": 1, "name": "Proyecto General", "notes": "", "active": True},
    ]
    tracker_db["processes"] = [
        {"id": 1, "name": "Punzonado", "active": True},
        {"id": 2, "name": "Doblado",   "active": True},
        {"id": 3, "name": "Insercion", "active": True},
    ]
    tracker_db["assemblies"] = [
        {"id": 1, "project_id": 1, "part_number": "ENS-1000", "description": "Ensamble Principal",
         "qty_ordered": 10, "active": True},
        {"id": 2, "project_id": 1, "part_number": "ENS-2000", "description": "Ensamble Secundario",
         "qty_ordered": 5, "active": True},
    ]
    tracker_db["parts"] = [
        {"id": 1, "part_number": "M1320502-001", "description": "Bracket A", "image": None, "active": True},
        {"id": 2, "part_number": "M1320509-001", "description": "Bracket B", "image": None, "active": True},
        {"id": 3, "part_number": "M1320515-001", "description": "Bracket C", "image": None, "active": True},
    ]
    tracker_db["assembly_parts"] = [
        # Bracket A se reutiliza en los DOS ensambles — ejemplo de parte común.
        {"id": 1, "assembly_id": 1, "part_id": 1, "qty_ordered": 100, "active": True},
        {"id": 2, "assembly_id": 1, "part_id": 2, "qty_ordered": 120, "active": True},
        {"id": 3, "assembly_id": 2, "part_id": 1, "qty_ordered": 50,  "active": True},
        {"id": 4, "assembly_id": 2, "part_id": 3, "qty_ordered": 80,  "active": True},
    ]
    tracker_db["items"] = []
    idc = 1
    proj_by_id = {p["id"]: p for p in tracker_db["projects"]}
    asm_by_id  = {a["id"]: a for a in tracker_db["assemblies"]}
    part_by_id = {p["id"]: p for p in tracker_db["parts"]}
    for ap in tracker_db["assembly_parts"]:
        asm  = asm_by_id[ap["assembly_id"]]
        part = part_by_id[ap["part_id"]]
        proj = proj_by_id[asm["project_id"]]
        for seq, proc in enumerate(tracker_db["processes"], 1):
            tracker_db["items"].append({
                "id": idc, "assembly_part_id": ap["id"], "assembly_id": asm["id"], "part_id": part["id"],
                "client_id": proj["client_id"], "project_id": proj["id"], "process_id": proc["id"],
                "assembly_number": asm["part_number"], "part_number": part["part_number"],
                "description": part["description"], "process": proc["name"], "seq": seq,
                "priority": idc,
                "planned_start": "", "planned_end": "",
                "actual_start":  "", "actual_end":   "",
                "qty_ordered": ap["qty_ordered"], "qty_completed": 0,
                "status": "Sin Iniciar", "notes": "",
                "cycle_time_min": None,
            })
            idc += 1

def migrate_flat_to_relational():
    """One-time upgrade of very old flat item data (no client/project/assembly split
    at all) directly into the client/project/assembly/part model."""
    if tracker_db.get("clients"):
        return False
    items = tracker_db["items"]
    client  = {"id": 1, "name": "Cliente General", "contact": "", "notes": "", "active": True}
    project = {"id": 1, "client_id": 1, "name": "Proyecto General", "notes": "", "active": True}
    tracker_db["clients"]  = [client]
    tracker_db["projects"] = [project]

    proc_by_name = {}
    processes = []
    for it in items:
        name = it.get("process", "")
        if name and name not in proc_by_name:
            p = {"id": len(processes) + 1, "name": name, "active": True}
            proc_by_name[name] = p
            processes.append(p)
    tracker_db["processes"] = processes

    assemblies, parts, assembly_parts = [], [], []
    asm_by_pn = {}
    for it in items:
        pn = it.get("part_number", "")
        if pn and pn not in asm_by_pn:
            asm = {"id": len(assemblies) + 1, "project_id": 1, "part_number": pn,
                   "description": it.get("description", ""),
                   "qty_ordered": it.get("qty_ordered", 0), "active": True}
            part = {"id": len(parts) + 1, "part_number": pn,
                    "description": it.get("description", ""), "image": None, "active": True}
            ap = {"id": len(assembly_parts) + 1, "assembly_id": asm["id"], "part_id": part["id"],
                  "qty_ordered": it.get("qty_ordered", 0), "active": True}
            asm_by_pn[pn] = (asm, part, ap)
            assemblies.append(asm); parts.append(part); assembly_parts.append(ap)
    tracker_db["assemblies"]     = assemblies
    tracker_db["parts"]          = parts
    tracker_db["assembly_parts"] = assembly_parts

    for it in items:
        it["client_id"]  = 1
        it["project_id"] = 1
        triple = asm_by_pn.get(it.get("part_number"))
        if triple:
            asm, part, ap = triple
            it["assembly_id"]      = asm["id"]
            it["part_id"]          = part["id"]
            it["assembly_part_id"] = ap["id"]
            it["assembly_number"]  = asm["part_number"]
        proc = proc_by_name.get(it.get("process"))
        it["process_id"] = proc["id"] if proc else None
    return True

def migrate_parts_to_assemblies(loaded_keys):
    """One-time upgrade of the previous relational model — where 'parts' were
    project-scoped tracked items — into the assembly / global-part-catalog model.
    Old parts become assemblies; identical part_numbers across projects merge
    into a single reusable catalog entry (assembly_parts links them back).
    `loaded_keys` is the key set of the raw JSON that was actually on disk —
    tracker_db itself always has an "assembly_parts" key (pre-seeded as [] at
    module load), so checking membership on tracker_db would never detect an
    old-format file."""
    if "assembly_parts" in loaded_keys:
        return False
    tracker_db["assemblies"] = tracker_db.get("parts", [])

    parts, part_by_pn = [], {}
    assembly_parts, ap_by_assembly_id = [], {}
    for asm in tracker_db["assemblies"]:
        pn = asm["part_number"]
        part = part_by_pn.get(pn)
        if not part:
            part = {"id": len(parts) + 1, "part_number": pn,
                    "description": asm.get("description", ""), "image": None, "active": True}
            part_by_pn[pn] = part
            parts.append(part)
        ap = {"id": len(assembly_parts) + 1, "assembly_id": asm["id"], "part_id": part["id"],
              "qty_ordered": asm.get("qty_ordered", 0), "active": True}
        assembly_parts.append(ap)
        ap_by_assembly_id[asm["id"]] = ap

    tracker_db["parts"]          = parts
    tracker_db["assembly_parts"] = assembly_parts

    asm_by_id = {a["id"]: a for a in tracker_db["assemblies"]}
    for it in tracker_db["items"]:
        old_pid = it.get("part_id")   # used to point at the "parts" collection (now assemblies)
        asm = asm_by_id.get(old_pid)
        ap  = ap_by_assembly_id.get(old_pid)
        it["assembly_id"]      = old_pid
        it["assembly_part_id"] = ap["id"] if ap else None
        it["part_id"]          = part_by_pn[asm["part_number"]]["id"] if asm else it.get("part_id")
        it["assembly_number"]  = asm["part_number"] if asm else it.get("part_number", "")
    return True

loaded = load_data()
if loaded:
    # migrate older records that lack new fields
    for it in loaded.get("items", []):
        it.setdefault("actual_start",   "")
        it.setdefault("actual_end",     "")
        it.setdefault("cycle_time_min", None)
        it.setdefault("priority", it.get("id"))
    for pt in loaded.get("parts", []):
        pt.setdefault("image", None)
    tracker_db.update(loaded)
    # backfill "seq" for legacy records that predate this field
    by_part = {}
    for it in tracker_db["items"]:
        by_part.setdefault(it.get("part_number", ""), []).append(it)
    for pn, steps in by_part.items():
        if any("seq" not in s for s in steps):
            steps_sorted = sorted(steps, key=lambda x: x["id"])
            for i, s in enumerate(steps_sorted, 1):
                s["seq"] = i
    loaded_had_clients = bool(loaded.get("clients"))
    migrated = migrate_flat_to_relational()
    # only the very-old flat format lacked "clients" entirely; anything else
    # that predates the assembly split is judged by what was actually on disk
    if loaded_had_clients and migrate_parts_to_assemblies(loaded.keys()):
        migrated = True
    if migrated:
        save_data()
else:
    init_data()
    save_data()

# ─────────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────────
class UpdateStepModel(BaseModel):
    id:            int
    planned_start: str = ""
    planned_end:   str = ""
    actual_start:  str = ""
    actual_end:    str = ""
    qty_completed: int
    status:        str
    notes:         Optional[str] = ""
    reopen_note:   Optional[str] = ""   # required when reopening a Completado item

class BulkUpdateModel(BaseModel):
    ids:    list[int]
    status: str
    reopen_note: Optional[str] = ""

class ReorderModel(BaseModel):
    assembly_part_id: int
    ordered_ids: list[int]   # process item ids in new desired sequence

class PriorityReorderModel(BaseModel):
    ordered_ids: list[int]   # item ids, in the new desired display order within a process section

class ClientModel(BaseModel):
    name:    str
    contact: Optional[str] = ""
    notes:   Optional[str] = ""

class ProjectModel(BaseModel):
    client_id: int
    name:      str
    notes:     Optional[str] = ""

class AssemblyModel(BaseModel):
    project_id:   int
    part_number:  str
    description:  Optional[str] = ""
    qty_ordered:  int

class PartModel(BaseModel):
    part_number:  str
    description:  Optional[str] = ""

class PartImageModel(BaseModel):
    image: Optional[str] = None   # base64 data URI (e.g. "data:image/jpeg;base64,...") or null to remove

class AssemblyPartModel(BaseModel):
    part_id:      int
    qty_ordered:  int

class AssemblyPartQtyModel(BaseModel):
    qty_ordered:  int

class ProcessModel(BaseModel):
    name: str

class StepModel(BaseModel):
    process_id: int

# ─────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────
@app.put("/api/update")
def update(data: UpdateStepModel):
    history = load_history()

    for item in tracker_db["items"]:
        if item["id"] != data.id:
            continue

        # ── #3: require note when reopening a completed item ──
        if item["status"] == "Completado" and data.status != "Completado":
            if not (data.reopen_note or "").strip():
                raise HTTPException(
                    status_code=400,
                    detail="REOPEN_NOTE_REQUIRED"
                )
            # log the reopen reason in notes
            data.notes = f"[REABIERTO: {data.reopen_note.strip()}] " + (data.notes or "")

        # ── sequence lock (steps of the SAME assembly+part usage) ──
        steps = sorted(
            [i for i in tracker_db["items"] if i["assembly_part_id"] == item["assembly_part_id"]],
            key=lambda x: x.get("seq", x["id"])
        )
        current_index = next((i for i, s in enumerate(steps) if s["id"] == item["id"]), None)

        if data.status == "En Proceso" and current_index and current_index > 0:
            if steps[current_index - 1]["status"] != "Completado":
                raise HTTPException(status_code=400, detail="Proceso anterior no completado")

        # ── auto actual_start when first moved to En Proceso ──
        new_actual_start = data.actual_start
        if data.status == "En Proceso" and not item.get("actual_start"):
            new_actual_start = datetime.now().strftime("%Y-%m-%dT%H:%M")

        # ── auto actual_end + cycle time when completed ────
        new_actual_end   = data.actual_end
        new_cycle_time   = item.get("cycle_time_min")
        if data.qty_completed >= item["qty_ordered"] or data.status == "Completado":
            if not item.get("actual_end"):
                new_actual_end = datetime.now().strftime("%Y-%m-%dT%H:%M")
            # calc cycle time in minutes
            start_str = new_actual_start or item.get("actual_start", "")
            if start_str and new_actual_end:
                try:
                    t0 = datetime.fromisoformat(start_str)
                    t1 = datetime.fromisoformat(new_actual_end)
                    new_cycle_time = round((t1 - t0).total_seconds() / 60, 1)
                except Exception:
                    pass

        # ── audit log ──────────────────────────────────────
        old_status = item["status"]
        old_qty    = item["qty_completed"]
        history.append({
            "ts":              datetime.now().isoformat(timespec="seconds"),
            "id":              item["id"],
            "assembly_number": item.get("assembly_number", ""),
            "part_number":     item["part_number"],
            "process":         item["process"],
            "old_status":      old_status,
            "new_status":      data.status,
            "old_qty":         old_qty,
            "new_qty":         data.qty_completed,
        })
        # keep last 2000 entries
        if len(history) > 2000:
            history = history[-2000:]

        # ── apply update ───────────────────────────────────
        item.update({
            "planned_start":  data.planned_start,
            "planned_end":    data.planned_end,
            "actual_start":   new_actual_start,
            "actual_end":     new_actual_end,
            "qty_completed":  data.qty_completed,
            "status":         data.status,
            "notes":          data.notes,
            "cycle_time_min": new_cycle_time,
        })

        # ── auto-complete + unlock next (same assembly+part usage) ─────
        if item["qty_completed"] >= item["qty_ordered"]:
            item["status"] = "Completado"
            steps2 = sorted(
                [i for i in tracker_db["items"] if i["assembly_part_id"] == item["assembly_part_id"]],
                key=lambda x: x.get("seq", x["id"])
            )
            for idx, step in enumerate(steps2):
                if step["id"] == item["id"] and idx + 1 < len(steps2):
                    nxt = steps2[idx + 1]
                    if nxt["status"] == "Sin Iniciar":
                        nxt["status"] = "En Proceso"
                        nxt["actual_start"] = datetime.now().strftime("%Y-%m-%dT%H:%M")
                    break

        save_data()
        save_history(history)
        take_daily_snapshot()
        return {"ok": True}

    raise HTTPException(status_code=404)

# ─────────────────────────────────────────────
# EXCEL UPLOAD
# ─────────────────────────────────────────────
def _find_or_create_client(name):
    name = (name or "").strip() or "Cliente General"
    for c in tracker_db["clients"]:
        if c["name"].lower() == name.lower():
            return c
    c = {"id": next_id(tracker_db["clients"]), "name": name, "contact": "", "notes": "", "active": True}
    tracker_db["clients"].append(c)
    return c

def _find_or_create_project(client_id, name):
    name = (name or "").strip() or "Proyecto General"
    for p in tracker_db["projects"]:
        if p["client_id"] == client_id and p["name"].lower() == name.lower():
            return p
    p = {"id": next_id(tracker_db["projects"]), "client_id": client_id, "name": name, "notes": "", "active": True}
    tracker_db["projects"].append(p)
    return p

def _find_or_create_assembly(project_id, part_number, description, qty_ordered):
    part_number = (part_number or "").strip() or "ENSAMBLE-GENERAL"
    for a in tracker_db["assemblies"]:
        if a["project_id"] == project_id and a["part_number"].lower() == part_number.lower():
            return a
    a = {"id": next_id(tracker_db["assemblies"]), "project_id": project_id, "part_number": part_number,
         "description": description or "", "qty_ordered": qty_ordered or 0, "active": True}
    tracker_db["assemblies"].append(a)
    return a

def _find_or_create_part(part_number, description):
    """Parts are a global, reusable catalog — the same part_number can be shared
    across assemblies and projects (piezas comunes)."""
    for p in tracker_db["parts"]:
        if p["part_number"].lower() == part_number.lower():
            if description and not p.get("description"):
                p["description"] = description
            return p
    p = {"id": next_id(tracker_db["parts"]), "part_number": part_number,
         "description": description or "", "image": None, "active": True}
    tracker_db["parts"].append(p)
    return p

def _find_or_create_assembly_part(assembly_id, part_id, qty_ordered):
    for ap in tracker_db["assembly_parts"]:
        if ap["assembly_id"] == assembly_id and ap["part_id"] == part_id:
            return ap
    ap = {"id": next_id(tracker_db["assembly_parts"]), "assembly_id": assembly_id, "part_id": part_id,
          "qty_ordered": qty_ordered, "active": True}
    tracker_db["assembly_parts"].append(ap)
    return ap

def _find_or_create_process(name):
    for pr in tracker_db["processes"]:
        if pr["name"].lower() == name.lower():
            return pr
    pr = {"id": next_id(tracker_db["processes"]), "name": name, "active": True}
    tracker_db["processes"].append(pr)
    return pr

@app.post("/upload")
def upload(file: UploadFile = File(...)):
    try:
        content = file.file.read()
        raw = pd.read_excel(io.BytesIO(content), header=None)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo Excel: {exc}")

    # the exported /export/template file has a title + instructions row before
    # the real header row, so find whichever row actually has "Assembly_Number"
    # instead of always assuming row 1 — works for that template and for a
    # plain sheet with headers already on row 1.
    header_row_idx = None
    for i in range(min(10, len(raw))):
        if raw.iloc[i].astype(str).str.strip().eq("Assembly_Number").any():
            header_row_idx = i
            break
    if header_row_idx is None:
        raise HTTPException(status_code=400,
            detail="No se encontró la fila de encabezados (debe incluir 'Assembly_Number') "
                   "en las primeras filas del archivo.")

    try:
        df = pd.read_excel(io.BytesIO(content), header=header_row_idx)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo leer el archivo Excel: {exc}")

    required_cols = ["Assembly_Number", "Part_Number", "Process", "Sequence", "Qty"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    if missing_cols:
        raise HTTPException(status_code=400,
            detail="Faltan columnas obligatorias en el Excel: " + ", ".join(missing_cols))

    # drop leftover blank template rows (Assembly_Number/Part_Number/Process empty)
    df = df.dropna(subset=["Assembly_Number", "Part_Number", "Process"], how="any")
    if df.empty:
        raise HTTPException(status_code=400,
            detail="El archivo no tiene filas con datos (Assembly_Number, Part_Number y Process vacíos en todas las filas).")

    # ── validate every row BEFORE touching any existing data, so a bad file
    #    never leaves the app with partially-cleared/partially-loaded data ──
    for idx, row in df.iterrows():
        excel_row = idx + 2  # +2: Excel header is row 1, pandas index is 0-based
        pn = row.get("Part_Number")
        if pd.isna(row.get("Qty")):
            raise HTTPException(status_code=400,
                detail=f"Fila {excel_row}: falta la cantidad (Qty) para la parte '{pn}'.")
        try:
            int(row["Qty"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400,
                detail=f"Fila {excel_row}: la cantidad (Qty) '{row['Qty']}' no es un número válido para la parte '{pn}'.")
        if pd.isna(row.get("Sequence")):
            raise HTTPException(status_code=400,
                detail=f"Fila {excel_row}: falta la secuencia (Sequence) para la parte '{pn}'.")
        try:
            int(row["Sequence"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400,
                detail=f"Fila {excel_row}: la secuencia (Sequence) '{row['Sequence']}' no es un número válido para la parte '{pn}'.")
        if "Assembly_Qty" in df.columns and pd.notna(row.get("Assembly_Qty")):
            try:
                int(row["Assembly_Qty"])
            except (ValueError, TypeError):
                raise HTTPException(status_code=400,
                    detail=f"Fila {excel_row}: la cantidad del ensamble (Assembly_Qty) '{row['Assembly_Qty']}' no es un número válido.")

    tracker_db["items"].clear()
    tracker_db["assembly_parts"].clear()
    tracker_db["assemblies"].clear()
    idc = 1
    touched_assemblies, touched_parts, n_steps = set(), set(), 0
    for (asm_num, part_num), group in df.groupby(["Assembly_Number", "Part_Number"]):
        group = group.sort_values("Sequence")
        first = group.iloc[0]
        client   = _find_or_create_client(str(first.get("Client", "")) if "Client" in df.columns else "")
        project  = _find_or_create_project(client["id"], str(first.get("Project", "")) if "Project" in df.columns else "")
        assembly = _find_or_create_assembly(
            project["id"], str(asm_num),
            str(first.get("Assembly_Description", "")) if "Assembly_Description" in df.columns else "",
            int(first["Assembly_Qty"]) if "Assembly_Qty" in df.columns and pd.notna(first.get("Assembly_Qty")) else 0,
        )
        part = _find_or_create_part(str(part_num), str(first.get("Description", "")))
        ap   = _find_or_create_assembly_part(assembly["id"], part["id"], int(first["Qty"]))
        touched_assemblies.add(assembly["id"])
        touched_parts.add(part["id"])
        for seq, (_, row) in enumerate(group.iterrows(), 1):
            proc = _find_or_create_process(str(row["Process"]))
            tracker_db["items"].append({
                "id": idc, "assembly_part_id": ap["id"], "assembly_id": assembly["id"], "part_id": part["id"],
                "client_id": client["id"], "project_id": project["id"], "process_id": proc["id"],
                "assembly_number": assembly["part_number"], "part_number": part["part_number"],
                "description":    part["description"],
                "process":        str(row["Process"]),
                "seq":            seq,
                "priority":       idc,
                "planned_start":  "", "planned_end":  "",
                "actual_start":   "", "actual_end":   "",
                "qty_ordered":    int(row["Qty"]),
                "qty_completed":  0,
                "status":         "Sin Iniciar",
                "notes":          "",
                "cycle_time_min": None,
            })
            idc += 1
            n_steps += 1
    save_data()
    return {"ok": True, "assemblies": len(touched_assemblies), "parts": len(touched_parts), "steps": n_steps}

# ─────────────────────────────────────────────
# DATA API
# ─────────────────────────────────────────────
@app.get("/api/data")
def api_data():
    items     = tracker_db["items"]
    processes = list(dict.fromkeys(i["process"] for i in items))
    aps       = set(i["assembly_part_id"] for i in items)
    completed = set(i["assembly_part_id"] for i in items if i["status"] == "Completado")

    # cycle time averages per process
    ct_by_proc = {}
    for p in processes:
        times = [i["cycle_time_min"] for i in items
                 if i["process"] == p and i["cycle_time_min"] is not None]
        ct_by_proc[p] = round(sum(times)/len(times), 1) if times else None

    # part progress (% of processes completed), keyed by assembly_part_id since
    # the same part_number can be tracked independently in several assemblies
    part_progress = {}
    for ap in aps:
        pi   = [i for i in items if i["assembly_part_id"] == ap]
        done = sum(1 for i in pi if i["status"] == "Completado")
        part_progress[ap] = round(done / len(pi) * 100, 1) if pi else 0

    return {
        "kpis": {
            "total":      len(aps),
            "completed":  len(completed),
            "efficiency": round(len(completed)/len(aps)*100, 1) if aps else 0,
        },
        "items":            items,
        "processes":        processes,
        "ct_by_proc":       ct_by_proc,
        "part_progress":    part_progress,
        "snapshots":        load_snapshots(),
        "clients":          tracker_db["clients"],
        "projects":         tracker_db["projects"],
        "assemblies":       tracker_db["assemblies"],
        "parts":            tracker_db["parts"],
        "assembly_parts":   tracker_db["assembly_parts"],
        "process_catalog":  tracker_db["processes"],
    }

# ─────────────────────────────────────────────
# BOTTLENECK ALERT CHECK
# ─────────────────────────────────────────────
ALERT_THRESHOLD_HOURS = 4   # flag if En Proceso for longer than this

@app.get("/api/alerts")
def api_alerts():
    alerts = []
    now = datetime.now()
    for item in tracker_db["items"]:
        if item["status"] == "En Proceso" and item.get("actual_start"):
            try:
                t0    = datetime.fromisoformat(item["actual_start"])
                hours = (now - t0).total_seconds() / 3600
                if hours >= ALERT_THRESHOLD_HOURS:
                    alerts.append({
                        "id":              item["id"],
                        "assembly_number": item.get("assembly_number", ""),
                        "part_number":     item["part_number"],
                        "process":         item["process"],
                        "hours":           round(hours, 1),
                    })
            except Exception:
                pass
    return {"alerts": alerts}

# ─────────────────────────────────────────────
# BULK UPDATE  (#2)
# ─────────────────────────────────────────────
@app.put("/api/bulk-update")
def bulk_update(data: BulkUpdateModel):
    history  = load_history()
    now_str  = datetime.now().strftime("%Y-%m-%dT%H:%M")
    now_iso  = datetime.now().isoformat(timespec="seconds")
    updated  = 0

    for item in tracker_db["items"]:
        if item["id"] not in data.ids:
            continue

        # reopen note check
        if item["status"] == "Completado" and data.status != "Completado":
            if not (data.reopen_note or "").strip():
                raise HTTPException(status_code=400, detail="REOPEN_NOTE_REQUIRED")
            prefix = f"[REABIERTO: {data.reopen_note.strip()}] "
            item["notes"] = prefix + (item.get("notes") or "")

        # sequence lock (steps of the same assembly+part usage)
        steps = sorted(
            [i for i in tracker_db["items"] if i["assembly_part_id"] == item["assembly_part_id"]],
            key=lambda x: x.get("seq", x["id"])
        )
        curr_idx = next((i for i, s in enumerate(steps) if s["id"] == item["id"]), None)
        if data.status == "En Proceso" and curr_idx and curr_idx > 0:
            if steps[curr_idx - 1]["status"] != "Completado":
                continue  # skip ineligible items silently

        history.append({
            "ts": now_iso, "id": item["id"],
            "assembly_number": item.get("assembly_number", ""),
            "part_number": item["part_number"], "process": item["process"],
            "old_status": item["status"], "new_status": data.status,
            "old_qty": item["qty_completed"], "new_qty": item["qty_completed"],
        })

        item["status"] = data.status

        if data.status == "En Proceso" and not item.get("actual_start"):
            item["actual_start"] = now_str
        if data.status == "Completado":
            item["qty_completed"] = item["qty_ordered"]
            if not item.get("actual_end"):
                item["actual_end"] = now_str
            if item.get("actual_start"):
                try:
                    t0 = datetime.fromisoformat(item["actual_start"])
                    t1 = datetime.fromisoformat(now_str)
                    item["cycle_time_min"] = round((t1 - t0).total_seconds() / 60, 1)
                except Exception:
                    pass
            for idx, step in enumerate(steps):
                if step["id"] == item["id"] and idx + 1 < len(steps):
                    nxt = steps[idx + 1]
                    if nxt["status"] == "Sin Iniciar":
                        nxt["status"]       = "En Proceso"
                        nxt["actual_start"] = now_str
                    break

        updated += 1

    if len(history) > 2000:
        history = history[-2000:]

    save_data()
    save_history(history)
    take_daily_snapshot()
    return {"ok": True, "updated": updated}

# ─────────────────────────────────────────────
# REORDER PROCESSES  (#1)
# ─────────────────────────────────────────────
@app.put("/api/reorder")
def reorder(data: ReorderModel):
    steps  = [i for i in tracker_db["items"] if i["assembly_part_id"] == data.assembly_part_id]
    id_set = {s["id"] for s in steps}
    if set(data.ordered_ids) != id_set:
        raise HTTPException(status_code=400, detail="ordered_ids mismatch")
    for new_seq, item_id in enumerate(data.ordered_ids, 1):
        for item in steps:
            if item["id"] == item_id:
                item["seq"] = new_seq
                break
    save_data()
    return {"ok": True}

# ─────────────────────────────────────────────
# REORDER ROWS WITHIN A PROCESS SECTION (display/work priority — independent
# of "seq", which only gates when the next manufacturing step can start)
# ─────────────────────────────────────────────
@app.put("/api/reorder-priority")
def reorder_priority(data: PriorityReorderModel):
    by_id = {i["id"]: i for i in tracker_db["items"]}
    missing = [iid for iid in data.ordered_ids if iid not in by_id]
    if missing:
        raise HTTPException(status_code=400, detail=f"ids inválidos: {missing}")
    for pr, item_id in enumerate(data.ordered_ids, 1):
        by_id[item_id]["priority"] = pr
    save_data()
    return {"ok": True}

# ─────────────────────────────────────────────
# CATALOG HELPERS  (clients / projects / assemblies / parts / assembly_parts / processes)
# ─────────────────────────────────────────────
def find_or_404(collection, id_, label):
    for x in collection:
        if x["id"] == id_:
            return x
    raise HTTPException(status_code=404, detail=f"{label} no encontrado")

def sync_part_to_items(part):
    for it in tracker_db["items"]:
        if it.get("part_id") == part["id"]:
            it["part_number"] = part["part_number"]
            it["description"] = part["description"]

def sync_assembly_to_items(assembly):
    for it in tracker_db["items"]:
        if it.get("assembly_id") == assembly["id"]:
            it["assembly_number"] = assembly["part_number"]

def sync_process_to_items(process):
    for it in tracker_db["items"]:
        if it.get("process_id") == process["id"]:
            it["process"] = process["name"]

def sync_project_to_items(project_id, client_id):
    for it in tracker_db["items"]:
        if it.get("project_id") == project_id:
            it["client_id"] = client_id

def sync_assembly_part_qty_to_items(assembly_part):
    for it in tracker_db["items"]:
        if it.get("assembly_part_id") == assembly_part["id"]:
            it["qty_ordered"] = assembly_part["qty_ordered"]

def client_dependents(cid):
    projects   = [p for p in tracker_db["projects"] if p["client_id"] == cid]
    proj_ids   = {p["id"] for p in projects}
    assemblies = [a for a in tracker_db["assemblies"] if a["project_id"] in proj_ids]
    asm_ids    = {a["id"] for a in assemblies}
    aparts     = [ap for ap in tracker_db["assembly_parts"] if ap["assembly_id"] in asm_ids]
    ap_ids     = {ap["id"] for ap in aparts}
    items      = [i for i in tracker_db["items"] if i.get("assembly_part_id") in ap_ids]
    return {"proyectos": len(projects), "ensambles": len(assemblies),
            "partes_asignadas": len(aparts), "pasos": len(items)}

def project_dependents(pid):
    assemblies = [a for a in tracker_db["assemblies"] if a["project_id"] == pid]
    asm_ids    = {a["id"] for a in assemblies}
    aparts     = [ap for ap in tracker_db["assembly_parts"] if ap["assembly_id"] in asm_ids]
    ap_ids     = {ap["id"] for ap in aparts}
    items      = [i for i in tracker_db["items"] if i.get("assembly_part_id") in ap_ids]
    return {"ensambles": len(assemblies), "partes_asignadas": len(aparts), "pasos": len(items)}

def assembly_dependents(aid):
    aparts = [ap for ap in tracker_db["assembly_parts"] if ap["assembly_id"] == aid]
    ap_ids = {ap["id"] for ap in aparts}
    items  = [i for i in tracker_db["items"] if i.get("assembly_part_id") in ap_ids]
    return {"partes_asignadas": len(aparts), "pasos": len(items)}

def part_dependents(pid):
    """pid = id de la parte GLOBAL. Cuenta en cuántos ensambles distintos está asignada."""
    aparts = [ap for ap in tracker_db["assembly_parts"] if ap["part_id"] == pid]
    ap_ids = {ap["id"] for ap in aparts}
    items  = [i for i in tracker_db["items"] if i.get("assembly_part_id") in ap_ids]
    return {"ensambles_que_la_usan": len(aparts), "pasos": len(items)}

def assembly_part_dependents(apid):
    items = [i for i in tracker_db["items"] if i.get("assembly_part_id") == apid]
    return {"pasos": len(items)}

def process_dependents(pid):
    items = [i for i in tracker_db["items"] if i.get("process_id") == pid]
    return {"pasos": len(items)}

# ── CLIENTS ──
@app.post("/api/clients")
def create_client(data: ClientModel):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    c = {"id": next_id(tracker_db["clients"]), "name": name,
         "contact": data.contact or "", "notes": data.notes or "", "active": True}
    tracker_db["clients"].append(c)
    save_data()
    return c

@app.put("/api/clients/{cid}")
def update_client(cid: int, data: ClientModel):
    c = find_or_404(tracker_db["clients"], cid, "Cliente")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    c.update({"name": name, "contact": data.contact or "", "notes": data.notes or ""})
    save_data()
    return c

@app.delete("/api/clients/{cid}")
def delete_client(cid: int, force: bool = False):
    find_or_404(tracker_db["clients"], cid, "Cliente")
    dep = client_dependents(cid)
    if any(dep.values()) and not force:
        raise HTTPException(status_code=409, detail={"dependents": dep})
    proj_ids = {p["id"] for p in tracker_db["projects"] if p["client_id"] == cid}
    asm_ids  = {a["id"] for a in tracker_db["assemblies"] if a["project_id"] in proj_ids}
    ap_ids   = {ap["id"] for ap in tracker_db["assembly_parts"] if ap["assembly_id"] in asm_ids}
    tracker_db["items"]          = [i for i in tracker_db["items"] if i.get("assembly_part_id") not in ap_ids]
    tracker_db["assembly_parts"] = [ap for ap in tracker_db["assembly_parts"] if ap["id"] not in ap_ids]
    tracker_db["assemblies"]     = [a for a in tracker_db["assemblies"] if a["id"] not in asm_ids]
    tracker_db["projects"]       = [p for p in tracker_db["projects"] if p["id"] not in proj_ids]
    tracker_db["clients"]        = [c for c in tracker_db["clients"] if c["id"] != cid]
    save_data()
    return {"ok": True}

# ── PROJECTS ──
@app.post("/api/projects")
def create_project(data: ProjectModel):
    find_or_404(tracker_db["clients"], data.client_id, "Cliente")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    p = {"id": next_id(tracker_db["projects"]), "client_id": data.client_id,
         "name": name, "notes": data.notes or "", "active": True}
    tracker_db["projects"].append(p)
    save_data()
    return p

@app.put("/api/projects/{pid}")
def update_project(pid: int, data: ProjectModel):
    p = find_or_404(tracker_db["projects"], pid, "Proyecto")
    find_or_404(tracker_db["clients"], data.client_id, "Cliente")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    p.update({"client_id": data.client_id, "name": name, "notes": data.notes or ""})
    sync_project_to_items(pid, data.client_id)
    save_data()
    return p

@app.delete("/api/projects/{pid}")
def delete_project(pid: int, force: bool = False):
    find_or_404(tracker_db["projects"], pid, "Proyecto")
    dep = project_dependents(pid)
    if any(dep.values()) and not force:
        raise HTTPException(status_code=409, detail={"dependents": dep})
    asm_ids = {a["id"] for a in tracker_db["assemblies"] if a["project_id"] == pid}
    ap_ids  = {ap["id"] for ap in tracker_db["assembly_parts"] if ap["assembly_id"] in asm_ids}
    tracker_db["items"]          = [i for i in tracker_db["items"] if i.get("assembly_part_id") not in ap_ids]
    tracker_db["assembly_parts"] = [ap for ap in tracker_db["assembly_parts"] if ap["id"] not in ap_ids]
    tracker_db["assemblies"]     = [a for a in tracker_db["assemblies"] if a["id"] not in asm_ids]
    tracker_db["projects"]       = [p for p in tracker_db["projects"] if p["id"] != pid]
    save_data()
    return {"ok": True}

# ── ASSEMBLIES (ensambles — números de parte principales) ──
@app.post("/api/assemblies")
def create_assembly(data: AssemblyModel):
    find_or_404(tracker_db["projects"], data.project_id, "Proyecto")
    pn = data.part_number.strip()
    if not pn:
        raise HTTPException(status_code=400, detail="Número de ensamble requerido")
    asm = {"id": next_id(tracker_db["assemblies"]), "project_id": data.project_id,
           "part_number": pn, "description": data.description or "",
           "qty_ordered": data.qty_ordered, "active": True}
    tracker_db["assemblies"].append(asm)
    save_data()
    return asm

@app.put("/api/assemblies/{aid}")
def update_assembly(aid: int, data: AssemblyModel):
    asm  = find_or_404(tracker_db["assemblies"], aid, "Ensamble")
    proj = find_or_404(tracker_db["projects"], data.project_id, "Proyecto")
    pn = data.part_number.strip()
    if not pn:
        raise HTTPException(status_code=400, detail="Número de ensamble requerido")
    asm.update({"project_id": data.project_id, "part_number": pn,
                "description": data.description or "", "qty_ordered": data.qty_ordered})
    sync_assembly_to_items(asm)
    for it in tracker_db["items"]:
        if it.get("assembly_id") == aid:
            it["project_id"] = proj["id"]
            it["client_id"]  = proj["client_id"]
    save_data()
    return asm

@app.delete("/api/assemblies/{aid}")
def delete_assembly(aid: int, force: bool = False):
    find_or_404(tracker_db["assemblies"], aid, "Ensamble")
    dep = assembly_dependents(aid)
    if any(dep.values()) and not force:
        raise HTTPException(status_code=409, detail={"dependents": dep})
    ap_ids = {ap["id"] for ap in tracker_db["assembly_parts"] if ap["assembly_id"] == aid}
    tracker_db["items"]          = [i for i in tracker_db["items"] if i.get("assembly_part_id") not in ap_ids]
    tracker_db["assembly_parts"] = [ap for ap in tracker_db["assembly_parts"] if ap["id"] not in ap_ids]
    tracker_db["assemblies"]     = [a for a in tracker_db["assemblies"] if a["id"] != aid]
    save_data()
    return {"ok": True}

# ── PARTS (catálogo global — reutilizable entre ensambles / proyectos) ──
@app.post("/api/parts")
def create_part(data: PartModel):
    pn = data.part_number.strip()
    if not pn:
        raise HTTPException(status_code=400, detail="Número de parte requerido")
    if any(p["part_number"].lower() == pn.lower() for p in tracker_db["parts"]):
        raise HTTPException(status_code=400, detail="Ya existe una parte con ese número")
    part = {"id": next_id(tracker_db["parts"]), "part_number": pn,
            "description": data.description or "", "image": None, "active": True}
    tracker_db["parts"].append(part)
    save_data()
    return part

@app.put("/api/parts/{part_id}")
def update_part(part_id: int, data: PartModel):
    part = find_or_404(tracker_db["parts"], part_id, "Parte")
    pn = data.part_number.strip()
    if not pn:
        raise HTTPException(status_code=400, detail="Número de parte requerido")
    if any(p["part_number"].lower() == pn.lower() and p["id"] != part_id for p in tracker_db["parts"]):
        raise HTTPException(status_code=400, detail="Ya existe una parte con ese número")
    part.update({"part_number": pn, "description": data.description or ""})
    sync_part_to_items(part)
    save_data()
    return part

@app.put("/api/parts/{part_id}/image")
def update_part_image(part_id: int, data: PartImageModel):
    part = find_or_404(tracker_db["parts"], part_id, "Parte")
    part["image"] = data.image
    save_data()
    return part

@app.delete("/api/parts/{part_id}")
def delete_part(part_id: int, force: bool = False):
    find_or_404(tracker_db["parts"], part_id, "Parte")
    dep = part_dependents(part_id)
    if any(dep.values()) and not force:
        raise HTTPException(status_code=409, detail={"dependents": dep})
    ap_ids = {ap["id"] for ap in tracker_db["assembly_parts"] if ap["part_id"] == part_id}
    tracker_db["items"]          = [i for i in tracker_db["items"] if i.get("assembly_part_id") not in ap_ids]
    tracker_db["assembly_parts"] = [ap for ap in tracker_db["assembly_parts"] if ap["id"] not in ap_ids]
    tracker_db["parts"]          = [p for p in tracker_db["parts"] if p["id"] != part_id]
    save_data()
    return {"ok": True}

# ── PROCESSES (catálogo) ──
@app.post("/api/processes")
def create_process(data: ProcessModel):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    if any(p["name"].lower() == name.lower() for p in tracker_db["processes"]):
        raise HTTPException(status_code=400, detail="Ya existe un proceso con ese nombre")
    proc = {"id": next_id(tracker_db["processes"]), "name": name, "active": True}
    tracker_db["processes"].append(proc)
    save_data()
    return proc

@app.put("/api/processes/{proc_id}")
def update_process(proc_id: int, data: ProcessModel):
    proc = find_or_404(tracker_db["processes"], proc_id, "Proceso")
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre requerido")
    if any(p["name"].lower() == name.lower() and p["id"] != proc_id for p in tracker_db["processes"]):
        raise HTTPException(status_code=400, detail="Ya existe un proceso con ese nombre")
    proc["name"] = name
    sync_process_to_items(proc)
    save_data()
    return proc

@app.delete("/api/processes/{proc_id}")
def delete_process(proc_id: int, force: bool = False):
    find_or_404(tracker_db["processes"], proc_id, "Proceso")
    dep = process_dependents(proc_id)
    if dep["pasos"] and not force:
        raise HTTPException(status_code=409, detail={"dependents": dep})
    affected_aps = {i["assembly_part_id"] for i in tracker_db["items"] if i.get("process_id") == proc_id}
    tracker_db["items"]     = [i for i in tracker_db["items"] if i.get("process_id") != proc_id]
    tracker_db["processes"] = [p for p in tracker_db["processes"] if p["id"] != proc_id]
    for apid in affected_aps:
        steps = sorted([i for i in tracker_db["items"] if i.get("assembly_part_id") == apid],
                        key=lambda x: x.get("seq", x["id"]))
        for idx, s in enumerate(steps, 1):
            s["seq"] = idx
    save_data()
    return {"ok": True}

# ── ASSEMBLY PARTS (BOM: asignar una parte del catálogo a un ensamble) ──
@app.post("/api/assemblies/{assembly_id}/parts")
def add_assembly_part(assembly_id: int, data: AssemblyPartModel):
    find_or_404(tracker_db["assemblies"], assembly_id, "Ensamble")
    find_or_404(tracker_db["parts"], data.part_id, "Parte")
    if any(ap["assembly_id"] == assembly_id and ap["part_id"] == data.part_id
           for ap in tracker_db["assembly_parts"]):
        raise HTTPException(status_code=400, detail="Esa parte ya está asignada a este ensamble")
    ap = {"id": next_id(tracker_db["assembly_parts"]), "assembly_id": assembly_id,
          "part_id": data.part_id, "qty_ordered": data.qty_ordered, "active": True}
    tracker_db["assembly_parts"].append(ap)
    save_data()
    return ap

@app.put("/api/assembly-parts/{ap_id}")
def update_assembly_part(ap_id: int, data: AssemblyPartQtyModel):
    ap = find_or_404(tracker_db["assembly_parts"], ap_id, "Parte de ensamble")
    ap["qty_ordered"] = data.qty_ordered
    sync_assembly_part_qty_to_items(ap)
    save_data()
    return ap

@app.delete("/api/assembly-parts/{ap_id}")
def delete_assembly_part(ap_id: int, force: bool = False):
    find_or_404(tracker_db["assembly_parts"], ap_id, "Parte de ensamble")
    dep = assembly_part_dependents(ap_id)
    if dep["pasos"] and not force:
        raise HTTPException(status_code=409, detail={"dependents": dep})
    tracker_db["items"]          = [i for i in tracker_db["items"] if i.get("assembly_part_id") != ap_id]
    tracker_db["assembly_parts"] = [ap for ap in tracker_db["assembly_parts"] if ap["id"] != ap_id]
    save_data()
    return {"ok": True}

# ── PART STEPS (asignar / quitar un proceso de una parte-de-ensamble) ──
@app.post("/api/assembly-parts/{ap_id}/steps")
def add_step(ap_id: int, data: StepModel):
    ap   = find_or_404(tracker_db["assembly_parts"], ap_id, "Parte de ensamble")
    proc = find_or_404(tracker_db["processes"], data.process_id, "Proceso")
    part = find_or_404(tracker_db["parts"], ap["part_id"], "Parte")
    asm  = find_or_404(tracker_db["assemblies"], ap["assembly_id"], "Ensamble")
    proj = find_or_404(tracker_db["projects"], asm["project_id"], "Proyecto")
    if any(i.get("assembly_part_id") == ap_id and i.get("process_id") == proc["id"]
           for i in tracker_db["items"]):
        raise HTTPException(status_code=400, detail="Ese proceso ya está asignado a esta parte")
    existing = [i for i in tracker_db["items"] if i.get("assembly_part_id") == ap_id]
    seq = max([i.get("seq", 0) for i in existing], default=0) + 1
    new_id = next_id(tracker_db["items"])
    item = {
        "id": new_id, "assembly_part_id": ap_id,
        "assembly_id": asm["id"], "part_id": part["id"],
        "client_id": proj["client_id"], "project_id": proj["id"], "process_id": proc["id"],
        "assembly_number": asm["part_number"], "part_number": part["part_number"],
        "description": part["description"], "process": proc["name"], "seq": seq,
        "priority": new_id,
        "planned_start": "", "planned_end": "", "actual_start": "", "actual_end": "",
        "qty_ordered": ap["qty_ordered"], "qty_completed": 0,
        "status": "Sin Iniciar", "notes": "", "cycle_time_min": None,
    }
    tracker_db["items"].append(item)
    save_data()
    return item

@app.delete("/api/steps/{step_id}")
def delete_step(step_id: int, force: bool = False):
    item = find_or_404(tracker_db["items"], step_id, "Paso")
    if (item["qty_completed"] > 0 or item["status"] != "Sin Iniciar") and not force:
        raise HTTPException(status_code=409, detail={"dependents": {"progreso": 1}})
    ap_id = item.get("assembly_part_id")
    tracker_db["items"] = [i for i in tracker_db["items"] if i["id"] != step_id]
    steps = sorted([i for i in tracker_db["items"] if i.get("assembly_part_id") == ap_id],
                    key=lambda x: x.get("seq", x["id"]))
    for idx, s in enumerate(steps, 1):
        s["seq"] = idx
    save_data()
    return {"ok": True}

# ─────────────────────────────────────────────
# EXPORT — EXCEL  (adds Ensamble column / groups by ensamble+parte)
# ─────────────────────────────────────────────
@app.get("/export/excel")
def export_excel():
    file_name = "tracker_report.xlsx"
    wb = openpyxl.Workbook()

    C = {
        "HDR_BG":  "1F3864", "HDR_FG":  "FFFFFF",
        "COMP_BG": "1E5631", "COMP_FG": "FFFFFF",
        "PROC_BG": "7B6000", "PROC_FG": "FFE082",
        "SIN_BG":  "1A237E", "SIN_FG":  "C5CAE9",
        "TTL_BG":  "071529", "TTL_FG":  "E6D17A",
        "SEC_BG":  "0D1F35", "SEC_FG":  "4FC3F7",
        "ALT_BG":  "0A1828",
    }
    thin   = Side(style="thin", color="334466")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def cs(ws, row, col, value, bg=None, fg="FFFFFF",
           bold=False, size=11, align="center", wrap=False):
        c = ws.cell(row=row, column=col, value=value)
        if bg:
            c.fill = PatternFill("solid", fgColor=bg)
        c.font      = Font(bold=bold, color=fg, size=size, name="Segoe UI")
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        c.border    = border
        return c

    items     = tracker_db["items"]
    aps       = set(i["assembly_part_id"] for i in items)
    comp      = set(i["assembly_part_id"] for i in items if i["status"] == "Completado")
    eff       = round(len(comp)/len(aps)*100, 1) if aps else 0
    processes = list(dict.fromkeys(i["process"] for i in items))

    ST = {
        "Completado":  (C["COMP_BG"], C["COMP_FG"]),
        "En Proceso":  (C["PROC_BG"], C["PROC_FG"]),
        "Sin Iniciar": (C["SIN_BG"],  C["SIN_FG"]),
    }

    # ── Sheet 1: Detalle ──────────────────────────────
    ws1 = wb.active
    ws1.title = "Detalle"
    ws1.sheet_view.showGridLines = False
    ws1.freeze_panes = "A4"

    hdrs = ["ID","Ensamble","Part Number","Descripción","Proceso",
            "Inicio Plan.","Fin Plan.","Inicio Real","Fin Real",
            "Qty Ord.","Qty Comp.","T.Ciclo (min)","Estatus","Notas"]

    ws1.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(hdrs))
    cs(ws1,1,1, f"FABRICATION TRACKER — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
       bg=C["TTL_BG"], fg=C["TTL_FG"], bold=True, size=14)
    ws1.row_dimensions[1].height = 30

    for col, (lbl, val) in enumerate([
        ("Total Parts", len(aps)), ("Completados", len(comp)), ("Eficiencia", f"{eff}%")
    ], 1):
        start = (col-1)*4 + 1
        ws1.merge_cells(start_row=2, start_column=start, end_row=2, end_column=start+3)
        cs(ws1,2,start, f"{lbl}: {val}", bg=C["SEC_BG"], fg=C["SEC_FG"], bold=True)
    ws1.row_dimensions[2].height = 22

    for c, h in enumerate(hdrs, 1):
        cs(ws1,3,c, h, bg=C["HDR_BG"], fg=C["HDR_FG"], bold=True, size=10)
    ws1.row_dimensions[3].height = 20

    for r, item in enumerate(items, 4):
        alt   = r % 2 == 0
        rbg   = C["ALT_BG"] if alt else None
        st_bg, st_fg = ST.get(item["status"], (rbg, "FFFFFF"))
        vals = [
            item["id"], item.get("assembly_number",""), item["part_number"], item["description"], item["process"],
            item["planned_start"], item["planned_end"],
            item["actual_start"],  item["actual_end"],
            item["qty_ordered"],   item["qty_completed"],
            item["cycle_time_min"],
        ]
        for c, v in enumerate(vals, 1):
            cs(ws1,r,c, v, bg=rbg, fg="C5CAE9", size=10,
               align="left" if c in (2,3,4,5) else "center")
        cs(ws1,r,13, item["status"],  bg=st_bg, fg=st_fg, bold=True, size=10)
        cs(ws1,r,14, item["notes"],   bg=rbg,   fg="C5CAE9", size=10, align="left", wrap=True)
        ws1.row_dimensions[r].height = 18

    for i, w in enumerate([5,14,18,20,16,13,13,16,16,10,11,13,14,22], 1):
        ws1.column_dimensions[get_column_letter(i)].width = w

    # ── Sheet 2: Matriz de Flujo ──────────────────────
    ws2 = wb.create_sheet("Matriz de Flujo")
    ws2.sheet_view.showGridLines = False
    ap_label = {}
    parts_map = {}
    for item in items:
        apid = item["assembly_part_id"]
        ap_label[apid] = f"{item.get('assembly_number','')} / {item['part_number']}"
        parts_map.setdefault(apid, {})[item["process"]] = item

    ws2.merge_cells(f"A1:{get_column_letter(len(processes)+1)}1")
    cs(ws2,1,1,"MATRIZ DE FLUJO DE MANUFACTURA",bg=C["TTL_BG"],fg=C["TTL_FG"],bold=True,size=13)
    ws2.row_dimensions[1].height = 28
    cs(ws2,2,1,"Ensamble / Parte",bg=C["HDR_BG"],fg=C["HDR_FG"],bold=True)
    for c, p in enumerate(processes, 2):
        cs(ws2,2,c, p, bg=C["HDR_BG"],fg=C["HDR_FG"],bold=True)
    ws2.row_dimensions[2].height = 20

    for r, (apid, pd_) in enumerate(parts_map.items(), 3):
        alt = r % 2 == 0
        bg  = C["ALT_BG"] if alt else None
        cs(ws2,r,1,ap_label[apid],bg=bg,fg=C["SEC_FG"],bold=True,align="left")
        for c, p in enumerate(processes, 2):
            it = pd_.get(p)
            if it:
                sb, sf = ST.get(it["status"],(bg,"FFFFFF"))
                ct = f"\n⏱{it['cycle_time_min']}m" if it["cycle_time_min"] else ""
                cs(ws2,r,c, f"{it['qty_completed']}/{it['qty_ordered']}{ct}",
                   bg=sb,fg=sf,bold=(it["status"]=="Completado"),wrap=True)
            else:
                cs(ws2,r,c,"—",bg=bg,fg="555577")
        ws2.row_dimensions[r].height = 28

    ws2.column_dimensions["A"].width = 26
    for c in range(2, len(processes)+2):
        ws2.column_dimensions[get_column_letter(c)].width = 18

    # ── Sheet 3: Resumen por Proceso ──────────────────
    ws3 = wb.create_sheet("Resumen por Proceso")
    ws3.sheet_view.showGridLines = False
    ws3.merge_cells("A1:G1")
    cs(ws3,1,1,"RESUMEN POR PROCESO",bg=C["TTL_BG"],fg=C["TTL_FG"],bold=True,size=13)
    ws3.row_dimensions[1].height = 28
    for c, h in enumerate(["Proceso","Total","Sin Iniciar","En Proceso","Completado","% Avance","T.Ciclo Prom (min)"],1):
        cs(ws3,2,c,h,bg=C["HDR_BG"],fg=C["HDR_FG"],bold=True)
    ws3.row_dimensions[2].height = 20

    for r, p in enumerate(processes, 3):
        pi    = [i for i in items if i["process"] == p]
        total = len(pi)
        sin   = sum(1 for i in pi if i["status"]=="Sin Iniciar")
        en_p  = sum(1 for i in pi if i["status"]=="En Proceso")
        cmp   = sum(1 for i in pi if i["status"]=="Completado")
        pct   = round(cmp/total*100,1) if total else 0
        times = [i["cycle_time_min"] for i in pi if i["cycle_time_min"] is not None]
        avg_ct= round(sum(times)/len(times),1) if times else "—"
        alt   = r%2==0; bg=C["ALT_BG"] if alt else None
        cs(ws3,r,1,p,   bg=bg,fg=C["SEC_FG"],bold=True,align="left")
        cs(ws3,r,2,total,bg=bg,fg="C5CAE9")
        cs(ws3,r,3,sin,  bg=bg,fg=C["SIN_FG"])
        cs(ws3,r,4,en_p, bg=bg,fg=C["PROC_FG"])
        cs(ws3,r,5,cmp,  bg=bg,fg=C["COMP_FG"])
        pct_bg=C["COMP_BG"] if pct==100 else (C["PROC_BG"] if pct>0 else bg)
        pct_fg=C["COMP_FG"] if pct==100 else (C["PROC_FG"] if pct>0 else C["SIN_FG"])
        cs(ws3,r,6,f"{pct}%",bg=pct_bg,fg=pct_fg,bold=True)
        cs(ws3,r,7,avg_ct,bg=bg,fg="C5CAE9")
        ws3.row_dimensions[r].height = 18

    for i,w in enumerate([22,10,14,14,14,12,18],1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    # ── Sheet 4: Historial de Eficiencia ─────────────
    ws4 = wb.create_sheet("Historial")
    ws4.sheet_view.showGridLines = False
    ws4.merge_cells("A1:C1")
    cs(ws4,1,1,"HISTORIAL DE EFICIENCIA",bg=C["TTL_BG"],fg=C["TTL_FG"],bold=True,size=13)
    ws4.row_dimensions[1].height = 28
    for c,h in enumerate(["Fecha","Eficiencia %"],1):
        cs(ws4,2,c,h,bg=C["HDR_BG"],fg=C["HDR_FG"],bold=True)
    snaps = load_snapshots()
    for r, s in enumerate(snaps, 3):
        alt=r%2==0;bg=C["ALT_BG"] if alt else None
        cs(ws4,r,1,s["date"],bg=bg,fg="C5CAE9",align="left")
        cs(ws4,r,2,s["efficiency"],bg=bg,fg=C["TTL_FG"],bold=True)
    ws4.column_dimensions["A"].width=14
    ws4.column_dimensions["B"].width=14

    wb.save(file_name)
    return FileResponse(file_name,
        filename=f"fabrication_tracker_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ─────────────────────────────────────────────
# EXPORT — UPLOAD TEMPLATE
# ─────────────────────────────────────────────
@app.get("/export/template")
def export_template():
    """Generate a ready-to-fill Excel template matching the /upload format."""
    file_name = "fabrication_template.xlsx"
    wb = openpyxl.Workbook()

    # ── palette (reuse same dark theme) ──────────────────
    C = {
        "TTL_BG": "071529", "TTL_FG": "E6D17A",
        "HDR_BG": "1F3864", "HDR_FG": "FFFFFF",
        "ALT_BG": "0A1828", "SEC_FG": "4FC3F7",
        "NOTE_BG":"0D2040", "NOTE_FG":"FFE082",
        "EX_BG":  "0A1F0F", "EX_FG":  "81C784",
        "LOCK_BG":"1A237E", "LOCK_FG":"C5CAE9",
    }
    thin   = Side(style="thin", color="334466")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def cs(ws, row, col, value, bg=None, fg="FFFFFF",
           bold=False, size=11, align="center", wrap=False, italic=False):
        c = ws.cell(row=row, column=col, value=value)
        if bg:
            c.fill = PatternFill("solid", fgColor=bg)
        c.font      = Font(bold=bold, italic=italic, color=fg, size=size, name="Segoe UI")
        c.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        c.border    = border
        return c

    from openpyxl.worksheet.datavalidation import DataValidation

    # ══════════════════════════════════════════════════════
    #  SHEET 1 — Template (the actual upload sheet)
    # ══════════════════════════════════════════════════════
    ws = wb.active
    ws.title = "Template"
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A4"

    # Title
    ws.merge_cells("A1:F1")
    cs(ws,1,1, "FABRICATION TRACKER — Plantilla de Carga",
       bg=C["TTL_BG"], fg=C["TTL_FG"], bold=True, size=14)
    ws.row_dimensions[1].height = 30

    # Subtitle / instructions
    ws.merge_cells("A2:K2")
    cs(ws,2,1,
       "Llena desde la fila 4 hacia abajo. Assembly_Number y Part_Number son obligatorios "
       "(el Ensamble es la pieza principal; Part_Number son sus componentes). Client y Project "
       "son opcionales (si se dejan vacíos se usa 'Cliente General' / 'Proyecto General'). "
       "Un mismo Part_Number puede repetirse en distintos Assembly_Number: el sistema lo trata "
       "como una parte común y reutilizable, con avance independiente en cada ensamble. "
       "Sequence define el orden de los procesos por parte (1, 2, 3…). No cambies los encabezados de la fila 3.",
       bg=C["NOTE_BG"], fg=C["NOTE_FG"], size=9, align="left", wrap=True, italic=True)
    ws.row_dimensions[2].height = 42

    # Column headers  — must match what /upload expects exactly
    COLS = [
        ("Client",               "Nombre del cliente (opcional)",                          16),
        ("Project",              "Nombre del proyecto (opcional)",                          16),
        ("Assembly_Number",      "Número de parte del ENSAMBLE. Ej: ENS-1000",              16),
        ("Assembly_Description", "Descripción del ensamble (opcional)",                     20),
        ("Assembly_Qty",         "Cantidad de ensambles a fabricar (opcional)",             13),
        ("Part_Number",          "Número de parte del COMPONENTE. Ej: M1320502-001. "
                                  "Puede repetirse en otros ensambles (parte común)",        18),
        ("Description",          "Descripción de la pieza (opcional)",                      22),
        ("Process",              "Nombre del proceso. Ej: Punzonado",                       16),
        ("Sequence",             "Orden del proceso para esta parte (1,2,3…)",              11),
        ("Qty",                  "Cantidad de este componente a fabricar en este ensamble", 10),
        ("Notes",                "Notas adicionales (opcional)",                            20),
    ]
    for c, (hdr, _, w) in enumerate(COLS, 1):
        cs(ws,3,c, hdr, bg=C["HDR_BG"], fg=C["HDR_FG"], bold=True, size=10)
        ws.column_dimensions[get_column_letter(c)].width = w
    ws.row_dimensions[3].height = 20

    LEFT_COLS = (1,2,3,4,6,7,8,11)  # Client, Project, Assembly_Number, Assembly_Description, Part_Number, Description, Process, Notes

    # ── Example rows — muestra una parte común (Bracket A) compartida entre 2 ensambles ──
    examples = [
        ("Acme Corp","Proyecto Alfa","ENS-1000","Ensamble Principal",10,"M1320502-001","Bracket A","Punzonado",1,100,""),
        ("Acme Corp","Proyecto Alfa","ENS-1000","Ensamble Principal",10,"M1320502-001","Bracket A","Doblado",  2,100,""),
        ("Acme Corp","Proyecto Alfa","ENS-1000","Ensamble Principal",10,"M1320502-001","Bracket A","Insercion",3,100,""),
        ("Acme Corp","Proyecto Alfa","ENS-1000","Ensamble Principal",10,"M1320509-001","Bracket B","Punzonado",1,120,""),
        ("Acme Corp","Proyecto Alfa","ENS-1000","Ensamble Principal",10,"M1320509-001","Bracket B","Doblado",  2,120,""),
        ("Acme Corp","Proyecto Alfa","ENS-1000","Ensamble Principal",10,"M1320509-001","Bracket B","Insercion",3,120,""),
        ("Acme Corp","Proyecto Beta","ENS-2000","Ensamble Secundario",5,"M1320502-001","Bracket A","Punzonado",1,50,"Parte común, reutilizada de ENS-1000"),
        ("Acme Corp","Proyecto Beta","ENS-2000","Ensamble Secundario",5,"M1320502-001","Bracket A","Doblado",  2,50,""),
        ("Acme Corp","Proyecto Beta","ENS-2000","Ensamble Secundario",5,"M1320502-001","Bracket A","Insercion",3,50,""),
    ]
    for r, row in enumerate(examples, 4):
        alt = r % 2 == 0
        bg  = C["ALT_BG"] if alt else C["EX_BG"]
        for c, val in enumerate(row, 1):
            cs(ws, r, c, val, bg=bg, fg=C["EX_FG"], size=10,
               align="left" if c in LEFT_COLS else "center",
               italic=True)
        ws.row_dimensions[r].height = 18

    # ── 50 blank input rows below examples ───────────────
    n_cols = len(COLS)
    for r in range(4+len(examples), 4+len(examples)+50):
        alt = r % 2 == 0
        bg  = C["ALT_BG"] if alt else None
        for c in range(1, n_cols+1):
            cs(ws, r, c, None, bg=bg, fg="C5CAE9", size=10,
               align="left" if c in LEFT_COLS else "center")
        ws.row_dimensions[r].height = 18

    last_row = 4 + len(examples) + 50

    # ── Data validation: Sequence must be integer 1-20 ───
    seq_col = get_column_letter(9)
    dv_seq = DataValidation(
        type="whole", operator="between", formula1="1", formula2="20",
        showErrorMessage=True,
        errorTitle="Secuencia inválida",
        error="Ingresa un número entero entre 1 y 20."
    )
    dv_seq.sqref = f"{seq_col}4:{seq_col}{last_row}"
    ws.add_data_validation(dv_seq)

    # ── Data validation: Qty must be positive integer ────
    qty_col = get_column_letter(10)
    dv_qty = DataValidation(
        type="whole", operator="greaterThan", formula1="0",
        showErrorMessage=True,
        errorTitle="Cantidad inválida",
        error="La cantidad debe ser un número entero mayor a 0."
    )
    dv_qty.sqref = f"{qty_col}4:{qty_col}{last_row}"
    ws.add_data_validation(dv_qty)

    # ══════════════════════════════════════════════════════
    #  SHEET 2 — Instructions (visual guide)
    # ══════════════════════════════════════════════════════
    wi = wb.create_sheet("Instrucciones")
    wi.sheet_view.showGridLines = False
    wi.column_dimensions["A"].width = 5
    wi.column_dimensions["B"].width = 22
    wi.column_dimensions["C"].width = 55

    wi.merge_cells("A1:C1")
    cs(wi,1,1, "GUÍA DE USO — Plantilla de Carga",
       bg=C["TTL_BG"], fg=C["TTL_FG"], bold=True, size=14)
    wi.row_dimensions[1].height = 30

    steps_guide = [
        ("1", "Client",
         "Nombre del cliente. Opcional — si se deja vacío se agrupa bajo 'Cliente General'. "
         "Si el cliente ya existe (mismo nombre) se reutiliza, si no se crea automáticamente."),
        ("2", "Project",
         "Nombre del proyecto dentro del cliente. Opcional — si se deja vacío se usa 'Proyecto General'."),
        ("3", "Assembly_Number",
         "Identificador único del ENSAMBLE (la pieza/proyecto principal). Usa el mismo valor "
         "en todas las filas de ese ensamble."),
        ("4", "Assembly_Description",
         "Nombre o descripción del ensamble. Campo opcional."),
        ("5", "Assembly_Qty",
         "Cantidad de ensambles a fabricar. Opcional, solo informativo."),
        ("6", "Part_Number",
         "Identificador del NÚMERO DE PARTE (componente) dentro del ensamble. Puedes repetir el "
         "mismo Part_Number en distintos ensambles o proyectos: el sistema lo reconoce como una "
         "parte común y comparte su catálogo, pero da seguimiento independiente a su avance en cada ensamble."),
        ("7", "Description",
         "Nombre o descripción de la pieza. Campo opcional, solo se muestra en la UI."),
        ("8", "Process",
         "Nombre exacto del proceso (Ej: Punzonado, Doblado, Soldadura). "
         "Puedes tener tantos procesos como necesites por parte, y no todas las partes "
         "necesitan los mismos procesos."),
        ("9", "Sequence",
         "Número que define el ORDEN de ejecución de los procesos para esa parte. "
         "Empieza en 1. El proceso con Sequence=1 se activa primero, "
         "luego el 2 cuando el 1 esté Completado, y así sucesivamente."),
        ("10", "Qty",
         "Cantidad de piezas de este componente a fabricar en este ensamble."),
        ("11", "Notes",
         "Campo libre para instrucciones especiales, herramientas, referencias, etc."),
    ]

    wi.merge_cells("A2:C2")
    cs(wi,2,1, "Columnas del Template", bg=C["HDR_BG"], fg=C["HDR_FG"], bold=True, size=11)
    wi.row_dimensions[2].height = 22

    for r, (num, col, desc) in enumerate(steps_guide, 3):
        cs(wi, r, 1, num,  bg=C["NOTE_BG"], fg=C["NOTE_FG"], bold=True, size=11)
        cs(wi, r, 2, col,  bg=C["ALT_BG"],  fg=C["SEC_FG"],  bold=True, size=10, align="left")
        cs(wi, r, 3, desc, bg=C["ALT_BG"],  fg="C5CAE9",     size=10, align="left", wrap=True)
        wi.row_dimensions[r].height = 42

    guide_end = 3 + len(steps_guide)

    # Example block
    ex_title_row = guide_end + 1
    wi.merge_cells(f"A{ex_title_row}:C{ex_title_row}")
    cs(wi,ex_title_row,1, "Ejemplo: un ensamble con 1 parte y 3 procesos",
       bg=C["HDR_BG"], fg=C["HDR_FG"], bold=True, size=11)
    wi.row_dimensions[ex_title_row].height = 22

    ex_hdrs = ["Client","Project","Assembly_Number","Assembly_Description","Assembly_Qty",
               "Part_Number","Description","Process","Sequence","Qty","Notes"]
    hdr_row = ex_title_row + 1
    cs(wi,hdr_row,1,"",bg=C["HDR_BG"])
    for c, hh in enumerate(ex_hdrs, 2):
        cs(wi,hdr_row,c, hh, bg=C["HDR_BG"], fg=C["HDR_FG"], bold=True, size=9)
    wi.row_dimensions[hdr_row].height = 18

    ex_rows = [
        ("Cliente Ejemplo","Proyecto Ejemplo","ENS-9000","Ensamble X",20,"M9990001-001","Soporte X","Corte",    1,50,""),
        ("Cliente Ejemplo","Proyecto Ejemplo","ENS-9000","Ensamble X",20,"M9990001-001","Soporte X","Doblado",  2,50,""),
        ("Cliente Ejemplo","Proyecto Ejemplo","ENS-9000","Ensamble X",20,"M9990001-001","Soporte X","Pintura",  3,50,"Usar pintura gris RAL 7016"),
    ]
    for r, row in enumerate(ex_rows, hdr_row+1):
        cs(wi,r,1,"",bg=C["EX_BG"])
        for c, val in enumerate(row, 2):
            cs(wi,r,c, val, bg=C["EX_BG"], fg=C["EX_FG"], size=9,
               align="left" if c in (2,3,4,7,8,12) else "center", italic=True)
        wi.row_dimensions[r].height = 18

    # tip row
    tip_row = hdr_row + 1 + len(ex_rows) + 1
    wi.merge_cells(f"A{tip_row}:C{tip_row}")
    cs(wi,tip_row,1,
       "💡 TIP: Puedes agregar tantos clientes, proyectos y ensambles como necesites. Si un mismo "
       "Part_Number aparece en varios Assembly_Number, el sistema lo trata como una parte común: "
       "comparte catálogo (número/descripción) pero da seguimiento de procesos independiente en cada ensamble.",
       bg=C["NOTE_BG"], fg=C["NOTE_FG"], size=10, align="left", wrap=True, italic=True)
    wi.row_dimensions[tip_row].height = 44

    for col_letter, width in zip(["A","B","C","D","E","F","G","H","I","J","K","L"],
                                  [5,20,20,22,18,12,20,22,18,10,8,22]):
        wi.column_dimensions[col_letter].width = width

    wb.save(file_name)
    return FileResponse(file_name,
        filename=f"fabrication_template.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# -----------------------------------------
# PDF DIAGNOSTIC
# -----------------------------------------
@app.get("/api/test-pdf")
def test_pdf():
    results = {}
    try:
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import Image as RLImage
        results["reportlab"] = "OK"
    except ImportError as e:
        results["reportlab"] = f"MISSING: {e}"
    results["logo_path"]    = LOGO_PATH
    results["logo_exists"]  = os.path.exists(LOGO_PATH)
    results["items_count"]  = len(tracker_db["items"])
    results["write_access"] = os.access(".", os.W_OK)
    return results

# -----------------------------------------
# EXPORT -- PDF
# -----------------------------------------
@app.get("/export/pdf")
def export_pdf():
    import traceback
    file_name = "tracker_report.pdf"
    try:
        doc = SimpleDocTemplate(
            file_name, pagesize=landscape(letter),
            leftMargin=0.5*inch, rightMargin=0.5*inch,
            topMargin=0.5*inch,  bottomMargin=0.5*inch,
        )

        NAVY    = colors.HexColor("#071529")
        GOLD    = colors.HexColor("#E6D17A")
        TEAL    = colors.HexColor("#4FC3F7")
        DKBLUE  = colors.HexColor("#1F3864")
        GREEN   = colors.HexColor("#1E5631")
        AMBER   = colors.HexColor("#7B6000")
        SINBLUE = colors.HexColor("#1A237E")
        WHITE   = colors.white
        LTGRAY  = colors.HexColor("#C5CAE9")
        ALT     = colors.HexColor("#0A1828")
        GRID_C  = colors.HexColor("#334466")
        AMBER_FG= colors.HexColor("#FFE082")
        GRAY_DIM= colors.HexColor("#555577")

        STATUS_BG = {
            "Completado":  GREEN,
            "En Proceso":  AMBER,
            "Sin Iniciar": SINBLUE,
        }

        def cp(name, fg, font="Helvetica", size=7.5, align="CENTER"):
            return ParagraphStyle(
                name, fontName=font, fontSize=size, textColor=fg,
                leading=size * 1.35,
                alignment={"LEFT": 0, "CENTER": 1, "RIGHT": 2}.get(align, 1),
                wordWrap="LTR", spaceAfter=0, spaceBefore=0,
            )

        def safe(v):
            if v is None or v == "":
                return "-"
            s = str(v)
            for bad, good in [("—","-"),("–","-"),("⏱",""),("→",">"),("\n"," ")]:
                s = s.replace(bad, good)
            return s.strip() or "-"

        items     = tracker_db["items"]
        processes = list(dict.fromkeys(i["process"] for i in items))
        aps       = set(i["assembly_part_id"] for i in items)
        comp_p    = set(i["assembly_part_id"] for i in items if i["status"] == "Completado")
        eff       = round(len(comp_p) / len(aps) * 100, 1) if aps else 0

        elements = []

        # -- Logo + Title header --
        ps_title = cp("Title", GOLD,  font="Helvetica-Bold", size=16, align="CENTER")
        ps_date  = cp("Date",  TEAL,  size=9, align="CENTER")
        ps_empty = cp("Empty", WHITE, size=8, align="LEFT")

        if os.path.exists(LOGO_PATH):
            logo_cell = RLImage(LOGO_PATH, width=1.3*inch, height=0.5*inch, kind="proportional")
        else:
            logo_cell = Paragraph("", ps_empty)

        hdr_tbl = Table(
            [[logo_cell,
              [Paragraph("FABRICATION TRACKER", ps_title),
               Paragraph("Reporte: " + datetime.now().strftime("%d/%m/%Y  %H:%M"), ps_date)],
              ""]],
            colWidths=[1.6*inch, 7.5*inch, 1.6*inch],
        )
        hdr_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), NAVY),
            ("VALIGN",        (0,0), (-1,0), "MIDDLE"),
            ("ALIGN",         (0,0), (0,0),  "LEFT"),
            ("ALIGN",         (1,0), (1,0),  "CENTER"),
            ("LEFTPADDING",   (0,0), (-1,0), 8),
            ("RIGHTPADDING",  (0,0), (-1,0), 8),
            ("TOPPADDING",    (0,0), (-1,0), 8),
            ("BOTTOMPADDING", (0,0), (-1,0), 8),
            ("LINEBELOW",     (0,0), (-1,0), 1.5, GOLD),
        ]))
        elements += [hdr_tbl, Spacer(1, 10)]

        sec_ps = ParagraphStyle(
            "SecHdr", fontName="Helvetica-Bold", fontSize=11,
            textColor=TEAL, backColor=NAVY, spaceAfter=4, leading=14,
        )

        # -- KPI row --
        kpi_tbl = Table(
            [["Total Parts", "Completados", "Eficiencia"],
             [str(len(aps)), str(len(comp_p)), str(eff) + "%"]],
            colWidths=[2.5*inch, 2.5*inch, 2.5*inch],
        )
        kpi_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,0), DKBLUE),
            ("TEXTCOLOR",     (0,0), (-1,0), WHITE),
            ("FONTNAME",      (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",      (0,0), (-1,0), 9),
            ("BACKGROUND",    (0,1), (-1,1), ALT),
            ("TEXTCOLOR",     (0,1), (-1,1), GOLD),
            ("FONTNAME",      (0,1), (-1,1), "Helvetica-Bold"),
            ("FONTSIZE",      (0,1), (-1,1), 13),
            ("ALIGN",         (0,0), (-1,-1), "CENTER"),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("GRID",          (0,0), (-1,-1), 0.5, GRID_C),
            ("TOPPADDING",    (0,0), (-1,-1), 6),
            ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ]))
        elements += [kpi_tbl, Spacer(1, 14)]

        # ── shared paragraph styles for process-group tables ──
        ps_hdr = cp("DH",  WHITE,    font="Helvetica-Bold", size=7.5)
        ps_b   = cp("DB",  LTGRAY,   size=7)
        ps_bL  = cp("DBL", LTGRAY,   size=7, align="LEFT")
        ps_sc  = cp("SC",  WHITE,    font="Helvetica-Bold", size=7)
        ps_sp  = cp("SP",  AMBER_FG, font="Helvetica-Bold", size=7)
        ps_ss  = cp("SS",  LTGRAY,   font="Helvetica-Bold", size=7)
        SPS    = {"Completado": ps_sc, "En Proceso": ps_sp, "Sin Iniciar": ps_ss}

        # ── process group header styles ─────────────────────
        ps_proc_title = ParagraphStyle(
            "ProcTitle", fontName="Helvetica-Bold", fontSize=12,
            textColor=TEAL, backColor=colors.HexColor("#0D2040"),
            leading=16, spaceAfter=0, spaceBefore=0,
            leftIndent=6,
        )
        ps_stat_sin  = cp("PSin",  colors.HexColor("#C5CAE9"), font="Helvetica-Bold", size=8)
        ps_stat_proc = cp("PProc", colors.HexColor("#FFE082"), font="Helvetica-Bold", size=8)
        ps_stat_comp = cp("PComp", colors.HexColor("#81C784"), font="Helvetica-Bold", size=8)

        col_w = [0.28*inch, 1.05*inch, 1.30*inch, 1.35*inch,
                 0.80*inch, 0.80*inch, 0.90*inch, 0.90*inch,
                 0.55*inch, 0.65*inch, 0.70*inch, 0.85*inch]

        hdr_lbls = ["ID", "Ensamble", "Part Number", "Descripcion",
                    "Ini.Plan", "Fin Plan", "Ini.Real", "Fin Real",
                    "Qty Ord", "Qty Comp", "T.Ciclo m", "Estatus"]

        PAGE_W = 10.7 * inch   # landscape letter usable width

        # ── one section per process ─────────────────────────
        for proc in processes:
            proc_items = [i for i in items if i["process"] == proc]
            total = len(proc_items)
            n_sin  = sum(1 for i in proc_items if i["status"] == "Sin Iniciar")
            n_proc = sum(1 for i in proc_items if i["status"] == "En Proceso")
            n_comp = sum(1 for i in proc_items if i["status"] == "Completado")
            pct    = round(n_comp / total * 100, 1) if total else 0

            # ── section header bar ──────────────────────────
            stat_cells = [
                [Paragraph(proc, ps_proc_title),
                 Paragraph(f"⚪ Sin Iniciar: {n_sin}", ps_stat_sin),
                 Paragraph(f"● En Proceso: {n_proc}",  ps_stat_proc),
                 Paragraph(f"● Completado: {n_comp}",  ps_stat_comp),
                 Paragraph(f"{pct}%",                   ps_stat_comp if pct==100 else ps_stat_proc if pct>0 else ps_stat_sin),
                ]
            ]
            stat_tbl = Table(
                stat_cells,
                colWidths=[3.2*inch, 1.7*inch, 1.7*inch, 1.7*inch, 0.9*inch],
            )
            stat_tbl.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (-1,0), colors.HexColor("#0D2040")),
                ("VALIGN",        (0,0), (-1,0), "MIDDLE"),
                ("ALIGN",         (0,0), (0,0),  "LEFT"),
                ("ALIGN",         (1,0), (-1,0), "CENTER"),
                ("TOPPADDING",    (0,0), (-1,0), 6),
                ("BOTTOMPADDING", (0,0), (-1,0), 6),
                ("LEFTPADDING",   (0,0), (-1,0), 8),
                ("RIGHTPADDING",  (0,0), (-1,0), 6),
                ("LINEBELOW",     (0,0), (-1,0), 2, TEAL),
            ]))
            elements.append(stat_tbl)

            # ── progress bar (drawn as a 1-row table) ───────
            filled_w = PAGE_W * (pct / 100)
            empty_w  = PAGE_W - filled_w
            bar_style = TableStyle([
                ("BACKGROUND",    (0,0), (0,0), colors.HexColor("#1F3864")),
                ("BACKGROUND",    (1,0), (1,0), colors.HexColor("#0A1828")),
                ("TOPPADDING",    (0,0), (-1,0), 0),
                ("BOTTOMPADDING", (0,0), (-1,0), 0),
                ("LEFTPADDING",   (0,0), (-1,0), 0),
                ("RIGHTPADDING",  (0,0), (-1,0), 0),
            ])
            if filled_w > 0 and empty_w > 0:
                bar_tbl = Table([["",""]], colWidths=[filled_w, empty_w], rowHeights=[5])
            elif filled_w >= PAGE_W:
                bar_tbl = Table([[""]], colWidths=[PAGE_W], rowHeights=[5])
                bar_style = TableStyle([("BACKGROUND",(0,0),(0,0),colors.HexColor("#1E8449")),
                                        ("TOPPADDING",(0,0),(-1,0),0),("BOTTOMPADDING",(0,0),(-1,0),0),
                                        ("LEFTPADDING",(0,0),(-1,0),0),("RIGHTPADDING",(0,0),(-1,0),0)])
            else:
                bar_tbl = Table([[""]], colWidths=[PAGE_W], rowHeights=[5])
            bar_tbl.setStyle(bar_style)
            elements.append(bar_tbl)
            elements.append(Spacer(1, 4))

            # ── parts table for this process ─────────────────
            tbl_rows = [[Paragraph(h, ps_hdr) for h in hdr_lbls]]
            for ri, item in enumerate(proc_items):
                st  = item["status"]
                bg  = ALT if ri % 2 == 0 else NAVY
                tbl_rows.append([
                    Paragraph(safe(item["id"]),                    ps_b),
                    Paragraph(safe(item.get("assembly_number","")),ps_bL),
                    Paragraph(safe(item["part_number"]),           ps_bL),
                    Paragraph(safe(item["description"]),           ps_bL),
                    Paragraph(safe(item["planned_start"]),         ps_b),
                    Paragraph(safe(item["planned_end"]),           ps_b),
                    Paragraph(safe(item["actual_start"]),          ps_b),
                    Paragraph(safe(item["actual_end"]),            ps_b),
                    Paragraph(safe(item["qty_ordered"]),           ps_b),
                    Paragraph(safe(item["qty_completed"]),         ps_b),
                    Paragraph(safe(item.get("cycle_time_min")),    ps_b),
                    Paragraph(safe(st),                            SPS.get(st, ps_b)),
                ])

            p_tbl = Table(tbl_rows, colWidths=col_w, repeatRows=1)
            p_rs  = [
                ("BACKGROUND",    (0,0),  (-1,0),  DKBLUE),
                ("ALIGN",         (0,0),  (-1,-1), "CENTER"),
                ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
                ("GRID",          (0,0),  (-1,-1), 0.4, GRID_C),
                ("TOPPADDING",    (0,0),  (-1,-1), 3),
                ("BOTTOMPADDING", (0,0),  (-1,-1), 3),
                ("LEFTPADDING",   (0,0),  (-1,-1), 2),
                ("RIGHTPADDING",  (0,0),  (-1,-1), 2),
            ]
            for ri, item in enumerate(proc_items, 1):
                bg = ALT if ri % 2 == 0 else NAVY
                p_rs.append(("BACKGROUND", (0,ri),  (10,ri), bg))
                p_rs.append(("TEXTCOLOR",  (0,ri),  (10,ri), LTGRAY))
                p_rs.append(("BACKGROUND", (11,ri), (11,ri), STATUS_BG.get(item["status"], NAVY)))
            p_tbl.setStyle(TableStyle(p_rs))
            elements += [p_tbl, Spacer(1, 14)]

        # -- Flow matrix --
        elements.append(Paragraph("Matriz de Flujo de Manufactura", sec_ps))
        elements.append(Spacer(1, 4))

        ap_label  = {}
        parts_map = {}
        for item in items:
            apid = item["assembly_part_id"]
            ap_label[apid] = f"{item.get('assembly_number','')} / {item['part_number']}"
            parts_map.setdefault(apid, {})[item["process"]] = item

        n   = len(processes)
        pw  = 2.2*inch
        pcw = (9.7*inch - pw) / n if n else 1.5*inch

        ps_mh  = cp("MH",  WHITE,    font="Helvetica-Bold", size=8)
        ps_mp  = cp("MP",  TEAL,     font="Helvetica-Bold", size=7.5, align="LEFT")
        ps_mv  = cp("MV",  LTGRAY,   size=7.5)
        ps_md  = cp("MD",  GRAY_DIM, size=7.5)
        ps_mc  = cp("MC",  WHITE,    font="Helvetica-Bold", size=7.5)
        ps_mpr = cp("MPR", AMBER_FG, font="Helvetica-Bold", size=7.5)
        ps_ms  = cp("MS",  LTGRAY,   font="Helvetica-Bold", size=7.5)
        MPS = {"Completado": ps_mc, "En Proceso": ps_mpr, "Sin Iniciar": ps_ms}

        mx_rows = [[Paragraph("Ensamble / Parte", ps_mh)] + [Paragraph(p, ps_mh) for p in processes]]
        for apid, pd_ in parts_map.items():
            row = [Paragraph(safe(ap_label[apid]), ps_mp)]
            for p in processes:
                it = pd_.get(p)
                if it:
                    ct_str = (" T:" + str(it["cycle_time_min"]) + "m") if it.get("cycle_time_min") else ""
                    label  = str(it["qty_completed"]) + "/" + str(it["qty_ordered"]) + ct_str
                    row.append(Paragraph(label, MPS.get(it["status"], ps_mv)))
                else:
                    row.append(Paragraph("-", ps_md))
            mx_rows.append(row)

        mx_tbl = Table(mx_rows, colWidths=[pw] + [pcw]*n, repeatRows=1)
        mx_rs = [
            ("BACKGROUND",    (0,0),  (-1,0),  DKBLUE),
            ("ALIGN",         (0,0),  (-1,-1), "CENTER"),
            ("ALIGN",         (0,1),  (0,-1),  "LEFT"),
            ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
            ("GRID",          (0,0),  (-1,-1), 0.4, GRID_C),
            ("TOPPADDING",    (0,0),  (-1,-1), 4),
            ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
            ("LEFTPADDING",   (0,0),  (-1,-1), 3),
            ("RIGHTPADDING",  (0,0),  (-1,-1), 3),
        ]
        for ri, (apid, pd_) in enumerate(parts_map.items(), 1):
            bg = ALT if ri % 2 == 0 else NAVY
            mx_rs.append(("BACKGROUND", (0,ri), (0,ri), bg))
            for ci, p in enumerate(processes, 1):
                it    = pd_.get(p)
                st_bg = STATUS_BG.get(it["status"], bg) if it else bg
                mx_rs.append(("BACKGROUND", (ci,ri), (ci,ri), st_bg))
        mx_tbl.setStyle(TableStyle(mx_rs))
        elements += [mx_tbl, Spacer(1, 16)]

        # -- Summary by process --
        elements.append(Paragraph("Resumen por Proceso", sec_ps))
        elements.append(Spacer(1, 4))

        ps_sh  = cp("SH",  WHITE,    font="Helvetica-Bold", size=8)
        ps_sp2 = cp("SP2", TEAL,     font="Helvetica-Bold", size=8, align="LEFT")
        ps_sn  = cp("SN",  LTGRAY,   size=8)
        ps_sc2 = cp("SC2", WHITE,    font="Helvetica-Bold", size=8)
        ps_sa  = cp("SA",  AMBER_FG, font="Helvetica-Bold", size=8)
        ps_sb2 = cp("SB2", LTGRAY,   font="Helvetica-Bold", size=8)

        sm_hdrs = ["Proceso","Total","Sin Iniciar","En Proceso","Completado","% Avance","T.Ciclo Prom"]
        sm_rows = [[Paragraph(h, ps_sh) for h in sm_hdrs]]
        pct_vals = []

        for p in processes:
            pi    = [i for i in items if i["process"] == p]
            total = len(pi)
            sin   = sum(1 for i in pi if i["status"] == "Sin Iniciar")
            en_p  = sum(1 for i in pi if i["status"] == "En Proceso")
            cmp   = sum(1 for i in pi if i["status"] == "Completado")
            pct   = round(cmp / total * 100, 1) if total else 0
            pct_vals.append(pct)
            times = [i["cycle_time_min"] for i in pi if i.get("cycle_time_min") is not None]
            avg   = (str(round(sum(times) / len(times), 1)) + "m") if times else "-"
            pps   = ps_sc2 if pct == 100 else (ps_sa if pct > 0 else ps_sb2)
            sm_rows.append([
                Paragraph(safe(p),        ps_sp2),
                Paragraph(str(total),     ps_sn),
                Paragraph(str(sin),       ps_sn),
                Paragraph(str(en_p),      ps_sn),
                Paragraph(str(cmp),       ps_sn),
                Paragraph(str(pct) + "%", pps),
                Paragraph(avg,            ps_sn),
            ])

        sm_tbl = Table(
            sm_rows,
            colWidths=[2.0*inch, 0.8*inch, 1.1*inch, 1.1*inch, 1.1*inch, 0.9*inch, 1.1*inch],
        )
        sm_rs = [
            ("BACKGROUND",    (0,0),  (-1,0),  DKBLUE),
            ("ALIGN",         (0,0),  (-1,-1), "CENTER"),
            ("ALIGN",         (0,1),  (0,-1),  "LEFT"),
            ("VALIGN",        (0,0),  (-1,-1), "MIDDLE"),
            ("GRID",          (0,0),  (-1,-1), 0.4, GRID_C),
            ("TOPPADDING",    (0,0),  (-1,-1), 4),
            ("BOTTOMPADDING", (0,0),  (-1,-1), 4),
            ("LEFTPADDING",   (0,0),  (-1,-1), 3),
            ("RIGHTPADDING",  (0,0),  (-1,-1), 3),
        ]
        for ri, pv in enumerate(pct_vals, 1):
            bg = ALT if ri % 2 == 0 else NAVY
            sm_rs.append(("BACKGROUND", (0,ri),  (-1,ri), bg))
            pb = GREEN if pv == 100 else (AMBER if pv > 0 else SINBLUE)
            sm_rs.append(("BACKGROUND", (5,ri),  (5,ri),  pb))
        sm_tbl.setStyle(TableStyle(sm_rs))
        elements.append(sm_tbl)

        doc.build(elements)
        return FileResponse(
            file_name,
            filename="fabrication_tracker_" + datetime.now().strftime("%Y%m%d_%H%M") + ".pdf",
            media_type="application/pdf",
        )

    except Exception as exc:
        tb = traceback.format_exc()
        raise HTTPException(status_code=500, detail=str(exc) + "\n\nTraceback:\n" + tb)


# ─────────────────────────────────────────────
# FRONTEND
# ─────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def home():
    return r"""
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Fabrication Tracker</title>
<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4/dist/chart.umd.min.js"></script>
<style>
/* ── RESET & BASE ── */
*{box-sizing:border-box;margin:0;padding:0;}
body{background:#071529;color:#e0e8f0;font-family:'Segoe UI',sans-serif;font-size:14px;}

/* ── LAYOUT ── */
.app{display:flex;flex-direction:column;min-height:100vh;}
.topbar{background:#0a1e38;border-bottom:2px solid #e6d17a;padding:10px 16px;
        display:flex;align-items:center;gap:12px;flex-wrap:wrap;}
.topbar .logo{height:38px;}
.topbar .title{font-size:20px;font-weight:700;color:#e6d17a;flex:1;}
.topbar .kpis{display:flex;gap:18px;flex-wrap:wrap;}
.kpi-box{background:#0d2040;border:1px solid #1f3864;border-radius:8px;
         padding:6px 14px;text-align:center;min-width:90px;}
.kpi-box .val{font-size:22px;font-weight:700;color:#e6d17a;line-height:1.1;}
.kpi-box .lbl{font-size:10px;color:#4fc3f7;text-transform:uppercase;letter-spacing:.5px;}

/* ── TOOLBAR ── */
.toolbar{display:flex;gap:8px;flex-wrap:wrap;padding:10px 16px;
         background:#060f1e;border-bottom:1px solid #1a2d4a;align-items:center;}
.btn{display:inline-flex;align-items:center;gap:5px;padding:7px 14px;border:none;
     border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;
     text-decoration:none;letter-spacing:.3px;transition:filter .15s,transform .1s;}
.btn:hover{filter:brightness(1.18);transform:translateY(-1px);}
.btn:active{transform:translateY(0);}
.btn-upload  {background:#1f3864;color:#e6d17a;}
.btn-excel   {background:#1e7145;color:#fff;}
.btn-pdf     {background:#b22222;color:#fff;}
.btn-template{background:#4a235a;color:#e6d17a;border:1px solid #7b4f8e;}
.btn-bulk    {background:#0d4a3a;color:#81c784;border:1px solid #1e8449;}
.btn-bulk:disabled{opacity:.4;cursor:not-allowed;transform:none;filter:none;}
.file-input{color:#8ba0b8;font-size:12px;}

/* ── ALERTS BANNER ── */
.alerts-banner{background:#3b1a00;border-left:4px solid #ff6b35;
               padding:8px 16px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;}
.alert-chip{background:#5a2800;border:1px solid #ff6b35;border-radius:20px;
            padding:3px 10px;font-size:11px;color:#ffb347;
            animation:pulse 2s ease-in-out infinite;}
@keyframes pulse{0%,100%{opacity:1;}50%{opacity:.6;}}

/* ── TABS ── */
.tabs{display:flex;gap:0;border-bottom:2px solid #1a2d4a;padding:0 16px;background:#060f1e;}
.tab{padding:9px 18px;cursor:pointer;border-bottom:2px solid transparent;
     margin-bottom:-2px;font-size:13px;color:#6a88a8;transition:color .2s,border-color .2s;}
.tab.active{color:#4fc3f7;border-bottom-color:#4fc3f7;font-weight:600;}
.tab:hover:not(.active){color:#a0c4e8;}

/* ── MAIN CONTENT ── */
.content{padding:14px 16px;flex:1;}

/* ── PROGRESS CARDS ── */
.parts-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-bottom:18px;}
.part-card{background:#0d2040;border:1px solid #1f3864;border-radius:10px;padding:12px 14px;}
.part-card .pn{font-size:12px;font-weight:700;color:#4fc3f7;margin-bottom:2px;
               white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.part-card .desc{font-size:11px;color:#6a88a8;margin-bottom:8px;}
.progress-track{height:10px;background:#0a1828;border-radius:10px;overflow:hidden;margin-bottom:4px;}
.progress-fill{height:100%;border-radius:10px;transition:width .6s ease;
               background:linear-gradient(90deg,#1a5276,#1e8449);}
.progress-fill.done{background:linear-gradient(90deg,#1e7145,#27ae60);}
.progress-label{font-size:10px;color:#6a88a8;display:flex;justify-content:space-between;}
.step-dots{display:flex;gap:4px;margin-top:6px;}
.dot{flex:1;height:6px;border-radius:3px;}
.dot.comp{background:#1e8449;}
.dot.proc{background:#e6a817;}
.dot.sin {background:#1a237e;}

/* ── PROCESS SECTIONS ── */
.proc-section{margin-bottom:18px;border:1px solid #1a2d4a;border-radius:10px;overflow:hidden;}
.proc-header{display:flex;align-items:center;gap:10px;padding:10px 14px;
             background:#0d2040;cursor:pointer;user-select:none;}
.proc-header:hover{background:#112244;}
.proc-title{color:#4fc3f7;font-size:15px;font-weight:600;flex:1;}
.drag-handle{cursor:grab;color:#334d66;font-size:18px;padding:0 4px;user-select:none;}
.drag-handle:active{cursor:grabbing;}
.proc-section.drag-over{border-color:#4fc3f7;box-shadow:0 0 0 2px #4fc3f740;}
.proc-stats{display:flex;gap:14px;font-size:12px;}
.stat-chip{padding:2px 9px;border-radius:12px;font-weight:600;}
.chip-sin {background:#1a237e;color:#c5cae9;}
.chip-proc{background:#7b6000;color:#ffe082;}
.chip-comp{background:#1e5631;color:#fff;}
.proc-bar-wrap{padding:4px 14px 6px;background:#0a1828;}
.proc-bar{height:6px;background:#0d2040;border-radius:6px;overflow:hidden;}
.proc-bar-fill{height:100%;background:#e6d17a;border-radius:6px;transition:width .6s;}

/* ── BOTTLENECK ── */
.bottleneck-badge{background:#5a2800;color:#ffb347;border:1px solid #ff6b35;
                  border-radius:12px;padding:1px 8px;font-size:10px;font-weight:700;}

/* ── BULK TOOLBAR (inside proc section) ── */
.bulk-bar{display:flex;align-items:center;gap:10px;padding:6px 14px;
          background:#071a2e;border-top:1px solid #1a2d4a;flex-wrap:wrap;}
.bulk-count{font-size:12px;color:#4fc3f7;font-weight:600;}
.sel-all-btn{font-size:11px;color:#8ba0b8;cursor:pointer;text-decoration:underline;background:none;border:none;}

/* ── TABLE ── */
.tbl-wrap{overflow-x:auto;}
table{width:100%;border-collapse:collapse;font-size:12px;}
th{background:#1a2d4a;color:#8bb8d8;padding:7px 8px;text-align:left;
   position:sticky;top:0;white-space:nowrap;}
td{padding:6px 8px;border-bottom:1px solid #0d1f35;}
tr.comp{background:#1a5c2a;}
tr.proc{background:#3a2f00;}
tr.sin {background:#080e1a;}
tr.date-sep td{background:#0d2040;color:#e6d17a;font-weight:700;font-size:11px;padding:6px 10px;
  border-top:1px solid #1f3864;border-bottom:1px solid #1f3864;}
tr:hover td{background:#0e2035;}
td.cb-cell{width:28px;text-align:center;}
input[type=checkbox]{accent-color:#4fc3f7;width:14px;height:14px;cursor:pointer;}

/* ── INLINE INPUTS ── */
td input[type=text],td input[type=number],td input[type=date],
td input[type=datetime-local],td select{
  background:#0a1828;color:#c5cae9;border:1px solid #1f3864;
  border-radius:4px;padding:3px 6px;font-size:11px;width:100%;
  transition:border-color .2s;}
td input:focus,td select:focus{outline:none;border-color:#4fc3f7;}
td input[type=date]{color-scheme:dark;}
.real-date{color:#7ec8e3 !important;border-color:#2a4a6a !important;}
.cycle-badge{background:#0d2040;color:#e6d17a;border-radius:8px;
             padding:1px 7px;font-size:10px;font-weight:700;white-space:nowrap;}

/* ── MATRIX ── */
.matrix-wrap{overflow-x:auto;margin-top:4px;}
.matrix-wrap table{min-width:500px;}
.matrix-wrap td,.matrix-wrap th{text-align:center;padding:7px 10px;border:1px solid #1a2d4a;}
.matrix-wrap .pn-cell{text-align:left;color:#4fc3f7;font-weight:600;font-size:11px;}
.matrix-wrap .cell-comp{background:#0a1f0f;color:#81c784;}
.matrix-wrap .cell-proc{background:#1a1400;color:#ffe082;}
.matrix-wrap .cell-sin {background:#080e1a;color:#7986cb;}
.matrix-wrap .cell-na  {color:#333d55;}

/* ── CHART ── */
.chart-container{background:#0d2040;border:1px solid #1f3864;border-radius:10px;
                 padding:14px;margin-bottom:16px;}
.chart-title{color:#4fc3f7;font-size:13px;font-weight:600;margin-bottom:10px;}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
canvas{max-height:220px;}

/* ── CYCLE TIME TABLE ── */
.ct-table{width:100%;border-collapse:collapse;font-size:13px;}
.ct-table th{background:#1a2d4a;color:#8bb8d8;padding:8px 12px;text-align:left;}
.ct-table td{padding:8px 12px;border-bottom:1px solid #0d1f35;color:#c5cae9;}
.ct-bar-cell{width:40%;}
.ct-bar-bg{background:#0a1828;border-radius:6px;height:10px;overflow:hidden;}
.ct-bar-fill{height:100%;background:linear-gradient(90deg,#1f3864,#4fc3f7);border-radius:6px;}

/* ── MODAL ── */
.modal-overlay{position:fixed;inset:0;background:#000a;display:flex;
               align-items:center;justify-content:center;z-index:1000;}
.modal{background:#0d2040;border:1px solid #4fc3f7;border-radius:12px;
       padding:24px;min-width:320px;max-width:440px;width:90%;}
.modal h3{color:#e6d17a;margin-bottom:8px;font-size:15px;}
.modal p{color:#8ba0b8;font-size:12px;margin-bottom:14px;}
.modal textarea{width:100%;background:#071529;color:#c5cae9;border:1px solid #1f3864;
                border-radius:6px;padding:8px;font-size:12px;resize:vertical;min-height:70px;}
.modal textarea:focus{outline:none;border-color:#4fc3f7;}
.modal-btns{display:flex;gap:8px;margin-top:14px;justify-content:flex-end;}
.btn-cancel{background:#1a2d4a;color:#8ba0b8;}
.btn-confirm{background:#1e5631;color:#fff;}
.btn-confirm-warn{background:#7b1f1f;color:#fff;}

/* ── REORDER HINT ── */
.reorder-hint{font-size:10px;color:#4a6a88;padding:4px 14px;font-style:italic;}

/* ── FILTER BAR ── */
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;padding:8px 16px;
            background:#081428;border-bottom:1px solid #1a2d4a;align-items:center;}
.filter-bar select,.filter-bar input[type=text]{
  background:#0a1828;color:#c5cae9;border:1px solid #1f3864;
  border-radius:6px;padding:5px 10px;font-size:12px;}
.filter-bar input[type=text]{min-width:200px;}
.filter-clear{font-size:11px;color:#8ba0b8;cursor:pointer;text-decoration:underline;
              background:none;border:none;}

/* ── ADMIN TAB ── */
.admin-section{background:#0d2040;border:1px solid #1f3864;border-radius:10px;
               padding:14px;margin-bottom:16px;}
.admin-section h3{color:#4fc3f7;font-size:14px;margin-bottom:10px;}
.admin-form{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px;align-items:center;}
.admin-form input,.admin-form select{
  background:#0a1828;color:#c5cae9;border:1px solid #1f3864;
  border-radius:6px;padding:6px 10px;font-size:12px;}
.admin-section table{width:100%;}
.admin-section .btn{padding:4px 9px;font-size:11px;}
.steps-panel{display:flex;flex-wrap:wrap;gap:6px;padding:8px 4px;align-items:center;}
.step-chip{display:inline-flex;align-items:center;gap:6px;}
.step-chip .x{cursor:pointer;opacity:.75;}
.step-chip .x:hover{opacity:1;}
.expand-toggle{cursor:pointer;color:#4fc3f7;}
.bom-card{border:1px solid #1a2d4a;border-radius:8px;padding:8px;}
.part-thumb{width:32px;height:32px;object-fit:cover;border-radius:5px;
            border:1px solid #1f3864;cursor:pointer;flex-shrink:0;}
.part-thumb-empty{display:flex;align-items:center;justify-content:center;
                  background:#0a1828;color:#334d66;font-size:14px;}

/* ── RESPONSIVE ── */
@media(max-width:600px){
  .topbar{flex-direction:column;align-items:flex-start;}
  .topbar .kpis{width:100%;}
  .kpi-box{flex:1;}
  .chart-grid{grid-template-columns:1fr;}
  .parts-grid{grid-template-columns:1fr;}
  th,td{padding:5px 5px;font-size:11px;}
  .btn{font-size:11px;padding:6px 10px;}
  .proc-stats{gap:6px;}
  canvas{max-height:180px;}
}</style>
</head>
<body>
<div id="root"></div>
<script>
const h = React.createElement;
const {useState, useEffect, useRef, useCallback} = React;

const STATUS_CLASS = {"Completado":"comp","En Proceso":"proc","Sin Iniciar":"sin"};
const STATUS_DOT   = {"Completado":"comp","En Proceso":"proc","Sin Iniciar":"sin"};
function fmtDT(s){ return s ? s.replace("T"," ") : "—"; }
function fmtMins(m){
  if(!m) return "—";
  if(m<60) return m+"m";
  return Math.floor(m/60)+"h "+Math.round(m%60)+"m";
}

/* ── Efficiency chart ── */
function EffChart({snapshots}){
  const ref=useRef(null); const inst=useRef(null);
  useEffect(()=>{
    if(!snapshots||!snapshots.length) return;
    if(inst.current) inst.current.destroy();
    inst.current=new Chart(ref.current,{
      type:"line",
      data:{labels:snapshots.map(s=>s.date.slice(5)),
            datasets:[{label:"Eficiencia %",data:snapshots.map(s=>s.efficiency),
              borderColor:"#e6d17a",backgroundColor:"rgba(230,209,122,0.12)",
              tension:0.35,fill:true,pointBackgroundColor:"#4fc3f7",pointRadius:3}]},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{display:false},tooltip:{callbacks:{label:ctx=>`${ctx.parsed.y}%`}}},
        scales:{x:{ticks:{color:"#6a88a8",font:{size:10}},grid:{color:"#0d1f35"}},
                y:{ticks:{color:"#6a88a8",font:{size:10},callback:v=>v+"%"},
                   grid:{color:"#0d1f35"},min:0,max:100}}}
    });
    return ()=>{ if(inst.current) inst.current.destroy(); };
  },[snapshots]);
  return h("div",{style:{height:"200px"}},h("canvas",{ref}));
}

/* ── WIP chart ── */
function WipChart({items,processes}){
  const ref=useRef(null); const inst=useRef(null);
  useEffect(()=>{
    if(!items||!processes) return;
    const labels=[],sin_=[],proc_=[],comp_=[];
    processes.forEach(p=>{
      const pi=items.filter(i=>i.process===p);
      labels.push(p);
      sin_.push(pi.filter(i=>i.status==="Sin Iniciar").length);
      proc_.push(pi.filter(i=>i.status==="En Proceso").length);
      comp_.push(pi.filter(i=>i.status==="Completado").length);
    });
    if(inst.current) inst.current.destroy();
    inst.current=new Chart(ref.current,{
      type:"bar",
      data:{labels,datasets:[
        {label:"Sin Iniciar",data:sin_,backgroundColor:"#1a237e"},
        {label:"En Proceso",data:proc_,backgroundColor:"#7b6000"},
        {label:"Completado",data:comp_,backgroundColor:"#1e5631"},
      ]},
      options:{responsive:true,maintainAspectRatio:false,
        plugins:{legend:{labels:{color:"#8bb8d8",font:{size:10}}}},
        scales:{x:{stacked:true,ticks:{color:"#6a88a8",font:{size:10}},grid:{display:false}},
                y:{stacked:true,ticks:{color:"#6a88a8",font:{size:10}},grid:{color:"#0d1f35"}}}}
    });
    return ()=>{ if(inst.current) inst.current.destroy(); };
  },[items,processes]);
  return h("div",{style:{height:"200px"}},h("canvas",{ref}));
}

/* ════════════════════════════════════════
   MODAL — reopen note + bulk confirm
════════════════════════════════════════ */
function Modal({title,message,warn,onConfirm,onCancel,needNote}){
  const [note,setNote]=useState("");
  return h("div",{className:"modal-overlay"},
    h("div",{className:"modal"},
      h("h3",null,title),
      h("p",null,message),
      needNote && h("textarea",{
        placeholder:"Escribe el motivo (obligatorio)...",
        value:note, onChange:e=>setNote(e.target.value)
      }),
      h("div",{className:"modal-btns"},
        h("button",{className:"btn btn-cancel",onClick:onCancel},"Cancelar"),
        h("button",{
          className:"btn "+(warn?"btn-confirm-warn":"btn-confirm"),
          onClick:()=>onConfirm(note),
          disabled: needNote && !note.trim()
        },"Confirmar")
      )
    )
  );
}

/* ════════════════════════════════════════
   CATALOG CRUD — shared helpers
════════════════════════════════════════ */
const JSONH = {"Content-Type":"application/json"};

/* shrink an uploaded image client-side before it goes into tracker_data.json */
function fileToThumbDataURL(file, maxSize){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=reject;
    reader.onload=()=>{
      const img=new Image();
      img.onerror=reject;
      img.onload=()=>{
        const scale=Math.min(1, maxSize/Math.max(img.width,img.height));
        const w=Math.max(1,Math.round(img.width*scale));
        const h=Math.max(1,Math.round(img.height*scale));
        const canvas=document.createElement("canvas");
        canvas.width=w; canvas.height=h;
        canvas.getContext("2d").drawImage(img,0,0,w,h);
        resolve(canvas.toDataURL("image/jpeg",0.8));
      };
      img.src=reader.result;
    };
    reader.readAsDataURL(file);
  });
}

function requestDelete(endpoint, id, label, name, setModal, onDone){
  fetch(`${endpoint}/${id}`,{method:"DELETE"}).then(r=>{
    if(r.status===409){
      r.json().then(e=>{
        const dep = (e.detail && e.detail.dependents) || {};
        const parts = Object.entries(dep).filter(([,v])=>v>0).map(([k,v])=>`${v} ${k}`).join(", ");
        setModal({
          title:`⚠ Eliminar ${label}`,
          message:`"${name}" tiene datos relacionados (${parts||"dependencias"}). Esto también los eliminará. ¿Confirmar?`,
          warn:true, needNote:false,
          onConfirm:()=>{
            setModal(null);
            fetch(`${endpoint}/${id}?force=true`,{method:"DELETE"}).then(()=>onDone());
          },
        });
      });
    } else if(!r.ok){
      r.json().then(e=>alert("⚠ "+(e.detail||"Error al eliminar")));
    } else {
      onDone();
    }
  });
}

/* ════════════════════════════════════════
   FILTER BAR — Cliente / Proyecto / Ensamble / Parte / Proceso
════════════════════════════════════════ */
function FilterBar({data,filters,setFilters}){
  const projOpts = data.projects.filter(p=>!filters.client_id || p.client_id===parseInt(filters.client_id));
  const asmOpts = data.assemblies.filter(a=>{
    if(filters.project_id) return a.project_id===parseInt(filters.project_id);
    if(filters.client_id){
      const projIds=new Set(data.projects.filter(pr=>pr.client_id===parseInt(filters.client_id)).map(pr=>pr.id));
      return projIds.has(a.project_id);
    }
    return true;
  });
  const partOpts = filters.assembly_id
    ? data.parts.filter(p=>data.assembly_parts.some(ap=>ap.assembly_id===parseInt(filters.assembly_id)&&ap.part_id===p.id))
    : data.parts;
  const active = filters.client_id||filters.project_id||filters.assembly_id||filters.part_id||filters.process_id||filters.search;
  const clear = ()=>setFilters({client_id:"",project_id:"",assembly_id:"",part_id:"",process_id:"",search:""});

  return h("div",{className:"filter-bar"},
    h("select",{value:filters.client_id,
      onChange:e=>setFilters({...filters,client_id:e.target.value,project_id:"",assembly_id:"",part_id:""})},
      h("option",{value:""},"Todos los Clientes"),
      data.clients.map(c=>h("option",{key:c.id,value:c.id},c.name))),
    h("select",{value:filters.project_id,
      onChange:e=>setFilters({...filters,project_id:e.target.value,assembly_id:"",part_id:""})},
      h("option",{value:""},"Todos los Proyectos"),
      projOpts.map(p=>h("option",{key:p.id,value:p.id},p.name))),
    h("select",{value:filters.assembly_id,
      onChange:e=>setFilters({...filters,assembly_id:e.target.value,part_id:""})},
      h("option",{value:""},"Todos los Ensambles"),
      asmOpts.map(a=>h("option",{key:a.id,value:a.id},a.part_number))),
    h("select",{value:filters.part_id,
      onChange:e=>setFilters({...filters,part_id:e.target.value})},
      h("option",{value:""},"Todas las Partes"),
      partOpts.map(p=>h("option",{key:p.id,value:p.id},p.part_number))),
    h("select",{value:filters.process_id,
      onChange:e=>setFilters({...filters,process_id:e.target.value})},
      h("option",{value:""},"Todos los Procesos"),
      data.process_catalog.map(p=>h("option",{key:p.id,value:p.id},p.name))),
    h("input",{type:"text",placeholder:"Buscar parte, ensamble o descripción...",value:filters.search,
      onChange:e=>setFilters({...filters,search:e.target.value})}),
    active && h("button",{className:"filter-clear",onClick:clear},"✕ Limpiar filtros")
  );
}

/* ════════════════════════════════════════
   ADMIN — Clientes
════════════════════════════════════════ */
function ClientsAdmin({clients,projects,reload,setModal}){
  const [form,setForm]=useState({name:"",contact:"",notes:""});
  const [editingId,setEditingId]=useState(null);
  const [editForm,setEditForm]=useState({});
  const projCount = cid => projects.filter(p=>p.client_id===cid).length;

  const submit=()=>{
    if(!form.name.trim()) return;
    fetch("/api/clients",{method:"POST",headers:JSONH,body:JSON.stringify(form)})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setForm({name:"",contact:"",notes:""}); reload(); } });
  };
  const startEdit = c=>{ setEditingId(c.id); setEditForm({name:c.name,contact:c.contact,notes:c.notes}); };
  const saveEdit=()=>{
    fetch(`/api/clients/${editingId}`,{method:"PUT",headers:JSONH,body:JSON.stringify(editForm)})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setEditingId(null); reload(); } });
  };
  const del = c=>requestDelete("/api/clients", c.id, "Cliente", c.name, setModal, reload);

  return h("div",{className:"admin-section"},
    h("h3",null,"👤 Clientes"),
    h("div",{className:"admin-form"},
      h("input",{placeholder:"Nombre",value:form.name,onChange:e=>setForm({...form,name:e.target.value})}),
      h("input",{placeholder:"Contacto",value:form.contact,onChange:e=>setForm({...form,contact:e.target.value})}),
      h("input",{placeholder:"Notas",value:form.notes,onChange:e=>setForm({...form,notes:e.target.value})}),
      h("button",{className:"btn btn-bulk",onClick:submit},"+ Nuevo Cliente")
    ),
    h("div",{className:"tbl-wrap"},h("table",null,
      h("thead",null,h("tr",null,["Nombre","Contacto","Notas","Proyectos",""].map(cl=>h("th",{key:cl},cl)))),
      h("tbody",null,clients.map(c=>
        editingId===c.id
          ? h("tr",{key:c.id},
              h("td",null,h("input",{value:editForm.name,onChange:e=>setEditForm({...editForm,name:e.target.value})})),
              h("td",null,h("input",{value:editForm.contact,onChange:e=>setEditForm({...editForm,contact:e.target.value})})),
              h("td",null,h("input",{value:editForm.notes,onChange:e=>setEditForm({...editForm,notes:e.target.value})})),
              h("td",null,projCount(c.id)),
              h("td",null,
                h("button",{className:"btn btn-bulk",onClick:saveEdit},"Guardar"),
                h("button",{className:"btn btn-cancel",onClick:()=>setEditingId(null)},"Cancelar")))
          : h("tr",{key:c.id},
              h("td",null,c.name), h("td",null,c.contact||"—"), h("td",null,c.notes||"—"),
              h("td",null,projCount(c.id)),
              h("td",null,
                h("button",{className:"btn btn-upload",onClick:()=>startEdit(c)},"✎"),
                h("button",{className:"btn btn-pdf",onClick:()=>del(c)},"🗑")))
      ))
    ))
  );
}

/* ════════════════════════════════════════
   ADMIN — Proyectos
════════════════════════════════════════ */
function ProjectsAdmin({projects,clients,assemblies,reload,setModal}){
  const [form,setForm]=useState({client_id:"",name:"",notes:""});
  const [editingId,setEditingId]=useState(null);
  const [editForm,setEditForm]=useState({});
  const clientName = id => (clients.find(c=>c.id===id)||{}).name || "—";
  const asmCount  = pid => assemblies.filter(a=>a.project_id===pid).length;

  const submit=()=>{
    if(!form.client_id||!form.name.trim()) return;
    fetch("/api/projects",{method:"POST",headers:JSONH,
      body:JSON.stringify({...form,client_id:parseInt(form.client_id)})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setForm({client_id:"",name:"",notes:""}); reload(); } });
  };
  const startEdit = p=>{ setEditingId(p.id); setEditForm({client_id:p.client_id,name:p.name,notes:p.notes}); };
  const saveEdit=()=>{
    fetch(`/api/projects/${editingId}`,{method:"PUT",headers:JSONH,
      body:JSON.stringify({...editForm,client_id:parseInt(editForm.client_id)})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setEditingId(null); reload(); } });
  };
  const del = p=>requestDelete("/api/projects", p.id, "Proyecto", p.name, setModal, reload);

  return h("div",{className:"admin-section"},
    h("h3",null,"📁 Proyectos"),
    h("div",{className:"admin-form"},
      h("select",{value:form.client_id,onChange:e=>setForm({...form,client_id:e.target.value})},
        h("option",{value:""},"Cliente..."),
        clients.map(c=>h("option",{key:c.id,value:c.id},c.name))),
      h("input",{placeholder:"Nombre del proyecto",value:form.name,onChange:e=>setForm({...form,name:e.target.value})}),
      h("input",{placeholder:"Notas",value:form.notes,onChange:e=>setForm({...form,notes:e.target.value})}),
      h("button",{className:"btn btn-bulk",onClick:submit},"+ Nuevo Proyecto")
    ),
    h("div",{className:"tbl-wrap"},h("table",null,
      h("thead",null,h("tr",null,["Nombre","Cliente","Notas","Ensambles",""].map(cl=>h("th",{key:cl},cl)))),
      h("tbody",null,projects.map(p=>
        editingId===p.id
          ? h("tr",{key:p.id},
              h("td",null,h("input",{value:editForm.name,onChange:e=>setEditForm({...editForm,name:e.target.value})})),
              h("td",null,h("select",{value:editForm.client_id,onChange:e=>setEditForm({...editForm,client_id:e.target.value})},
                clients.map(c=>h("option",{key:c.id,value:c.id},c.name)))),
              h("td",null,h("input",{value:editForm.notes,onChange:e=>setEditForm({...editForm,notes:e.target.value})})),
              h("td",null,asmCount(p.id)),
              h("td",null,
                h("button",{className:"btn btn-bulk",onClick:saveEdit},"Guardar"),
                h("button",{className:"btn btn-cancel",onClick:()=>setEditingId(null)},"Cancelar")))
          : h("tr",{key:p.id},
              h("td",null,p.name), h("td",null,clientName(p.client_id)), h("td",null,p.notes||"—"),
              h("td",null,asmCount(p.id)),
              h("td",null,
                h("button",{className:"btn btn-upload",onClick:()=>startEdit(p)},"✎"),
                h("button",{className:"btn btn-pdf",onClick:()=>del(p)},"🗑")))
      ))
    ))
  );
}

/* ════════════════════════════════════════
   ADMIN — Ensambles (número de parte principal)
   Cada ensamble tiene sus propias partes asignadas (BOM),
   y cada parte asignada tiene sus propios procesos.
════════════════════════════════════════ */
function AssembliesAdmin({assemblies,projects,clients,parts,assemblyParts,items,processes,reload,setModal}){
  const [form,setForm]=useState({project_id:"",part_number:"",description:"",qty_ordered:""});
  const [editingId,setEditingId]=useState(null);
  const [editForm,setEditForm]=useState({});
  const [expanded,setExpanded]=useState(null);          // assembly id expandido
  const [expandedPart,setExpandedPart]=useState(null);  // assembly_part id expandido
  const [bomForm,setBomForm]=useState({});
  const [addProc,setAddProc]=useState({});
  const [qtyEdits,setQtyEdits]=useState({});  // { [assembly_part_id]: "new qty being typed" }

  const projName = id => (projects.find(p=>p.id===id)||{}).name || "—";
  const partsFor = aid => assemblyParts.filter(ap=>ap.assembly_id===aid);
  const partInfo = pid => parts.find(p=>p.id===pid) || {};
  const stepsFor = apid => items.filter(i=>i.assembly_part_id===apid).sort((a,b)=>(a.seq??0)-(b.seq??0));

  const submit=()=>{
    if(!form.project_id||!form.part_number.trim()||!form.qty_ordered) return;
    fetch("/api/assemblies",{method:"POST",headers:JSONH,body:JSON.stringify({
      project_id:parseInt(form.project_id), part_number:form.part_number.trim(),
      description:form.description, qty_ordered:parseInt(form.qty_ordered),
    })}).then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
      else { setForm({project_id:"",part_number:"",description:"",qty_ordered:""}); reload(); } });
  };
  const startEdit = a=>{
    setEditingId(a.id);
    setEditForm({project_id:a.project_id,part_number:a.part_number,description:a.description,qty_ordered:a.qty_ordered});
  };
  const saveEdit=()=>{
    fetch(`/api/assemblies/${editingId}`,{method:"PUT",headers:JSONH,body:JSON.stringify({
      project_id:parseInt(editForm.project_id), part_number:editForm.part_number,
      description:editForm.description, qty_ordered:parseInt(editForm.qty_ordered),
    })}).then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
      else { setEditingId(null); reload(); } });
  };
  const del = a=>requestDelete("/api/assemblies", a.id, "Ensamble", a.part_number, setModal, reload);

  const setBom = (aid,patch)=>setBomForm({...bomForm,
    [aid]:{...(bomForm[aid]||{mode:"existing",part_id:"",new_pn:"",new_desc:"",qty:""}),...patch}});

  const addPart = aid=>{
    const bf  = bomForm[aid]||{};
    const qty = parseInt(bf.qty);
    if(!qty) return;
    const go = partId => fetch(`/api/assemblies/${aid}/parts`,{method:"POST",headers:JSONH,
        body:JSON.stringify({part_id:partId, qty_ordered:qty})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setBomForm({...bomForm,[aid]:null}); reload(); } });
    if(bf.mode==="new"){
      if(!bf.new_pn||!bf.new_pn.trim()) return;
      fetch("/api/parts",{method:"POST",headers:JSONH,
        body:JSON.stringify({part_number:bf.new_pn.trim(), description:bf.new_desc||""})})
        .then(r=>r.json().then(p=>{ if(!r.ok) alert("⚠ "+p.detail); else go(p.id); }));
    } else {
      if(!bf.part_id) return;
      go(parseInt(bf.part_id));
    }
  };
  const delPart = ap=>requestDelete("/api/assembly-parts", ap.id, "Parte asignada", partInfo(ap.part_id).part_number, setModal, reload);

  const saveQty = ap=>{
    const qty = parseInt(qtyEdits[ap.id]);
    if(!qty || qty===ap.qty_ordered){ setQtyEdits({...qtyEdits,[ap.id]:undefined}); return; }
    fetch(`/api/assembly-parts/${ap.id}`,{method:"PUT",headers:JSONH,body:JSON.stringify({qty_ordered:qty})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setQtyEdits({...qtyEdits,[ap.id]:undefined}); reload(); } });
  };

  const addStep = apId=>{
    const pid = addProc[apId];
    if(!pid) return;
    fetch(`/api/assembly-parts/${apId}/steps`,{method:"POST",headers:JSONH,body:JSON.stringify({process_id:parseInt(pid)})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setAddProc({...addProc,[apId]:""}); reload(); } });
  };
  const delStep = step=>requestDelete("/api/steps", step.id, "Paso de proceso", step.process, setModal, reload);

  return h("div",{className:"admin-section"},
    h("h3",null,"🧩 Ensambles (números de parte principales)"),
    h("div",{className:"admin-form"},
      h("select",{value:form.project_id,onChange:e=>setForm({...form,project_id:e.target.value})},
        h("option",{value:""},"Proyecto..."),
        projects.map(p=>h("option",{key:p.id,value:p.id},
          `${p.name} (${(clients.find(c=>c.id===p.client_id)||{}).name||""})`))),
      h("input",{placeholder:"Número de Ensamble",value:form.part_number,
        onChange:e=>setForm({...form,part_number:e.target.value})}),
      h("input",{placeholder:"Descripción",value:form.description,
        onChange:e=>setForm({...form,description:e.target.value})}),
      h("input",{type:"number",placeholder:"Cantidad",style:{width:90},value:form.qty_ordered,
        onChange:e=>setForm({...form,qty_ordered:e.target.value})}),
      h("button",{className:"btn btn-bulk",onClick:submit},"+ Nuevo Ensamble")
    ),
    h("div",{className:"tbl-wrap"},h("table",null,
      h("thead",null,h("tr",null,["Ensamble","Descripción","Proyecto","Qty","Partes",""].map(cl=>h("th",{key:cl},cl)))),
      h("tbody",null,assemblies.map(a=>{
        const isEditing  = editingId===a.id;
        const isExpanded = expanded===a.id;
        const aps        = partsFor(a.id);
        const rows = [];
        rows.push(
          isEditing
            ? h("tr",{key:a.id},
                h("td",null,h("input",{value:editForm.part_number,
                  onChange:e=>setEditForm({...editForm,part_number:e.target.value})})),
                h("td",null,h("input",{value:editForm.description,
                  onChange:e=>setEditForm({...editForm,description:e.target.value})})),
                h("td",null,h("select",{value:editForm.project_id,
                  onChange:e=>setEditForm({...editForm,project_id:e.target.value})},
                  projects.map(pr=>h("option",{key:pr.id,value:pr.id},pr.name)))),
                h("td",null,h("input",{type:"number",style:{width:70},value:editForm.qty_ordered,
                  onChange:e=>setEditForm({...editForm,qty_ordered:e.target.value})})),
                h("td",null,aps.length),
                h("td",null,
                  h("button",{className:"btn btn-bulk",onClick:saveEdit},"Guardar"),
                  h("button",{className:"btn btn-cancel",onClick:()=>setEditingId(null)},"Cancelar")))
            : h("tr",{key:a.id},
                h("td",null,a.part_number), h("td",null,a.description||"—"),
                h("td",null,projName(a.project_id)), h("td",null,a.qty_ordered),
                h("td",{className:"expand-toggle",onClick:()=>setExpanded(isExpanded?null:a.id)},
                  `${aps.length} ${isExpanded?"▲":"▼"}`),
                h("td",null,
                  h("button",{className:"btn btn-upload",onClick:()=>startEdit(a)},"✎"),
                  h("button",{className:"btn btn-pdf",onClick:()=>del(a)},"🗑")))
        );
        if(isExpanded){
          const usedPartIds    = new Set(aps.map(ap=>ap.part_id));
          const availableParts = parts.filter(p=>!usedPartIds.has(p.id));
          const bf = bomForm[a.id]||{mode:"existing",part_id:"",new_pn:"",new_desc:"",qty:""};
          rows.push(h("tr",{key:a.id+"-parts"},
            h("td",{colSpan:6},
              h("div",{style:{display:"flex",flexDirection:"column",gap:8,padding:"6px 4px"}},
                aps.map(ap=>{
                  const pinfo = partInfo(ap.part_id);
                  const isPartExpanded = expandedPart===ap.id;
                  const steps = stepsFor(ap.id);
                  const availableProcs = processes.filter(pr=>!steps.some(s=>s.process_id===pr.id));
                  return h("div",{key:ap.id,className:"bom-card"},
                    h("div",{style:{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}},
                      h("span",{style:{color:"#4fc3f7",fontWeight:700}},pinfo.part_number),
                      h("span",{style:{color:"#6a88a8",fontSize:11}},pinfo.description||""),
                      h("span",{style:{fontSize:11,color:"#8ba0b8",display:"flex",alignItems:"center",gap:4}},
                        "Qty a producir:",
                        h("input",{type:"number",style:{width:70},
                          value:qtyEdits[ap.id]!==undefined?qtyEdits[ap.id]:ap.qty_ordered,
                          onChange:e=>setQtyEdits({...qtyEdits,[ap.id]:e.target.value})}),
                        qtyEdits[ap.id]!==undefined&&qtyEdits[ap.id]!=String(ap.qty_ordered)&&
                          h("button",{className:"btn btn-bulk",style:{padding:"2px 8px"},
                            onClick:()=>saveQty(ap)},"Guardar")
                      ),
                      h("span",{className:"expand-toggle",onClick:()=>setExpandedPart(isPartExpanded?null:ap.id)},
                        `${steps.length} proceso(s) ${isPartExpanded?"▲":"▼"}`),
                      h("button",{className:"btn btn-pdf",style:{padding:"2px 8px"},onClick:()=>delPart(ap)},"🗑")
                    ),
                    isPartExpanded && h("div",{className:"steps-panel"},
                      steps.map(s=>h("span",{key:s.id,className:"stat-chip chip-"+(STATUS_CLASS[s.status]||"sin")+" step-chip"},
                        h("span",null,`${s.seq}. ${s.process}`),
                        h("span",{className:"x",onClick:()=>delStep(s)},"✕")
                      )),
                      h("select",{value:addProc[ap.id]||"",
                        onChange:e=>setAddProc({...addProc,[ap.id]:e.target.value})},
                        h("option",{value:""},"Agregar proceso..."),
                        availableProcs.map(pr=>h("option",{key:pr.id,value:pr.id},pr.name))),
                      h("button",{className:"btn btn-bulk",onClick:()=>addStep(ap.id)},"+ Agregar")
                    )
                  );
                }),
                h("div",{style:{display:"flex",gap:8,flexWrap:"wrap",alignItems:"center",
                  borderTop:"1px dashed #1a2d4a",paddingTop:8}},
                  h("select",{value:bf.mode,onChange:e=>setBom(a.id,{mode:e.target.value})},
                    h("option",{value:"existing"},"Usar parte existente (común)"),
                    h("option",{value:"new"},"Crear parte nueva")),
                  bf.mode==="existing"
                    ? h("select",{value:bf.part_id,onChange:e=>setBom(a.id,{part_id:e.target.value})},
                        h("option",{value:""},"Parte..."),
                        availableParts.map(p=>h("option",{key:p.id,value:p.id},
                          `${p.part_number}${p.description?" — "+p.description:""}`)))
                    : h(React.Fragment,null,
                        h("input",{placeholder:"Número de Parte",value:bf.new_pn||"",
                          onChange:e=>setBom(a.id,{new_pn:e.target.value})}),
                        h("input",{placeholder:"Descripción",value:bf.new_desc||"",
                          onChange:e=>setBom(a.id,{new_desc:e.target.value})})
                      ),
                  h("input",{type:"number",placeholder:"Cantidad",style:{width:90},value:bf.qty||"",
                    onChange:e=>setBom(a.id,{qty:e.target.value})}),
                  h("button",{className:"btn btn-bulk",onClick:()=>addPart(a.id)},"+ Asignar Parte")
                )
              )
            )
          ));
        }
        return rows;
      }).flat())
    ))
  );
}

/* ════════════════════════════════════════
   ADMIN — Catálogo global de Partes
   (reutilizables entre varios ensambles / proyectos)
════════════════════════════════════════ */
function PartsAdmin({parts,assemblyParts,assemblies,reload,setModal}){
  const [form,setForm]=useState({part_number:"",description:""});
  const [editingId,setEditingId]=useState(null);
  const [editForm,setEditForm]=useState({});
  const usageAssemblies = pid => assemblyParts.filter(ap=>ap.part_id===pid)
    .map(ap=>(assemblies.find(a=>a.id===ap.assembly_id)||{}).part_number).filter(Boolean);

  const submit=()=>{
    if(!form.part_number.trim()) return;
    fetch("/api/parts",{method:"POST",headers:JSONH,body:JSON.stringify(form)})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setForm({part_number:"",description:""}); reload(); } });
  };
  const startEdit = p=>{ setEditingId(p.id); setEditForm({part_number:p.part_number,description:p.description}); };
  const saveEdit=()=>{
    fetch(`/api/parts/${editingId}`,{method:"PUT",headers:JSONH,body:JSON.stringify(editForm)})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setEditingId(null); reload(); } });
  };
  const del = p=>requestDelete("/api/parts", p.id, "Parte", p.part_number, setModal, reload);

  const fileInputs = useRef({});
  const pickImage = pid => fileInputs.current[pid] && fileInputs.current[pid].click();
  const onImageChosen = (pid,e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if(!file) return;
    fileToThumbDataURL(file, 200).then(dataUrl=>
      fetch(`/api/parts/${pid}/image`,{method:"PUT",headers:JSONH,body:JSON.stringify({image:dataUrl})})
        .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail)); else reload(); })
    );
  };
  const removeImage = pid =>
    fetch(`/api/parts/${pid}/image`,{method:"PUT",headers:JSONH,body:JSON.stringify({image:null})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail)); else reload(); });

  return h("div",{className:"admin-section"},
    h("h3",null,"🔩 Catálogo de Partes (reutilizables entre ensambles)"),
    h("p",{style:{color:"#6a88a8",fontSize:11,marginTop:-4,marginBottom:10}},
      "Estas partes son globales: la misma parte puede asignarse a varios ensambles o proyectos "
      +"distintos y su avance se sigue por separado en cada uno. La miniatura que subas aquí "
      +"también se muestra junto a la parte en la pestaña Procesos."),
    h("div",{className:"admin-form"},
      h("input",{placeholder:"Número de Parte",value:form.part_number,
        onChange:e=>setForm({...form,part_number:e.target.value})}),
      h("input",{placeholder:"Descripción",value:form.description,
        onChange:e=>setForm({...form,description:e.target.value})}),
      h("button",{className:"btn btn-bulk",onClick:submit},"+ Nueva Parte")
    ),
    h("div",{className:"tbl-wrap"},h("table",null,
      h("thead",null,h("tr",null,["Img","Parte","Descripción","Usada en",""].map(cl=>h("th",{key:cl},cl)))),
      h("tbody",null,parts.map(p=>{
        const used = usageAssemblies(p.id);
        const imgCell = h("td",null,
          h("input",{type:"file",accept:"image/*",style:{display:"none"},
            ref:el=>fileInputs.current[p.id]=el, onChange:e=>onImageChosen(p.id,e)}),
          h("div",{style:{display:"flex",alignItems:"center",gap:4}},
            p.image
              ? h("img",{src:p.image,className:"part-thumb",onClick:()=>pickImage(p.id)})
              : h("div",{className:"part-thumb part-thumb-empty",onClick:()=>pickImage(p.id)},"📷"),
            p.image && h("span",{className:"x",style:{cursor:"pointer",fontSize:11,color:"#8ba0b8"},
              onClick:()=>removeImage(p.id)},"✕")
          )
        );
        return editingId===p.id
          ? h("tr",{key:p.id},
              imgCell,
              h("td",null,h("input",{value:editForm.part_number,
                onChange:e=>setEditForm({...editForm,part_number:e.target.value})})),
              h("td",null,h("input",{value:editForm.description,
                onChange:e=>setEditForm({...editForm,description:e.target.value})})),
              h("td",null,used.length),
              h("td",null,
                h("button",{className:"btn btn-bulk",onClick:saveEdit},"Guardar"),
                h("button",{className:"btn btn-cancel",onClick:()=>setEditingId(null)},"Cancelar")))
          : h("tr",{key:p.id},
              imgCell,
              h("td",null,p.part_number), h("td",null,p.description||"—"),
              h("td",null,used.length ? `${used.length} ensamble(s): ${used.join(", ")}` : "—"),
              h("td",null,
                h("button",{className:"btn btn-upload",onClick:()=>startEdit(p)},"✎"),
                h("button",{className:"btn btn-pdf",onClick:()=>del(p)},"🗑")));
      }))
    ))
  );
}

/* ════════════════════════════════════════
   ADMIN — Procesos (catálogo)
════════════════════════════════════════ */
function ProcessesAdmin({processes,items,reload,setModal}){
  const [name,setName]=useState("");
  const [editingId,setEditingId]=useState(null);
  const [editName,setEditName]=useState("");
  const usage = pid => items.filter(i=>i.process_id===pid).length;

  const submit=()=>{
    if(!name.trim()) return;
    fetch("/api/processes",{method:"POST",headers:JSONH,body:JSON.stringify({name})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setName(""); reload(); } });
  };
  const saveEdit=()=>{
    fetch(`/api/processes/${editingId}`,{method:"PUT",headers:JSONH,body:JSON.stringify({name:editName})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setEditingId(null); reload(); } });
  };
  const del = p=>requestDelete("/api/processes", p.id, "Proceso", p.name, setModal, reload);

  return h("div",{className:"admin-section"},
    h("h3",null,"⚙ Procesos"),
    h("div",{className:"admin-form"},
      h("input",{placeholder:"Nombre del proceso",value:name,onChange:e=>setName(e.target.value)}),
      h("button",{className:"btn btn-bulk",onClick:submit},"+ Nuevo Proceso")
    ),
    h("div",{className:"tbl-wrap"},h("table",null,
      h("thead",null,h("tr",null,["Nombre","En uso",""].map(cl=>h("th",{key:cl},cl)))),
      h("tbody",null,processes.map(p=>
        editingId===p.id
          ? h("tr",{key:p.id},
              h("td",null,h("input",{value:editName,onChange:e=>setEditName(e.target.value)})),
              h("td",null,usage(p.id)),
              h("td",null,
                h("button",{className:"btn btn-bulk",onClick:saveEdit},"Guardar"),
                h("button",{className:"btn btn-cancel",onClick:()=>setEditingId(null)},"Cancelar")))
          : h("tr",{key:p.id},
              h("td",null,p.name), h("td",null,usage(p.id)),
              h("td",null,
                h("button",{className:"btn btn-upload",onClick:()=>{setEditingId(p.id);setEditName(p.name);}},"✎"),
                h("button",{className:"btn btn-pdf",onClick:()=>del(p)},"🗑")))
      ))
    ))
  );
}

/* ════════════════════════════════════════
   ADMIN TAB — wraps the 5 catalog sections
════════════════════════════════════════ */
function AdminTab({data,reload,setModal}){
  return h("div",null,
    h(ClientsAdmin,{clients:data.clients, projects:data.projects, reload, setModal}),
    h(ProjectsAdmin,{projects:data.projects, clients:data.clients, assemblies:data.assemblies, reload, setModal}),
    h(AssembliesAdmin,{assemblies:data.assemblies, projects:data.projects, clients:data.clients,
      parts:data.parts, assemblyParts:data.assembly_parts, items:data.items,
      processes:data.process_catalog, reload, setModal}),
    h(PartsAdmin,{parts:data.parts, assemblyParts:data.assembly_parts, assemblies:data.assemblies, reload, setModal}),
    h(ProcessesAdmin,{processes:data.process_catalog, items:data.items, reload, setModal}),
  );
}

/* ════════════════════════════════════════
   MAIN APP
════════════════════════════════════════ */
function App(){
  const [data,    setData  ]=useState(null);
  const [alerts,  setAlerts]=useState([]);
  const [open,    setOpen  ]=useState({});
  const [groupByDate,setGroupByDate]=useState({});  // {procName: bool} — agrupar filas por fecha
  const [file,    setFile  ]=useState(null);
  const [tab,     setTab   ]=useState("procesos");
  // bulk
  const [selected,setSelected]=useState({});  // {procName: Set<id>}
  // modal
  const [modal,   setModal ]=useState(null);  // {title,message,warn,needNote,onConfirm}
  // drag-and-drop reorder
  const [procOrder,setProcOrder]=useState(null);  // null = use data.processes
  const dragSrc=useRef(null);
  const fileInputRef=useRef(null);
  // filters
  const [filters,setFilters]=useState({client_id:"",project_id:"",assembly_id:"",part_id:"",process_id:"",search:""});

  const load=useCallback(()=>{
    fetch("/api/data").then(r=>r.json()).then(d=>{
      setData(d);
      if(!procOrder) setProcOrder(d.processes);
    });
    fetch("/api/alerts").then(r=>r.json()).then(d=>setAlerts(d.alerts||[]));
  },[procOrder]);

  useEffect(()=>{ load(); const id=setInterval(load,30000); return ()=>clearInterval(id); },[]);

  const upload=()=>{
    if(!file) return;
    const f=new FormData(); f.append("file",file);
    fetch("/upload",{method:"POST",body:f})
      .then(r=>r.json().then(res=>({ok:r.ok,res})))
      .then(({ok,res})=>{
        if(!ok){ alert("⚠ No se pudo cargar el archivo:\n"+(res.detail||"Error desconocido")); return; }
        setFile(null);
        if(fileInputRef.current) fileInputRef.current.value="";
        setProcOrder(null);
        load();
        alert(`✅ Archivo cargado con éxito: ${res.assemblies} ensamble(s), ${res.parts} parte(s), ${res.steps} paso(s) de proceso.`);
      })
      .catch(()=>alert("⚠ No se pudo conectar con el servidor para subir el archivo."));
  };

  /* ── single field update with reopen-note intercept ── */
  const updateField=(item,field,val)=>{
    const u={...item,[field]:val};
    const isReopening = item.status==="Completado" && u.status!=="Completado";
    const doUpdate=(reopenNote="")=>{
      fetch("/api/update",{method:"PUT",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          id:u.id, planned_start:u.planned_start||"", planned_end:u.planned_end||"",
          actual_start:u.actual_start||"", actual_end:u.actual_end||"",
          qty_completed:parseInt(u.qty_completed)||0,
          status:u.status, notes:u.notes||"", reopen_note:reopenNote
        })
      }).then(r=>{
        if(!r.ok) r.json().then(e=>{
          if(e.detail==="REOPEN_NOTE_REQUIRED") return; // modal handles it
          alert("⚠ "+e.detail);
        });
        else load();
      });
    };
    if(isReopening){
      setModal({
        title:"⚠ Reabrir proceso",
        message:`Vas a regresar "${item.process}" de Completado. Indica el motivo.`,
        warn:true, needNote:true,
        onConfirm:(note)=>{ setModal(null); doUpdate(note); },
      });
    } else { doUpdate(); }
  };

  /* ── bulk update ── */
  const bulkAction=(proc,status)=>{
    const ids=[...( selected[proc]||new Set())];
    if(!ids.length) return;
    const procItems=(data?.items||[]).filter(i=>i.process===proc&&ids.includes(i.id));
    const hasCompleted=procItems.some(i=>i.status==="Completado");
    const isReopening=hasCompleted && status!=="Completado";
    const doIt=(reopenNote="")=>{
      fetch("/api/bulk-update",{method:"PUT",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ids,status,reopen_note:reopenNote})
      }).then(r=>{
        if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail));
        else { setSelected(s=>({...s,[proc]:new Set()})); load(); }
      });
    };
    if(isReopening){
      setModal({
        title:"⚠ Reabrir en lote",
        message:`${ids.length} item(s) Completado(s) serán regresados. Indica el motivo.`,
        warn:true, needNote:true,
        onConfirm:(note)=>{ setModal(null); doIt(note); },
      });
    } else {
      setModal({
        title:"Actualizar en lote",
        message:`Marcar ${ids.length} item(s) como "${status}". ¿Confirmar?`,
        warn:false, needNote:false,
        onConfirm:()=>{ setModal(null); doIt(); },
      });
    }
  };

  /* ── drag-and-drop reorder ── */
  const onDragStart=(e,proc)=>{ dragSrc.current=proc; e.dataTransfer.effectAllowed="move"; };
  const onDragOver=(e,proc)=>{ e.preventDefault(); };
  const onDrop=(e,targetProc)=>{
    e.preventDefault();
    const src=dragSrc.current;
    if(!src||src===targetProc) return;
    const order=[...(procOrder||data.processes)];
    const from=order.indexOf(src); const to=order.indexOf(targetProc);
    if(from<0||to<0) return;
    order.splice(from,1); order.splice(to,0,src);
    setProcOrder(order);
  };

  /* ── date grouping helpers (Procesos tab) ── */
  const dateOf = it => (it.planned_start || it.actual_start || "").slice(0,10) || "Sin fecha";
  const fmtDateSep = dk => dk==="Sin fecha" ? "📅 Sin fecha" :
    "📅 " + new Date(dk+"T00:00:00").toLocaleDateString("es-MX",
      {weekday:"long", day:"2-digit", month:"short", year:"numeric"});

  /* ── move a row up/down within its process section (work order) ──
     when grouped by date, a row can't cross into a different day's group ── */
  const moveRow=(displayItems,itemId,dir,constrainToDate)=>{
    const arr=[...displayItems];
    const idx=arr.findIndex(i=>i.id===itemId);
    const swapIdx=idx+dir;
    if(idx<0||swapIdx<0||swapIdx>=arr.length) return;
    if(constrainToDate && dateOf(arr[idx])!==dateOf(arr[swapIdx])) return;
    [arr[idx],arr[swapIdx]]=[arr[swapIdx],arr[idx]];
    fetch("/api/reorder-priority",{method:"PUT",headers:JSONH,
      body:JSON.stringify({ordered_ids:arr.map(i=>i.id)})})
      .then(r=>{ if(!r.ok) r.json().then(e=>alert("⚠ "+e.detail)); else load(); });
  };

  if(!data) return h("div",{style:{padding:40,color:"#4fc3f7"}},"Cargando...");

  const displayProcs = procOrder || data.processes;
  const alertSet=new Set(alerts.map(a=>a.process));
  const partImgById={};
  data.parts.forEach(p=>{ if(p.image) partImgById[p.id]=p.image; });

  /* ── filtering ── */
  const filteredItems = data.items.filter(i=>{
    if(filters.client_id   && i.client_id   !== parseInt(filters.client_id))   return false;
    if(filters.project_id  && i.project_id  !== parseInt(filters.project_id))  return false;
    if(filters.assembly_id && i.assembly_id !== parseInt(filters.assembly_id)) return false;
    if(filters.part_id     && i.part_id     !== parseInt(filters.part_id))     return false;
    if(filters.process_id  && i.process_id  !== parseInt(filters.process_id))  return false;
    if(filters.search){
      const s=filters.search.toLowerCase();
      if(!(i.part_number||"").toLowerCase().includes(s)
         && !(i.assembly_number||"").toLowerCase().includes(s)
         && !(i.description||"").toLowerCase().includes(s)) return false;
    }
    return true;
  });
  const visibleProcs = displayProcs.filter(p=>filteredItems.some(i=>i.process===p));

  /* build maps */
  const procMap={};
  filteredItems.forEach(i=>{
    if(!procMap[i.process]) procMap[i.process]=[];
    procMap[i.process].push(i);
  });
  // sort each proc's items by priority (manual work order within that process,
  // independent of "seq" which only gates cross-process progression)
  Object.values(procMap).forEach(arr=>arr.sort((a,b)=>(a.priority??a.id)-(b.priority??b.id)));

  // grouped by assembly_part_id (NOT by raw part_number) so a shared part
  // tracked in two different assemblies never mixes its progress together
  const partsMap={};
  filteredItems.forEach(i=>{
    if(!partsMap[i.assembly_part_id]) partsMap[i.assembly_part_id]=[];
    partsMap[i.assembly_part_id].push(i);
  });
  Object.values(partsMap).forEach(arr=>arr.sort((a,b)=>(a.seq??a.id)-(b.seq??b.id)));

  /* topbar KPIs — recomputed from the currently filtered items */
  const kParts = new Set(filteredItems.map(i=>i.assembly_part_id));
  const kComp  = new Set(filteredItems.filter(i=>i.status==="Completado").map(i=>i.assembly_part_id));
  const kEff   = kParts.size ? Math.round((kComp.size/kParts.size)*1000)/10 : 0;

  const topbar=h("div",{className:"topbar"},
    h("img",{src:"/logo",className:"logo",onError:e=>{e.target.style.display="none"}}),
    h("div",{className:"title"},"Fabrication Tracker"),
    h("div",{className:"kpis"},
      h("div",{className:"kpi-box"},h("div",{className:"val"},kParts.size),h("div",{className:"lbl"},"Total Parts")),
      h("div",{className:"kpi-box"},h("div",{className:"val"},kComp.size),h("div",{className:"lbl"},"Completados")),
      h("div",{className:"kpi-box"},h("div",{className:"val"},kEff+"%"),h("div",{className:"lbl"},"Eficiencia"))
    )
  );

  /* toolbar */
  const toolbar=h("div",{className:"toolbar"},
    h("input",{type:"file",className:"file-input",ref:fileInputRef,onChange:e=>setFile(e.target.files[0])}),
    h("button",{className:"btn btn-upload",onClick:upload},"⬆ Upload Excel"),
    h("a",{className:"btn btn-excel",   href:"/export/excel",    target:"_blank"},"📊 Excel"),
    h("a",{className:"btn btn-pdf",     href:"/export/pdf",      target:"_blank"},"📄 PDF"),
    h("a",{className:"btn btn-template",href:"/export/template", target:"_blank"},"📋 Template"),
  );

  /* filter bar */
  const filterBar = h(FilterBar,{data,filters,setFilters});

  /* alerts banner */
  const alertBanner=alerts.length>0&&h("div",{className:"alerts-banner"},
    h("span",{style:{color:"#ff6b35",fontWeight:700,fontSize:12}},"⚠ Cuello de Botella:"),
    ...alerts.map(a=>h("span",{key:a.id,className:"alert-chip"},
      `${a.process} › ${a.assembly_number?a.assembly_number+" / ":""}${a.part_number} · ${a.hours}h`))
  );

  /* tabs */
  const tabBar=h("div",{className:"tabs"},
    ["procesos","parts","matrix","analytics","admin"].map(t=>
      h("div",{key:t,className:"tab"+(tab===t?" active":""),onClick:()=>setTab(t)},
        {procesos:"🔧 Procesos",parts:"📦 Parts",matrix:"🗺 Matriz",analytics:"📈 Analytics",admin:"⚙ Admin"}[t])
    )
  );

  /* ════════ TAB PROCESOS ════════ */
  const tabProcesos=[
    h("div",{key:"hint",className:"reorder-hint"},"⠿ Arrastra las secciones para reordenar los procesos"),
    ...visibleProcs.map(p=>{
      const pi=procMap[p]||[];
      const sin=pi.filter(i=>i.status==="Sin Iniciar").length;
      const proc=pi.filter(i=>i.status==="En Proceso").length;
      const comp=pi.filter(i=>i.status==="Completado").length;
      const pct=pi.length?comp/pi.length*100:0;
      const isOpen=!!open[p];
      const sel=selected[p]||new Set();
      const selCount=sel.size;
      // when every row in this section belongs to the same ensamble, show it
      // once in the header instead of repeating it on every row
      const asmSet=new Set(pi.map(i=>i.assembly_number));
      const singleAsm=asmSet.size===1 ? [...asmSet][0] : null;
      // date grouping (Ord. arrows stay free-form when off, and are locked to
      // their own day's block once grouping is on)
      const grouped=!!groupByDate[p];
      const displayItems=grouped ? [...pi].sort((a,b)=>dateOf(a).localeCompare(dateOf(b))) : pi;
      const colCount=(singleAsm?13:14);

      return h("div",{
        key:p, className:"proc-section",
        draggable:true,
        onDragStart:e=>onDragStart(e,p),
        onDragOver: e=>onDragOver(e,p),
        onDrop:     e=>onDrop(e,p),
      },
        /* section header */
        h("div",{className:"proc-header",onClick:()=>setOpen({...open,[p]:!isOpen})},
          h("span",{className:"drag-handle",onClick:e=>e.stopPropagation()},"⠿"),
          h("span",{style:{fontSize:16}},(isOpen?"▼":"▶")),
          h("span",{className:"proc-title"},p),
          singleAsm&&h("span",{className:"stat-chip",style:{background:"#0d2040",color:"#4fc3f7"}},
            `🧩 ${singleAsm}`),
          h("button",{
            className:"btn "+(grouped?"btn-bulk":"btn-cancel"),
            style:{padding:"3px 10px",fontSize:11},
            onClick:e=>{ e.stopPropagation(); setGroupByDate({...groupByDate,[p]:!grouped}); }
          }, grouped?"📅 Agrupado":"📅 Agrupar por fecha"),
          alertSet.has(p)&&h("span",{className:"bottleneck-badge"},"⚠ Cuello de Botella"),
          h("div",{className:"proc-stats"},
            h("span",{className:"stat-chip chip-sin"},`⚪ ${sin}`),
            h("span",{className:"stat-chip chip-proc"},`🟡 ${proc}`),
            h("span",{className:"stat-chip chip-comp"},`🟢 ${comp}`)
          )
        ),
        /* progress bar */
        h("div",{className:"proc-bar-wrap"},
          h("div",{className:"proc-bar"},
            h("div",{className:"proc-bar-fill",style:{width:pct+"%"}})
          )
        ),
        /* bulk toolbar — only when open and something selected */
        isOpen && h("div",{className:"bulk-bar"},
          h("button",{className:"sel-all-btn",onClick:e=>{
            e.stopPropagation();
            const allIds=new Set(pi.map(i=>i.id));
            const allSelected=sel.size===pi.length;
            setSelected(s=>({...s,[p]:allSelected?new Set():allIds}));
          }},sel.size===pi.length?"Deselect All":"Select All"),
          h("span",{className:"bulk-count"},selCount>0?`${selCount} seleccionado(s)`:""),
          selCount>0&&h("button",{className:"btn btn-bulk",
            onClick:()=>bulkAction(p,"En Proceso")},"▶ Iniciar selección"),
          selCount>0&&h("button",{className:"btn btn-bulk",style:{background:"#1e5631"},
            onClick:()=>bulkAction(p,"Completado")},"✓ Completar selección"),
          selCount>0&&h("button",{className:"btn btn-bulk",style:{background:"#5a2800",color:"#ffb347"},
            onClick:()=>bulkAction(p,"Sin Iniciar")},"↺ Reabrir selección"),
        ),
        /* parts table */
        isOpen&&h("div",{className:"tbl-wrap"},
          h("table",null,
            h("thead",null,h("tr",null,
              h("th",{className:"cb-cell"},""),
              h("th",null,"Ord."),
              h("th",null,"Img"),
              ...(singleAsm?[]:["Ensamble"]).concat(
                ["Part","Descripción","Estado","Qty","Ini.Plan","Fin Plan",
                 "Ini.Real","Fin Real","T.Ciclo","Notas"]
              ).map(c=>h("th",{key:c},c))
            )),
            h("tbody",null,displayItems.map((item,idx)=>{
              const rows=[];
              const prevDiffDay = idx===0 || dateOf(displayItems[idx-1])!==dateOf(item);
              const nextDiffDay = idx===displayItems.length-1 || dateOf(displayItems[idx+1])!==dateOf(item);
              if(grouped && prevDiffDay){
                rows.push(h("tr",{key:"sep-"+dateOf(item)+"-"+item.id,className:"date-sep"},
                  h("td",{colSpan:colCount},fmtDateSep(dateOf(item)))
                ));
              }
              rows.push(
              h("tr",{key:item.id,className:STATUS_CLASS[item.status]||"sin"},
                /* checkbox */
                h("td",{className:"cb-cell"},
                  h("input",{type:"checkbox",checked:sel.has(item.id),
                    onChange:e=>{
                      const ns=new Set(sel);
                      e.target.checked?ns.add(item.id):ns.delete(item.id);
                      setSelected(s=>({...s,[p]:ns}));
                    }})
                ),
                /* row order arrows — locked to the same day's block while grouped */
                h("td",null,
                  h("div",{style:{display:"flex",flexDirection:"column",gap:1}},
                    h("button",{className:"btn btn-cancel",style:{padding:"0 5px",fontSize:10,lineHeight:1.4},
                      disabled:grouped?prevDiffDay:idx===0,
                      onClick:()=>moveRow(displayItems,item.id,-1,grouped)},"▲"),
                    h("button",{className:"btn btn-cancel",style:{padding:"0 5px",fontSize:10,lineHeight:1.4},
                      disabled:grouped?nextDiffDay:idx===displayItems.length-1,
                      onClick:()=>moveRow(displayItems,item.id,1,grouped)},"▼")
                  )
                ),
                /* part thumbnail, if the catalog part has one */
                h("td",null, partImgById[item.part_id]
                  ? h("img",{src:partImgById[item.part_id],className:"part-thumb",style:{cursor:"default"}})
                  : h("div",{className:"part-thumb part-thumb-empty",style:{cursor:"default"}},"—")
                ),
                ...(singleAsm?[]:[h("td",{key:"asm"},item.assembly_number)]),
                h("td",null,item.part_number),
                h("td",null,item.description),
                h("td",null,
                  h("select",{value:item.status,onChange:e=>updateField(item,"status",e.target.value)},
                    ["Sin Iniciar","En Proceso","Completado"].map(s=>h("option",{key:s},s))
                  )
                ),
                h("td",null,
                  h("input",{type:"number",value:item.qty_completed,style:{width:52},
                    onChange:e=>updateField(item,"qty_completed",e.target.value)}),
                  ` / ${item.qty_ordered}`
                ),
                h("td",null,h("input",{type:"date",value:item.planned_start||"",
                  onChange:e=>updateField(item,"planned_start",e.target.value)})),
                h("td",null,h("input",{type:"date",value:item.planned_end||"",
                  onChange:e=>updateField(item,"planned_end",e.target.value)})),
                h("td",null,h("input",{type:"datetime-local",className:"real-date",
                  value:item.actual_start||"",
                  onChange:e=>updateField(item,"actual_start",e.target.value)})),
                h("td",null,h("input",{type:"datetime-local",className:"real-date",
                  value:item.actual_end||"",
                  onChange:e=>updateField(item,"actual_end",e.target.value)})),
                h("td",null,item.cycle_time_min
                  ?h("span",{className:"cycle-badge"},fmtMins(item.cycle_time_min)):"—"),
                h("td",null,h("input",{type:"text",value:item.notes||"",
                  onChange:e=>updateField(item,"notes",e.target.value)}))
              ));
              return rows;
            }).flat())
          )
        )
      );
    })
  ];

  /* ════════ TAB PARTS ════════ */
  const tabParts=h("div",{className:"parts-grid"},
    Object.entries(partsMap).map(([apid,steps])=>{
      const total=steps.length;
      const comp=steps.filter(s=>s.status==="Completado").length;
      const proc=steps.filter(s=>s.status==="En Proceso").length;
      const pct=data.part_progress[apid]||0;
      const done=pct===100;
      const first=steps[0]||{};
      return h("div",{key:apid,className:"part-card"},
        h("div",{className:"pn"},`${first.assembly_number||""} › ${first.part_number||""}`),
        h("div",{className:"desc"},first.description||""),
        h("div",{className:"progress-track"},
          h("div",{className:"progress-fill"+(done?" done":""),style:{width:pct+"%"}})
        ),
        h("div",{className:"progress-label"},
          h("span",null,`${comp}/${total} procesos`),
          h("span",{style:{color:done?"#27ae60":proc>0?"#e6a817":"#6a88a8"}},`${pct}%`)
        ),
        h("div",{className:"step-dots"},
          steps.map(s=>h("div",{key:s.id,className:"dot "+(STATUS_DOT[s.status]||"sin"),
            title:`${s.process}: ${s.status}`}))
        )
      );
    })
  );

  /* ════════ TAB MATRIX ════════ */
  const partsIndex={};
  filteredItems.forEach(i=>{
    if(!partsIndex[i.assembly_part_id]){
      partsIndex[i.assembly_part_id]={_label:`${i.assembly_number} › ${i.part_number}`};
    }
    partsIndex[i.assembly_part_id][i.process]=i;
  });
  const tabMatrix=h("div",{className:"matrix-wrap"},
    h("table",null,
      h("thead",null,h("tr",null,
        h("th",null,"Ensamble › Parte"),
        ...visibleProcs.map(p=>h("th",{key:p},p))
      )),
      h("tbody",null,Object.keys(partsIndex).map(apid=>
        h("tr",{key:apid},
          h("td",{className:"pn-cell"},partsIndex[apid]._label),
          ...visibleProcs.map(p=>{
            const it=partsIndex[apid][p];
            if(!it) return h("td",{key:p,className:"cell-na"},"—");
            const cls="cell-"+(STATUS_CLASS[it.status]||"sin");
            const ct=it.cycle_time_min?` ⏱${fmtMins(it.cycle_time_min)}`:"";
            return h("td",{key:p,className:cls},`${it.qty_completed}/${it.qty_ordered}${ct}`);
          })
        )
      ))
    )
  );

  /* ════════ TAB ANALYTICS ════════ */
  const ranking=visibleProcs.map(p=>{
    const pi=procMap[p]||[];
    return{proc:p,wip:pi.filter(i=>i.status==="En Proceso").length,
           sin:pi.filter(i=>i.status==="Sin Iniciar").length,alert:alertSet.has(p)};
  }).sort((a,b)=>(b.wip+b.sin)-(a.wip+a.sin));

  const ctByProc={};
  visibleProcs.forEach(p=>{
    const times=filteredItems.filter(i=>i.process===p && i.cycle_time_min!=null).map(i=>i.cycle_time_min);
    ctByProc[p]=times.length ? Math.round((times.reduce((a,b)=>a+b,0)/times.length)*10)/10 : null;
  });
  const ctRows=visibleProcs.map(p=>({p,avg:ctByProc[p]}));
  const maxCT=Math.max(1,...ctRows.map(r=>r.avg||0));

  const tabAnalytics=h("div",null,
    h("div",{className:"chart-grid"},
      h("div",{className:"chart-container"},
        h("div",{className:"chart-title"},"📈 Eficiencia Histórica"),
        (data.snapshots&&data.snapshots.length)
          ?h(EffChart,{snapshots:data.snapshots})
          :h("div",{style:{color:"#6a88a8",fontSize:12,padding:20}},"Los datos aparecerán después del primer día de uso.")
      ),
      h("div",{className:"chart-container"},
        h("div",{className:"chart-title"},"📊 WIP por Proceso"),
        h(WipChart,{items:filteredItems,processes:visibleProcs})
      )
    ),
    h("div",{className:"chart-container"},
      h("div",{className:"chart-title"},"🏆 Ranking de Cuellos de Botella"),
      h("div",{style:{display:"flex",flexDirection:"column",gap:8}},
        ranking.map((r,i)=>
          h("div",{key:r.proc,style:{display:"flex",alignItems:"center",gap:10}},
            h("span",{style:{color:"#4fc3f7",minWidth:20,fontWeight:700}},`${i+1}.`),
            h("span",{style:{flex:1}},r.proc),
            r.alert&&h("span",{className:"bottleneck-badge"},"⚠ Alerta"),
            h("span",{className:"stat-chip chip-proc",style:{minWidth:60,textAlign:"center"}},`🟡 ${r.wip}`),
            h("span",{className:"stat-chip chip-sin", style:{minWidth:60,textAlign:"center"}},`⚪ ${r.sin}`)
          )
        )
      )
    ),
    h("div",{className:"chart-container"},
      h("div",{className:"chart-title"},"⏱ Tiempo de Ciclo Promedio por Proceso"),
      h("table",{className:"ct-table"},
        h("thead",null,h("tr",null,["Proceso","Promedio","Distribución"].map(c=>h("th",{key:c},c)))),
        h("tbody",null,ctRows.map(({p,avg})=>
          h("tr",{key:p},
            h("td",{style:{color:"#4fc3f7",fontWeight:600}},p),
            h("td",{style:{color:"#e6d17a",fontWeight:700}},fmtMins(avg)),
            h("td",{className:"ct-bar-cell"},avg
              ?h("div",{className:"ct-bar-bg"},h("div",{className:"ct-bar-fill",style:{width:Math.round(avg/maxCT*100)+"%"}}))
              :h("span",{style:{color:"#6a88a8",fontSize:11}},"Sin datos"))
          )
        ))
      )
    )
  );

  const tabAdmin = h(AdminTab,{data, reload:load, setModal});
  const tabContent={procesos:tabProcesos,parts:tabParts,matrix:tabMatrix,analytics:tabAnalytics,admin:tabAdmin}[tab];

  return h("div",{className:"app"},
    modal&&h(Modal,{
      title:modal.title, message:modal.message,
      warn:modal.warn,   needNote:modal.needNote,
      onConfirm:modal.onConfirm,
      onCancel:()=>setModal(null),
    }),
    topbar, toolbar, filterBar, alertBanner, tabBar,
    h("div",{className:"content"},tabContent)
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(h(App));
</script>
</body>
</html>
""";

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8010)
