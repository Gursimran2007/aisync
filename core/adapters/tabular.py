"""Flexible Excel/CSV adapter with AUTO column-mapping (V1 priority #1).

Usage:
    ad = TabularAdapter()
    df = ad.read(file)                  # excel or csv -> dataframe
    mapping = ad.suggest_mapping(df)    # auto-detected, show + let user correct
    batch = ad.normalize(df, mapping)   # apply (possibly corrected) mapping
"""
import io
from datetime import datetime
import pandas as pd
from .base import Adapter, NormalizedBatch
from ..mapping import detect_mapping, _DATE_FMTS


def _to_float(v, default=0.0):
    try:
        return float(str(v).replace(",", "").replace("₹", "").strip())
    except (ValueError, AttributeError):
        return default


def _to_iso(v):
    s = str(v).strip()
    for f in _DATE_FMTS:
        try:
            return datetime.strptime(s, f).date().isoformat()
        except ValueError:
            continue
    try:
        return pd.to_datetime(s).date().isoformat()
    except Exception:
        return s  # leave as-is; surfaced as warning upstream


class TabularAdapter(Adapter):
    name = "tabular"

    def read(self, file_or_path) -> pd.DataFrame:
        """Accepts path, bytes, or file-like. Sniffs csv vs excel vs pdf."""
        if isinstance(file_or_path, (bytes, bytearray)):
            head = bytes(file_or_path[:5])
            if head.startswith(b"%PDF"):
                return self._read_pdf(io.BytesIO(file_or_path))
            buf = io.BytesIO(file_or_path)
            try:
                return pd.read_excel(buf)
            except Exception:
                buf.seek(0)
                return pd.read_csv(buf)
        name = getattr(file_or_path, "name", str(file_or_path)).lower()
        if name.endswith(".pdf"):
            return self._read_pdf(file_or_path)
        if name.endswith((".xlsx", ".xls", ".xlsm")):
            return pd.read_excel(file_or_path)
        return pd.read_csv(file_or_path)

    @staticmethod
    def _read_pdf(file_or_path) -> pd.DataFrame:
        """Pull the largest table out of a PDF stock/issue report.

        Plant PDFs (SAP MB52 dumps, stores registers) are tabular. We take the
        widest table on each page, use its first row as the header, and stack
        the pages into one DataFrame so the same auto-mapping path applies."""
        try:
            import pdfplumber
        except ImportError as e:
            raise RuntimeError(
                "Reading PDFs needs the 'pdfplumber' package. Add it to "
                "requirements.txt (already listed) or `pip install pdfplumber`, "
                "or upload an Excel/CSV export instead.") from e

        # Ruled tables extract cleanly with the default (line) strategy; many
        # SAP/stores PDFs have no ruling lines, so fall back to whitespace-
        # aligned text columns.
        _text_settings = {"vertical_strategy": "text",
                          "horizontal_strategy": "text",
                          "snap_y_tolerance": 6, "join_x_tolerance": 12}

        def _page_tables(page):
            t = page.extract_tables() or []
            return t or (page.extract_tables(_text_settings) or [])

        frames = []
        header = None
        with pdfplumber.open(file_or_path) as pdf:
            for page in pdf.pages:
                tables = _page_tables(page)
                if not tables:
                    continue
                tbl = max(tables, key=lambda t: len(t[0]) if t else 0)
                tbl = [r for r in tbl if any((c or "").strip() for c in r)]
                if len(tbl) < 2:
                    continue
                first = [(_c or "").strip() for _c in tbl[0]]
                if header is None:
                    header = [c or f"col{i}" for i, c in enumerate(first)]
                    body = tbl[1:]
                else:
                    # subsequent pages: drop the row only if it repeats the header
                    body = tbl[1:] if first == header else tbl
                width = len(header)
                rows = [(r + [None] * width)[:width] for r in body]
                frames.append(pd.DataFrame(rows, columns=header))

        if not frames:
            raise RuntimeError(
                "No table found in that PDF. Make sure it's a stock/issue "
                "report with columns (not a scanned image), or upload the "
                "Excel/CSV export instead.")
        return pd.concat(frames, ignore_index=True)

    def suggest_mapping(self, df, fields=None):
        return detect_mapping(df, fields)

    def normalize(self, df: pd.DataFrame, mapping: dict = None, **kwargs) -> NormalizedBatch:
        mapping = mapping or self.suggest_mapping(df)
        col = {f: m["column"] for f, m in mapping.items() if m.get("column")}
        b = NormalizedBatch(meta={"mapping": mapping, "rows": len(df)})

        if "sku" not in col:
            b.warnings.append("No SKU column detected — cannot import without a key.")
            return b

        prod_seen = {}
        for _, row in df.iterrows():
            sku = str(row[col["sku"]]).strip()
            if not sku or sku.lower() == "nan":
                continue
            name = str(row[col["name"]]).strip() if "name" in col else ""
            cost = _to_float(row[col["unit_cost"]]) if "unit_cost" in col else 0.0
            if sku not in prod_seen:
                prod_seen[sku] = True
                b.products.append({"sku": sku, "name": name, "unit_cost": cost})

            if "date" in col and "qty" in col:
                iso = _to_iso(row[col["date"]])
                qty = _to_float(row[col["qty"]])
                b.sales.append({"sku": sku, "date": iso, "qty": qty})

            if "stock" in col:
                b.inventory.append({"sku": sku, "stock": _to_float(row[col["stock"]])})

            if "lead_time_days" in col:
                b.suppliers.append({
                    "sku": sku,
                    "lead_time_days": _to_float(row[col["lead_time_days"]], 7),
                    "reliability": _to_float(row[col["reliability"]], 0.95)
                    if "reliability" in col else 0.95})

        if "date" not in col or "qty" not in col:
            b.warnings.append("No date+qty pair detected — imported as catalog/stock "
                              "only, no sales history for forecasting.")
        return b
