"""
Build the BTP presentation from the IITG template.

Opens a COPY of the local template ("Hybrid Energy Storage Application in
Microgrid — BTP Final Presentation.pptx"), removes its placeholder slides and
rebuilds every slide with the template's own chrome (navy header band, amber
rule, eyebrow + title, logo slot, footer, page number), theme fonts and
colours. Diagrams and flowcharts are native, editable PowerPoint shapes;
plots are the project's own figures from figures/. Every number comes from
presentation_assets/results.json (written by collect_results.py) or the
saved CSVs in results/. The scientific model is not imported or changed.

Run from the project root with a Python that has python-pptx:
    python presentation_assets/build_deck.py
"""

import json
import pandas as pd
from PIL import Image
from lxml import etree
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.oxml.ns import qn

TEMPLATE = "Hybrid Energy Storage Application in Microgrid — BTP Final Presentation.pptx"
OUT = "IITG_BTP_Microgrid_Presentation.pptx"
NOTES_MD = "Presentation_Speaker_Notes.md"
FIG = "figures"
R = json.load(open("presentation_assets/results.json"))

# ---- template palette (read from the template's slides) -------------------
NAVY, AMBER, STEEL = "13233A", "E8A33D", "2E6F95"
BODY, MUTED, CARD, BORDER = "4A5568", "5F6B78", "FBFBF8", "D5DBE1"
LIGHT, PALE, GREYM, WHITE = "F2F4F7", "C9D4DF", "8A9AAB", "FFFFFF"
# ---- project figure entities (same colours as the plots) ------------------
PVC, BATC, DEMC, UNMC, SCC, GOOD = "1F7A72", "2A78D6", "C86A0A", "E34948", "6250D6", "1BAF7A"

FOOTER = "Amit Raj · Optimal Cost Sizing of a PV–Battery Microgrid · B.Tech Project, IIT Guwahati"
W, H = 13.333, 7.5
X0, XW = 0.667, 12.0               # content left edge and width
Y0, Y1 = 1.32, 6.82                # content top and bottom (footer at 6.96)


def rgb(h):
    return RGBColor.from_string(h)


# ===========================================================================
# drawing helpers
# ===========================================================================

def no_shadow(shape):
    sppr = shape._element.spPr
    eff = sppr.find(qn("a:effectLst"))
    if eff is None:
        etree.SubElement(sppr, qn("a:effectLst"))


def box(sl, x, y, w, h, fill=None, line=None, lw=0.75, shape=MSO_SHAPE.RECTANGLE,
        radius=0.06, dash=False, name=None):
    s = sl.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(lw)
        if dash:
            s.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    else:
        s.line.fill.background()
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    no_shadow(s)
    if name:
        s.name = name
    return s


def _fmt_run(run, size, color, bold, italic, font):
    f = run.font
    f.size = Pt(size)
    f.color.rgb = rgb(color)
    f.bold = bold
    f.italic = italic
    if font:
        f.name = font


def _bullet(p, level=0, char="•", color=None):
    pPr = p._p.get_or_add_pPr()
    indent = 0.22 + 0.22 * level
    pPr.set("marL", str(Emu(Inches(indent))))
    pPr.set("indent", str(-Emu(Inches(0.2))))
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
        for e in pPr.findall(qn(tag)):
            pPr.remove(e)
    if color:
        bc = etree.SubElement(pPr, qn("a:buClr"))
        etree.SubElement(bc, qn("a:srgbClr")).set("val", color)
    bu = etree.SubElement(pPr, qn("a:buChar"))
    bu.set("char", char)


def text(sl, x, y, w, h, content, size=14, color=BODY, bold=False, italic=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, margin=0.03, font=None,
         space_after=4, line_spacing=None, name=None, autofit=False):
    """
    content: str, or list of paragraphs. A paragraph is a str, or a dict with
    keys: runs [(text, {opts})] or text, size, color, bold, bullet, level,
    align, space_after, font, italic.
    """
    tb = sl.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        d = para if isinstance(para, dict) else {"text": para}
        p.alignment = d.get("align", align)
        p.space_after = Pt(d.get("space_after", space_after))
        if line_spacing:
            p.line_spacing = line_spacing
        runs = d.get("runs") or [(d.get("text", ""), {})]
        for rt, ro in runs:
            r = p.add_run()
            r.text = rt
            _fmt_run(r, ro.get("size", d.get("size", size)), ro.get("color", d.get("color", color)),
                     ro.get("bold", d.get("bold", bold)), ro.get("italic", d.get("italic", italic)),
                     ro.get("font", d.get("font", font)))
        if d.get("bullet"):
            _bullet(p, d.get("level", 0), color=d.get("bullet_color"))
    if name:
        tb.name = name
    return tb


def shape_text(s, content, size=13, color=NAVY, bold=False, align=PP_ALIGN.CENTER,
               anchor=MSO_ANCHOR.MIDDLE, margin=0.05):
    tf = s.text_frame
    tf.word_wrap = True
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", Inches(margin))
    tf.vertical_anchor = anchor
    paras = content if isinstance(content, list) else [content]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        d = para if isinstance(para, dict) else {"text": para}
        p.alignment = d.get("align", align)
        p.space_after = Pt(d.get("space_after", 0))
        runs = d.get("runs") or [(d.get("text", ""), {})]
        for rt, ro in runs:
            r = p.add_run()
            r.text = rt
            _fmt_run(r, ro.get("size", d.get("size", size)), ro.get("color", d.get("color", color)),
                     ro.get("bold", d.get("bold", bold)), ro.get("italic", d.get("italic", False)), None)
    return s


def node(sl, x, y, w, h, content, fill=WHITE, line=BORDER, size=13, color=NAVY, bold=False,
         shape=MSO_SHAPE.ROUNDED_RECTANGLE, dash=False, lw=1.0, align=PP_ALIGN.CENTER, radius=0.12):
    s = box(sl, x, y, w, h, fill=fill, line=line, lw=lw, shape=shape, dash=dash, radius=radius)
    return shape_text(s, content, size=size, color=color, bold=bold, align=align)


def arrow(sl, x1, y1, x2, y2, color=GREYM, width=1.5, head=True, dash=False):
    c = sl.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    if dash:
        c.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    if head:
        ln = c.line._get_or_add_ln()
        t = etree.SubElement(ln, qn("a:tailEnd"))
        t.set("type", "triangle")
        t.set("w", "med")
        t.set("len", "med")
    return c


def picture(sl, name, x, y, w, h, border=True, valign="top"):
    """Place figures/<name>.png inside the box, keeping its aspect ratio."""
    path = f"{FIG}/{name}.png"
    iw, ih = Image.open(path).size
    ar = iw / ih
    if w / h > ar:
        ph, pw = h, h * ar
    else:
        pw, ph = w, w / ar
    px = x + (w - pw) / 2
    py = y if valign == "top" else y + (h - ph) / 2
    p = sl.shapes.add_picture(path, Inches(px), Inches(py), Inches(pw), Inches(ph))
    p.name = name
    p._element.nvPicPr.cNvPr.set("descr", f"Project figure {name}.png: " + name.replace("_", " "))
    if border:
        p.line.color.rgb = rgb(BORDER)
        p.line.width = Pt(0.75)
    return p, (px, py, pw, ph)


def caption(sl, x, y, w, txt, size=11):
    return text(sl, x, y, w, 0.3, txt, size=size, color=MUTED, italic=True)


def stat(sl, x, y, w, h, value, label, color=STEEL, vsize=26, lsize=12, fill=CARD):
    box(sl, x, y, w, h, fill=fill, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    text(sl, x + 0.15, y + 0.08, w - 0.3, h * 0.55, value, size=vsize, color=color, bold=True,
         anchor=MSO_ANCHOR.BOTTOM)
    text(sl, x + 0.15, y + h * 0.58, w - 0.3, h * 0.4, label, size=lsize, color=BODY)


def card(sl, x, y, w, h, title=None, body=None, title_color=NAVY, fill=CARD, line=BORDER,
         size=13, tsize=15, dark=False):
    box(sl, x, y, w, h, fill=(NAVY if dark else fill), line=(None if dark else line),
        shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    ty = y + 0.12
    if title:
        text(sl, x + 0.18, ty, w - 0.36, 0.4, title, size=tsize, bold=True,
             color=(AMBER if dark else title_color))
        ty += 0.45
    if body is not None:
        text(sl, x + 0.18, ty, w - 0.36, h - (ty - y) - 0.08, body, size=size,
             color=(WHITE if dark else BODY))


def takeaway(sl, y, txt, h=0.62, size=14):
    """The template's dark result strip: one sentence that states what the slide shows."""
    box(sl, X0, y, XW, h, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    runs = [("Takeaway  ", {"color": AMBER, "bold": True})] + \
        [(t, {"color": WHITE, "bold": b}) for t, b in (txt if isinstance(txt, list) else [(txt, False)])]
    text(sl, X0 + 0.2, y, XW - 0.4, h, [{"runs": runs}], size=size, anchor=MSO_ANCHOR.MIDDLE)


def table(sl, x, y, w, rows, col_w, size=12, header_size=12, row_h=0.36, first_col_bold=True,
          highlight=None, header_fill=NAVY):
    nr, nc = len(rows), len(rows[0])
    gf = sl.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr))
    tbl = gf.table
    tblPr = tbl._tbl.tblPr
    for attr in ("firstRow", "bandRow"):
        tblPr.set(attr, "0")
    sid = tblPr.find(qn("a:tableStyleId"))
    if sid is not None:
        sid.text = "{5940675A-B579-460E-94D1-54222C63F5DA}"   # "No Style, Table Grid"
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        tbl.rows[i].height = Inches(row_h)
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            if i == 0:
                fill, color, bold, sz = header_fill, WHITE, True, header_size
            elif highlight is not None and i == highlight:
                fill, color, bold, sz = "FCEFD9", NAVY, (j == 0 and first_col_bold), size
            else:
                fill, color, bold, sz = (WHITE if i % 2 else LIGHT), NAVY if j == 0 else BODY, \
                    (j == 0 and first_col_bold), size
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(fill)
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = ""
            r = p.add_run()
            r.text = str(val)
            _fmt_run(r, sz, color, bold, False, None)
            # thin grid lines
            tcPr = cell._tc.get_or_add_tcPr()
            for edge in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                ln = etree.SubElement(tcPr, qn(edge))
                ln.set("w", str(Emu(Pt(0.5))))
                sf = etree.SubElement(ln, qn("a:solidFill"))
                etree.SubElement(sf, qn("a:srgbClr")).set("val", BORDER)
    return gf


# ===========================================================================
# slide chrome (copied from the template's geometry)
# ===========================================================================

class Deck:
    def __init__(self):
        self.prs = Presentation(TEMPLATE)
        lst = self.prs.slides._sldIdLst
        for sid in list(lst):                      # drop the template's placeholder slides
            self.prs.part.drop_rel(sid.rId)
            lst.remove(sid)
        self.blank = next(l for l in self.prs.slide_layouts if len(l.placeholders) == 0)
        self.slides = []                           # (slide, notes, title)
        self.page_boxes = []

    def new(self, eyebrow, title, notes):
        sl = self.prs.slides.add_slide(self.blank)
        box(sl, 0, 0, W, 1.0417, fill=NAVY, name="Header band")
        box(sl, 0, 1.0417, W, 0.0417, fill=AMBER, name="Header rule")
        text(sl, 0.667, 0.194, 10.73, 0.26, eyebrow.upper(), size=12, color=AMBER, bold=True,
             name="Eyebrow")
        text(sl, 0.667, 0.43, 10.9, 0.5, title, size=26, color=WHITE, bold=True, name="Title")
        logo = box(sl, 11.94, 0.16, 0.72, 0.72, fill=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
                   radius=0.5, name="Logo slot")
        text(sl, 0.667, 6.961, 10.0, 0.26, FOOTER, size=12, color=MUTED, name="Footer")
        pb = text(sl, 11.222, 6.961, 1.444, 0.26, "", size=12, color=MUTED, align=PP_ALIGN.RIGHT,
                  name="Page number")
        self.page_boxes.append(pb)
        self.slides.append((sl, notes, title))
        return sl

    def raw(self, notes, title):
        sl = self.prs.slides.add_slide(self.blank)
        self.page_boxes.append(None)
        self.slides.append((sl, notes, title))
        return sl

    def finish(self):
        n = len(self.slides)
        for i, ((sl, notes, title), pb) in enumerate(zip(self.slides, self.page_boxes), 1):
            if pb is not None:
                p = pb.text_frame.paragraphs[0]
                r = p.add_run()
                r.text = f"{i} / {n}"
                _fmt_run(r, 12, MUTED, False, False, None)
            sl.notes_slide.notes_text_frame.text = notes
        self.prs.save(OUT)
        with open(NOTES_MD, "w") as f:
            f.write("# Speaker notes — Optimal Cost Sizing of a PV–Battery Microgrid for IIT Guwahati\n\n")
            f.write(f"{n} slides. The same notes are in each slide's notes pane in `{OUT}`.\n\n")
            for i, (sl, notes, title) in enumerate(self.slides, 1):
                f.write(f"## Slide {i} — {title}\n\n{notes}\n\n")
        return n


# ===========================================================================
# numbers
# ===========================================================================

O, G, GR, WY, MC, SC = R["optimum"], R["grid"], R["growth"], R["weather_years"], R["montecarlo"], R["sc"]
DM, EC, SP, REL = R["demand"], R["econ"], R["spider"], R["reliability"]
GS = R["grid_sweep"]
PS = R["pso"]
CH = R["checks"]
SH = R["shortage"]
n_checks = sum(c["passed"] for c in CH.values())
sweep = pd.read_csv("results/grid_sweep.csv")
feas = sweep[sweep.lpsp <= 0.01].sort_values("npc")
five_spread = (feas.npc.iloc[4] - feas.npc.iloc[0]) / feas.npc.iloc[0] * 100
within2 = int((feas.npc <= feas.npc.iloc[0] * 1.02).sum())


def m(v, d=0):
    return f"₹{v:,.{d}f} M"


def pct(v, d=0, sign=False):
    return f"{v:+.{d}f} %" if sign else f"{v:.{d}f} %"


# ===========================================================================
# slides
# ===========================================================================

def s_title(D):
    sl = D.raw(
        "Introduce yourself, your supervisor and the project in one sentence: we size a solar plus "
        "battery system for two IIT Guwahati departments at the lowest 15-year cost while keeping unmet "
        "demand at or below 1 %, and then test how robust that answer is to weather, demand growth, "
        "grid access, a supercapacitor and uncertain inputs. Fill in the roll number and date before "
        "presenting, and place the IITG logo in the grey slot.",
        "Title")
    box(sl, 0, 0, W, 0.83, fill=NAVY)
    box(sl, 0, 0.83, W, 0.04, fill=AMBER)
    text(sl, 0.72, 0.17, 11.9, 0.32, "Indian Institute of Technology Guwahati", size=15, color=WHITE, bold=True)
    text(sl, 0.72, 0.47, 11.9, 0.26, "Department of Energy Engineering", size=12, color=PALE)
    box(sl, 6.15, 1.23, 1.03, 1.03, fill=LIGHT, line=GREYM, shape=MSO_SHAPE.ROUNDED_RECTANGLE,
        radius=0.5, name="Logo slot")
    text(sl, 2.5, 2.9, 8.33, 0.3, "B.TECH PROJECT · FINAL PRESENTATION", size=13, color=STEEL, bold=True,
         align=PP_ALIGN.CENTER)
    text(sl, 1.0, 3.28, 11.33, 1.25, "Optimal Cost Sizing of a PV–Battery Microgrid for IIT Guwahati",
         size=36, color=NAVY, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(sl, 1.0, 4.58, 11.33, 0.4, "Lifecycle economics, reliability and robustness analysis",
         size=17, color=BODY, align=PP_ALIGN.CENTER)
    arrow(sl, 2.5, 5.55, 10.83, 5.55, color=BORDER, width=0.75, head=False)
    text(sl, 2.3, 5.72, 4.0, 0.26, "PRESENTED BY", size=12, color=MUTED, bold=True, align=PP_ALIGN.CENTER)
    text(sl, 2.3, 6.0, 4.0, 0.34, "Amit Raj", size=16, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
    text(sl, 2.3, 6.36, 4.0, 0.3, "Roll No. [add before presenting]", size=12, color=BODY, align=PP_ALIGN.CENTER)
    text(sl, 7.03, 5.72, 4.0, 0.26, "UNDER THE GUIDANCE OF", size=12, color=MUTED, bold=True, align=PP_ALIGN.CENTER)
    text(sl, 7.03, 6.0, 4.0, 0.34, "Kuldeep Kumar", size=16, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
    text(sl, 7.03, 6.36, 4.0, 0.3, "[Presentation date]", size=12, color=BODY, align=PP_ALIGN.CENTER)


def s_outline(D):
    sl = D.new("Roadmap", "Outline of the talk",
               "Walk through the structure. Part I sets up the problem, Part II positions it in the literature, "
               "Part III explains the model and optimiser, Part IV gives the optimal design and stress-tests it, "
               "and Part V covers the scenario studies and conclusions. The flow strip at the bottom is the logic "
               "of the whole project: data feed a verified simulator, an optimiser searches it, and the optimum is "
               "then tested against weather, uncertainty and alternative scenarios.")
    items = [("01", "Introduction", "Microgrids, IITG demand, solar resource, objectives", "Slides 3–6"),
             ("02", "Literature and gap", "Landscape, reference study, comparison, contribution", "Slides 7–11"),
             ("03", "Modelling and optimisation", "Architecture, data, component and cost models, PSO", "Slides 12–18"),
             ("04", "Optimal design", "Sizing, design space, dispatch, battery ageing", "Slides 19–22"),
             ("05", "Robustness", "Weather years, sensitivity, reliability target, Monte Carlo", "Slides 23–26"),
             ("06", "Scenarios and conclusions", "Load growth, grid access, supercapacitor, CERC check", "Slides 27–34")]
    cw, chh, gx, gy = 3.84, 1.62, 0.24, 0.24
    for i, (num, t, d, s) in enumerate(items):
        x = X0 + (i % 3) * (cw + gx)
        y = 1.38 + (i // 3) * (chh + gy)
        box(sl, x, y, cw, chh, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        text(sl, x + 0.22, y + 0.14, 1.2, 0.45, num, size=24, color=STEEL, bold=True)
        text(sl, x + 1.15, y + 0.2, cw - 1.3, 0.4, s, size=12, color=MUTED, align=PP_ALIGN.RIGHT)
        text(sl, x + 0.22, y + 0.62, cw - 0.4, 0.38, t, size=17, color=NAVY, bold=True)
        text(sl, x + 0.22, y + 1.02, cw - 0.4, 0.55, d, size=13, color=BODY)
    flow = ["Demand + weather data", "Hourly simulator", "PSO optimiser", "Optimal design",
            "Stress tests", "Engineering decisions"]
    fy, fw = 5.35, 1.78
    gap = (XW - fw * len(flow)) / (len(flow) - 1)
    for i, f in enumerate(flow):
        x = X0 + i * (fw + gap)
        node(sl, x, fy, fw, 0.7, f, fill=(NAVY if i in (1, 2) else WHITE),
             line=(None if i in (1, 2) else STEEL), color=(WHITE if i in (1, 2) else NAVY), size=13, bold=True)
        if i:
            arrow(sl, x - gap + 0.03, fy + 0.35, x - 0.03, fy + 0.35, color=AMBER, width=2)
    caption(sl, X0, 6.2, XW, "The logic of the project: every result in Parts IV–V comes from the same verified simulator.")


def s_microgrid(D):
    sl = D.new("Introduction", "What is a microgrid?",
               "A microgrid is a local group of generators, storage and loads that can be controlled as one unit "
               "and can either connect to the main grid or run islanded (Lasseter 2002; Hatziargyriou et al. 2007). "
               "Point out the common bus and the controller. Then the coupling choice: in an AC-coupled system each "
               "source has its own converter onto an AC bus; in a DC microgrid PV and batteries share a DC bus, "
               "which saves conversion stages (Dragičević et al. 2016). Be explicit that this project models an "
               "AC-coupled system, the same topology as the reference study: the PV inverter is inside the CERC "
               "all-in PV cost and the battery connects through a bidirectional converter. The off-grid case means "
               "islanded operation with no utility connection.")
    text(sl, X0, 1.4, 5.4, 1.3, [
        {"runs": [("A microgrid is a ", {}), ("local group of generators, storage and loads", {"bold": True, "color": NAVY}),
                  (" controlled as one unit — connected to the main grid or running on its own (islanded).", {})]}],
        size=16, color=BODY)
    text(sl, X0, 2.75, 5.4, 2.0, [
        {"text": "Generation sits close to the load", "bullet": True},
        {"text": "Storage covers the gap between supply and demand", "bullet": True},
        {"text": "A controller dispatches every unit, hour by hour", "bullet": True},
        {"text": "Islanded operation: every kWh must come from local sources", "bullet": True}],
        size=15, color=BODY, space_after=6)
    # diagram
    dx = 6.55
    node(sl, dx + 2.0, 1.4, 2.0, 0.5, "Utility grid", fill=NAVY, line=None, color=WHITE, bold=True, size=13)
    node(sl, dx + 2.25, 2.12, 1.5, 0.36, "PCC switch", fill=WHITE, line=GREYM, size=11, dash=True)
    arrow(sl, dx + 3.0, 1.9, dx + 3.0, 2.12, head=False, color=NAVY, width=1.5)
    bus = node(sl, dx, 2.75, 6.0, 0.42, "Common bus  (AC or DC)", fill=AMBER, line=None, color=NAVY, bold=True, size=13)
    arrow(sl, dx + 3.0, 2.48, dx + 3.0, 2.75, head=False, color=NAVY, width=1.5)
    comps = [("Solar PV", "arrays, inverter", PVC), ("Storage", "battery, supercap.", BATC),
             ("Generators", "diesel, biogas", GREYM), ("Loads", "labs, workshops", DEMC)]
    cw = 1.38
    for i, (t, sub, c) in enumerate(comps):
        x = dx + i * (cw + 0.16)
        arrow(sl, x + cw / 2, 3.17, x + cw / 2, 3.5, head=False, color=NAVY, width=1.5)
        node(sl, x, 3.5, cw, 0.95, [{"text": t, "bold": True, "color": c, "size": 14},
                                     {"text": sub, "size": 11, "color": BODY}], fill=CARD, line=BORDER)
    node(sl, dx, 4.72, 6.0, 0.45, "Energy management system: monitors and dispatches every unit",
         fill=WHITE, line=STEEL, dash=True, size=12, color=NAVY)
    # coupling cards
    cy = 5.38
    card(sl, X0, cy, 5.85, 1.3, "AC-coupled  ·  this project", [
        {"text": "PV inverter and battery converter each feed an AC bus. Same topology as Kumar et al. (2018).",
         "size": 13}], title_color=STEEL, size=13, tsize=14)
    card(sl, X0 + 6.15, cy, 5.85, 1.3, "DC-coupled", [
        {"text": "PV and batteries share a DC bus: fewer conversion stages, natural for storage and supercapacitors.",
         "size": 13}], size=13, tsize=14)
    caption(sl, X0, 6.68, XW, "Lasseter (2002); Hatziargyriou et al. (2007); Dragičević et al. (2016).", size=10)


def s_demand(D):
    sl = D.new("Introduction", "IIT Guwahati departmental electricity demand",
               "The study supplies two departments: Mechanical Engineering with the Central Workshop, and "
               f"Electronics and Electrical Engineering. Annual demand is {DM['annual_mwh']:,.0f} MWh with a "
               f"{DM['peak_kw']:.0f} kW peak; the load factor (mean over peak) is {DM['load_factor']:.2f}. "
               "Mechanical plus Workshop is slightly larger. The load is not metered: it is built bottom-up from "
               "equipment inventories (rated kW, duty, operating hours), the weekday calendar and two vacation "
               "periods, then checked against the campus statistics in Kumar et al. Stress that this is the "
               "project's largest assumption and that demand turns out to be the strongest cost driver.")
    p, (px, py, pw, ph) = picture(sl, "load_departments", X0, 1.38, 8.55, 3.2)
    caption(sl, X0, py + ph + 0.05, pw, "Average weekday by department, and monthly energy (dips = vacations). Source: prepare_data.py.")
    sx, sw = 9.45, 3.22
    stat(sl, sx, 1.38, sw, 0.98, f"{DM['annual_mwh']:,.0f} MWh", "annual demand", color=DEMC)
    stat(sl, sx, 2.48, sw, 0.98, f"{DM['peak_kw']:.0f} kW", "peak demand", color=DEMC)
    stat(sl, sx, 3.58, sw, 0.98, f"{DM['load_factor']:.2f}", "load factor (mean / peak)", color=DEMC)
    share = DM["mech_mwh"] / DM["annual_mwh"] * 100
    card(sl, X0, 5.0, XW, 1.72, "How the hourly load was built  ·  assumption, not metered data", [
        {"text": "Equipment inventory per department → rated kW × duty × operating hours → weekday and "
                 "two-vacation calendar → hourly profile, calibrated against campus statistics (Kumar et al. 2018).",
         "bullet": True},
        {"text": f"Mechanical + Workshop {DM['mech_mwh']:,.0f} MWh ({share:.0f} %) · Electronics + Electrical "
                 f"{DM['elec_mwh']:,.0f} MWh ({100 - share:.0f} %). Power ratings are engineering estimates.",
         "bullet": True}], size=13, tsize=14)


def s_solar(D):
    sl = D.new("Introduction", "Solar resource and why storage is needed",
               f"NASA POWER hourly data for the campus point give {R['weather']['ghi_2023_kwh_m2']:,.0f} kWh/m² in 2023. "
               "Left: monthly sunshine; pre-monsoon months are sunniest and the monsoon brings dull spells. Right: the "
               "worst week. Every month has more PV energy than demand, so the shortfall is not seasonal: it comes "
               "from runs of consecutive dull days. In this week three deficit days add up to about 13.7 MWh short, "
               "which is what sizes the battery. Demand peaks in working hours while PV peaks at noon, and the "
               "evening and night load must come from storage.")
    p1, b1 = picture(sl, "solar_resource", X0, 1.38, 5.9, 2.6)
    p2, b2 = picture(sl, "load_worst_week", X0 + 6.1, 1.38, 5.9, 2.6)
    caption(sl, X0, b1[1] + b1[3] + 0.04, 5.9, "NASA POWER, 26.16 °N 91.77 °E, 2023.")
    caption(sl, X0 + 6.1, b2[1] + b2[3] + 0.04, 5.9, "Worst week: PV (teal) against demand (amber).")
    y = 4.55
    stat(sl, X0, y, 3.84, 1.15, f"{R['weather']['ghi_2023_kwh_m2']:,.0f} kWh/m²", "global horizontal irradiation, 2023", color=PVC)
    stat(sl, X0 + 4.08, y, 3.84, 1.15, "12 / 12", "months in which PV energy exceeds demand", color=PVC)
    stat(sl, X0 + 8.16, y, 3.84, 1.15, "3 days", "dull spell, ≈13.7 MWh short: this sizes the battery", color=UNMC)
    takeaway(sl, 5.95, "Storage is needed for nights and multi-day cloudy spells, not for seasons.")


def s_motivation(D):
    sl = D.new("Introduction", "Research motivation and objectives",
               "The core tension: PV energy is cheap but intermittent; storage removes unmet demand but is expensive "
               "and wears out. The Pareto curve on the right, from the 2,700-design sweep, shows the price of "
               "reliability: each step towards zero unmet demand costs more. We fix the reliability target at "
               "LPSP ≤ 1 % of annual demand and minimise the 15-year net present cost, which includes replacements "
               "and salvage, not just capital. Decision variables are PV size, battery strings, converter rating, and "
               "supercapacitor strings.")
    rows = [("Cost", "PV is cheap per kWh but only produces in daylight; batteries and replacements dominate later costs.", BATC),
            ("Reliability", "Each step towards zero unmet demand needs more storage and PV, at a rising price.", UNMC),
            ("Lifetime", "Batteries wear out within the 15-year horizon, so ageing has to be modelled, not assumed.", AMBER)]
    for i, (t, d, c) in enumerate(rows):
        y = 1.42 + i * 1.08
        box(sl, X0, y + 0.06, 0.5, 0.5, fill=c, shape=MSO_SHAPE.OVAL)
        text(sl, X0 + 0.7, y, 5.2, 0.35, t, size=16, bold=True, color=NAVY)
        text(sl, X0 + 0.7, y + 0.36, 5.2, 0.7, d, size=13, color=BODY)
    p, b = picture(sl, "pareto", X0 + 6.2, 1.38, 5.8, 3.05)
    caption(sl, X0 + 6.2, b[1] + b[3] + 0.04, 5.8, "Cheapest design at each reliability level (grid sweep).")
    card(sl, X0, 4.85, XW, 1.85, "Objective", [
        {"runs": [("Find the least-cost PV–battery configuration that supplies both departments with ", {}),
                  ("unmet demand ≤ 1 %", {"bold": True, "color": AMBER}),
                  (", over a ", {}), ("15-year lifecycle", {"bold": True, "color": AMBER}),
                  (" — then test that answer against weather, demand growth, grid access, a supercapacitor and "
                   "uncertain inputs.", {})], "size": 15}], dark=True, tsize=15)


def s_landscape(D):
    sl = D.new("Literature review", "Research landscape",
               "A qualitative timeline of the work this project builds on, not a publication count. Borowy and "
               "Salameh (1996) sized PV and battery for a target loss-of-power-supply probability at minimum cost. "
               "Kennedy and Eberhart (1995) introduced particle swarm optimisation. Lasseter (2002) framed the "
               "microgrid concept. HOMER (Lambert et al. 2006) made hourly techno-economic simulation standard. "
               "Yang et al. (2008) combined LPSP with a genetic algorithm; Dufo-López and Bernal-Agustín (2008) went "
               "multi-objective. Dragičević et al. (2016) reviewed DC microgrids. Xu et al. (2018) modelled battery "
               "degradation from counted stress cycles. Kumar et al. (2018) applied HOMER to the IITG campus.")
    events = [("1995", "Particle swarm optimisation", "Kennedy & Eberhart"),
              ("1996", "LPSP-based PV–battery sizing", "Borowy & Salameh"),
              ("2002", "The microgrid concept", "Lasseter"),
              ("2006", "HOMER hourly techno-economics", "Lambert, Gilman, Lilienthal"),
              ("2008", "GA + LPSP; multi-objective design", "Yang et al.; Dufo-López & Bernal-Agustín"),
              ("2016", "DC microgrid control review", "Dragičević et al."),
              ("2018", "Degradation from counted cycles", "Xu et al."),
              ("2018", "HOMER study of the IITG campus", "Kumar et al.")]
    ly = 3.3
    arrow(sl, X0, ly, X0 + XW, ly, color=NAVY, width=2.5, head=True)
    step = XW / len(events)
    for i, (yr, t, a) in enumerate(events):
        cx = X0 + step * (i + 0.5)
        box(sl, cx - 0.12, ly - 0.12, 0.24, 0.24, fill=(AMBER if i == 7 else STEEL), shape=MSO_SHAPE.OVAL)
        up = i % 2 == 0
        ty = 1.45 if up else 3.6
        text(sl, cx - step / 2 + 0.04, ty, step - 0.08, 0.35, yr, size=16, bold=True, color=AMBER,
             align=PP_ALIGN.CENTER)
        text(sl, cx - step / 2 + 0.04, ty + 0.36, step - 0.08, 0.75, t, size=12, bold=True, color=NAVY,
             align=PP_ALIGN.CENTER)
        text(sl, cx - step / 2 + 0.04, ty + 1.05, step - 0.08, 0.5, a, size=10, color=MUTED, italic=True,
             align=PP_ALIGN.CENTER)
        arrow(sl, cx, ly - 0.12 if up else ly + 0.12, cx, (ty + 1.5) if up else ty, head=False,
              color=BORDER, width=1)
    themes = ["Sizing for reliability", "Lifecycle economics", "Battery ageing", "Weather and uncertainty",
              "Metaheuristic search"]
    tw = (XW - 0.2 * 4) / 5
    for i, t in enumerate(themes):
        node(sl, X0 + i * (tw + 0.2), 5.5, tw, 0.6, t, fill=LIGHT, line=None, size=13, bold=True)
    caption(sl, X0, 6.2, XW, "Themes this project combines. Full references on the last slide.")


def s_reference(D):
    sl = D.new("Literature review", "Reference study: Kumar et al. (2018), IEEE Access",
               "Kumar et al. used HOMER Pro with its multi-year module for the whole IITG campus (peak 3,075 kW, "
               "about 60,379 kWh a day), with 10 % yearly load growth over 15 years, comparing 12 off-grid and "
               "grid-connected scenarios with PV, food-waste biogas, diesel and lead-acid batteries. Their best "
               "off-grid case (scenario 8, load following) had NPC ₹5,835 M and LCOE ₹11.96/kWh; grid-connected "
               "LCOE was ₹0.18–1.39/kWh. We take their costs, economics and battery choice; we change the scope "
               "(two departments), the tool (our own verified Python model), the battery ageing model, the optimiser "
               "and the robustness tests.")
    cols = [("What they did", [
        "HOMER Pro, multi-year module",
        "Whole IITG campus: peak 3,075 kW, ≈60,379 kWh/day",
        "12 scenarios: PV, biogas, diesel, lead-acid, grid",
        "10 % yearly load growth, 15-year project"], STEEL),
        ("What this project takes", [
            "Component costs (Table 2) and economics",
            "Discover 12VRE-3000TF-L lead-acid battery",
            "PV model (eq. 3) and AC-coupled topology",
            "Benchmarks for comparison"], PVC),
        ("What this project changes", [
            "Two departments, built bottom-up",
            "Own Python simulator with 35 checks",
            "Rainflow ageing; PSO + grid search",
            "12 weather years; Monte Carlo"], AMBER)]
    cw = (XW - 0.48) / 3
    for i, (t, items, c) in enumerate(cols):
        x = X0 + i * (cw + 0.24)
        box(sl, x, 1.4, cw, 3.0, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
        text(sl, x + 0.2, 1.52, cw - 0.4, 0.4, t, size=16, bold=True, color=c)
        text(sl, x + 0.2, 2.0, cw - 0.4, 2.35, [{"text": s, "bullet": True, "bullet_color": c} for s in items],
             size=14, color=BODY, space_after=6)
    y = 4.65
    stat(sl, X0, y, 3.84, 1.2, "₹5,835 M", "best off-grid NPC, whole campus (scenario 8)", color=STEEL)
    stat(sl, X0 + 4.08, y, 3.84, 1.2, "₹11.96–18.47", "off-grid LCOE range, per kWh", color=STEEL)
    stat(sl, X0 + 8.16, y, 3.84, 1.2, "₹0.18–1.39", "grid-connected LCOE range, per kWh", color=STEEL)
    caption(sl, X0, 5.98, XW, "All values from Kumar et al. (2018), checked against the paper's text. Whole-campus "
                              "figures, so they are benchmarks for unit cost, not for absolute NPC.")


def s_littable(D):
    sl = D.new("Literature review", "Critical literature comparison",
               "Read across the rows. Each study covers part of the problem. Borowy and Salameh introduced LPSP-"
               "constrained least-cost sizing; Yang et al. solved it with a genetic algorithm; Dufo-López and Bernal-"
               "Agustín added emissions and unmet load as objectives; Xu et al. showed how to estimate battery life "
               "from counted stress cycles; Kumar et al. gave the site, costs and benchmark for IITG. This project "
               "combines LPSP-constrained NPC minimisation with cycle-counted ageing, multiple weather years and "
               "uncertainty analysis in one reproducible model. Only facts confirmed from the papers' records are "
               "in the table.")
    rows = [["Study", "System", "Method", "Objective / reliability", "What it contributes"],
            ["Borowy & Salameh (1996)", "Stand-alone wind–PV–battery", "Iterative sizing of PV and battery",
             "Minimum cost at a target LPSP", "30 years of hourly data; house load"],
            ["Yang et al. (2008)", "Stand-alone PV–wind–battery", "Genetic algorithm",
             "Minimum annualised cost at a target LPSP", "Telecom relay station case"],
            ["Dufo-López & Bernal-Agustín (2008)", "PV–wind–diesel–H₂–battery", "Multi-objective evolutionary + GA",
             "NPC, CO₂ and unmet load together", "Pareto set of designs"],
            ["Xu et al. (2018)", "Li-ion battery storage", "Semi-empirical model with cycle counting",
             "Cell life loss from operating profile", "Degradation from irregular cycles"],
            ["Kumar et al. (2018)", "IITG campus: PV, biogas, diesel, battery, grid", "HOMER Pro multi-year",
             "NPC and LCOE, 12 scenarios", "Site data, costs, benchmark"],
            ["This work", "Two IITG departments: PV–battery (+ SC option)", "Own simulator; grid search + PSO",
             "Min. 15-year NPC, LPSP ≤ 1 %", "Rainflow ageing, 12 weather years, Monte Carlo"]]
    table(sl, X0, 1.4, XW, rows, [2.35, 2.45, 2.35, 2.45, 2.4], size=12, header_size=13, row_h=0.62, highlight=6)
    caption(sl, X0, 6.05, XW, "LPSP: loss of power supply probability. SC: supercapacitor. Details confirmed from "
                              "publisher or index records (DOIs in References).")


def s_gap(D):
    sl = D.new("Research gap", "Research gap and contribution",
               "Be careful with the claim. None of these techniques is new on its own. The gap is in combining them "
               "for this site, and in checking the assumptions a black-box tool hides. HOMER's default battery model "
               "treats lifetime throughput as constant regardless of depth of discharge; a single weather year can "
               "flatter a design; and the reference paper's inputs were never re-checked against their source. "
               "This project addresses each of these in an open, verified Python model.")
    gaps = [("Battery life as constant throughput", "HOMER's default model ignores depth of discharge."),
            ("One weather year", "A design can look reliable only because the year was sunny."),
            ("Campus aggregate load", "Department-level demand and its uncertainty are not studied."),
            ("Unchecked inputs", "Reference costs are reused without going back to the source.")]
    adds = [("Cycle-counted ageing", "Rainflow + Miner's rule on the datasheet curve, plus temperature float life."),
            ("Weather robustness", "Same design on 12 NASA years; a design optimised for all of them."),
            ("Bottom-up demand", "Two departments from equipment inventories; tested ±20 %."),
            ("Verified, open model", f"{n_checks} automated checks; PSO cross-checked by grid search."),
            ("Scenario studies", "Staged growth, grid access, supercapacitor economics."),
            ("Source audit", "CERC order checked: paper's PV cost and discount rate corrected.")]
    text(sl, X0, 1.38, 5.0, 0.4, "Gaps in the reference approach", size=16, bold=True, color=UNMC)
    for i, (t, d) in enumerate(gaps):
        y = 1.85 + i * 1.18
        box(sl, X0, y, 5.0, 1.05, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
        text(sl, X0 + 0.18, y + 0.08, 4.65, 0.35, t, size=14, bold=True, color=NAVY)
        text(sl, X0 + 0.18, y + 0.45, 4.65, 0.55, d, size=13, color=BODY)
    text(sl, 6.0, 1.38, 6.6, 0.4, "What this project adds", size=16, bold=True, color=PVC)
    for i, (t, d) in enumerate(adds):
        x = 6.0 + (i % 2) * 3.37
        y = 1.85 + (i // 2) * 1.58
        box(sl, x, y, 3.23, 1.45, fill=WHITE, line=PVC, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        text(sl, x + 0.16, y + 0.1, 2.95, 0.35, t, size=14, bold=True, color=PVC)
        text(sl, x + 0.16, y + 0.48, 2.95, 0.95, d, size=12, color=BODY)


def s_rqmap(D):
    sl = D.new("Methodology", "Research questions, methods and answers",
               "This map is the spine of the talk. Each question has a method, a script, an answer and the slide "
               "where the evidence is shown. Use it to signpost: every result later on answers one of these rows.")
    rows = [["#", "Research question", "Method (script)", "Short answer", "Slide"],
            ["1", "Does PSO reproduce the grid-search optimum?", "Grid sweep + PSO, 5 seeds (pso.py)",
             f"Yes: 5/5 runs within {PS['spread_pct']:.2f} %, below the grid best", "18–19"],
            ["2", "How does battery ageing affect lifecycle cost?", "Rainflow + Miner (simulator.py)",
             f"Life {O['batt_life']:.1f} y; replacements {m(O['cost_parts_m']['battery_replacements'], 1)}", "22"],
            ["3", "Is the design reliable in other weather years?", "12 NASA years (performance.py)",
             f"No: misses 1 % in {WY['fails']} of 12 years", "23"],
            ["4", "Does staged expansion save cost under growth?", "15-year growth model (multiyear.py)",
             f"Yes: {GR['saving_pct']:.0f} % cheaper at 10 %/yr", "27"],
            ["5", "How does grid access change the design?", "Grid scenarios (grid_connected.py)",
             f"Grid + {G['pv_kw']:,.0f} kW PV, no battery: {m(G['grid_pv_m'])}", "28"],
            ["6", "Is a supercapacitor economically justified?", "1-s load + filter (sc_study.py)",
             "At best break-even (τ ≈ 1–2 s)", "29–30"],
            ["7", "Which inputs drive cost and reliability?", "Tornado, spider (sensitivity.py)",
             "Demand, then PV and battery prices", "24–25"],
            ["8", "How uncertain are the results?", "Monte Carlo, 1,000 runs",
             f"NPC {m(MC['p5'])}–{m(MC['p95'])}; target missed {MC['miss_pct']:.0f} %", "26"],
            ["9", "Do corrected CERC inputs change the design?", "Re-run with CERC values",
             f"NPC {R['cerc']['change_pct']:+.1f} %, design unchanged", "31"]]
    table(sl, X0, 1.36, XW, rows, [0.4, 3.75, 3.3, 3.85, 0.7], size=12, header_size=13, row_h=0.52,
          first_col_bold=False)


def s_architecture(D):
    sl = D.new("Modelling", "Proposed system architecture",
               "The modelled system, AC-coupled as in Kumar et al. The PV array feeds the AC bus through its own "
               "inverter, whose cost is inside CERC's all-in PV price. The battery bank is 177 strings of 20 × 3 kWh "
               "batteries behind a bidirectional converter (efficiency 0.95). Each hour the dispatch is load following: "
               "PV serves the load first; surplus charges the battery within its current, converter and state-of-"
               "charge limits, and the rest is curtailed; a deficit is drawn from the battery and whatever it cannot "
               "supply is unmet demand. The supercapacitor (dashed) is an optional add-on studied separately; it "
               "does not take part in the hourly energy balance.")
    # left: diagram
    node(sl, X0, 1.5, 2.3, 1.0, [{"text": "PV array", "bold": True, "color": PVC, "size": 15},
                                  {"text": f"{O['pv_kw']:,.0f} kW", "size": 12, "color": BODY}], fill=CARD)
    node(sl, X0 + 2.75, 1.65, 1.75, 0.7, "PV inverter", fill=WHITE, line=PVC, size=13)
    arrow(sl, X0 + 2.3, 2.0, X0 + 2.75, 2.0, color=PVC, width=2)
    node(sl, X0, 3.65, 2.3, 1.0, [{"text": "Battery bank", "bold": True, "color": BATC, "size": 15},
                                   {"text": f"{O['strings']} strings × 20 × 3 kWh", "size": 11, "color": BODY}], fill=CARD)
    node(sl, X0 + 2.75, 3.8, 1.75, 0.7, [{"text": "Bidirectional", "size": 12}, {"text": "converter", "size": 12}],
         fill=WHITE, line=BATC, size=12)
    arrow(sl, X0 + 2.3, 4.05, X0 + 2.75, 4.05, color=BATC, width=2)
    arrow(sl, X0 + 2.75, 4.25, X0 + 2.3, 4.25, color=BATC, width=2)
    bus_x = X0 + 4.95
    node(sl, bus_x, 1.45, 0.55, 4.0, "AC bus", fill=AMBER, line=None, size=13, bold=True)
    arrow(sl, X0 + 4.5, 2.0, bus_x, 2.0, color=PVC, width=2)
    arrow(sl, X0 + 4.5, 4.05, bus_x, 4.05, color=BATC, width=2)
    arrow(sl, bus_x, 4.25, X0 + 4.5, 4.25, color=BATC, width=2)
    node(sl, bus_x + 0.95, 2.55, 1.85, 1.1, [{"text": "Department loads", "bold": True, "color": DEMC, "size": 14},
                                             {"text": "Mech + Workshop, Electrical", "size": 11, "color": BODY}], fill=CARD)
    arrow(sl, bus_x + 0.55, 3.1, bus_x + 0.95, 3.1, color=DEMC, width=2)
    node(sl, bus_x + 0.95, 4.05, 1.85, 0.6, "Unmet demand", fill=WHITE, line=UNMC, size=12, color=UNMC, bold=True)
    node(sl, X0 + 2.75, 0.0 + 2.62, 1.75, 0.55, "Curtailed PV", fill=WHITE, line=GREYM, size=12, color=MUTED, dash=True)
    arrow(sl, X0 + 3.62, 2.35, X0 + 3.62, 2.62, color=GREYM, width=1.25)
    node(sl, X0, 5.15, 2.3, 0.75, [{"text": "Supercapacitor (option)", "bold": True, "color": SCC, "size": 12},
                                    {"text": "4 strings × 24 modules", "size": 11, "color": BODY}],
         fill=WHITE, line=SCC, dash=True)
    node(sl, X0 + 2.75, 5.2, 1.75, 0.65, "DC–DC stage", fill=WHITE, line=SCC, dash=True, size=12)
    arrow(sl, X0 + 2.3, 5.52, X0 + 2.75, 5.52, color=SCC, width=1.5, dash=True)
    arrow(sl, X0 + 3.62, 5.2, X0 + 3.62, 4.5, color=SCC, width=1.5, dash=True)
    caption(sl, X0, 6.05, 7.8, "Studied separately with 1-second load data (slides 29–30); not part of the hourly balance.")
    # right: dispatch rules
    rx = 8.65
    box(sl, rx, 1.45, 4.0, 5.2, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    text(sl, rx + 0.2, 1.55, 3.6, 0.4, "Hourly dispatch rules", size=15, bold=True, color=NAVY)
    steps = [("1", "PV serves the load directly."),
             ("2", "Surplus charges the battery, limited by charge current, converter rating and room in the battery."),
             ("3", "Whatever cannot be stored is curtailed."),
             ("4", "A deficit is drawn from the battery, down to 20 % state of charge."),
             ("5", "Demand the battery cannot cover is unmet: it counts towards LPSP.")]
    for i, (n_, s) in enumerate(steps):
        y = 2.1 + i * 0.88
        box(sl, rx + 0.2, y + 0.04, 0.38, 0.38, fill=STEEL, shape=MSO_SHAPE.OVAL)
        text(sl, rx + 0.2, y + 0.04, 0.38, 0.38, n_, size=12, bold=True, color=WHITE, align=PP_ALIGN.CENTER,
             anchor=MSO_ANCHOR.MIDDLE, margin=0)
        text(sl, rx + 0.72, y, 3.15, 0.85, s, size=13, color=BODY)


def s_pipeline(D):
    sl = D.new("Modelling", "Demand and weather data pipeline",
               "prepare_data.py builds the hourly demand: each department's equipment list gives rated kW, a duty "
               "factor and operating hours; a calendar applies weekdays and the two vacation periods (equipment runs "
               "at 45 % in vacation); the result is calibrated against the campus statistics and written to "
               "data/inputs.csv. NASA POWER supplies hourly irradiance (CERES SYN1deg) and temperature (MERRA-2). "
               "The same script writes the worst-case transient (four machines switching together: 93 kW for 5 s) "
               "for the supercapacitor study. The 2013–2024 weather years feed the robustness and Monte Carlo studies.")
    r1 = ["Equipment inventory\nper department", "Rated kW × duty\n× operating hours", "Weekday and\nvacation calendar",
          "Hourly department\nprofiles"]
    r2 = ["NASA POWER 2023\nGHI + temperature", "Gap filling and\nclean-up"]
    bw, bh, y1, y2 = 2.05, 0.85, 1.45, 2.65
    xs = [X0 + i * (bw + 0.35) for i in range(4)]
    for i, t in enumerate(r1):
        node(sl, xs[i], y1, bw, bh, t, fill=CARD, line=DEMC, size=12)
        if i:
            arrow(sl, xs[i] - 0.35, y1 + bh / 2, xs[i], y1 + bh / 2, color=DEMC, width=1.75)
    for i, t in enumerate(r2):
        node(sl, xs[i], y2, bw, bh, t, fill=CARD, line=PVC, size=12)
        if i:
            arrow(sl, xs[i] - 0.35, y2 + bh / 2, xs[i], y2 + bh / 2, color=PVC, width=1.75)
    ox = xs[3] + bw + 0.4
    # one tall output box, so both input rows arrive with straight arrows
    node(sl, ox, y1, 2.0, y2 + bh - y1, [{"text": "data/inputs.csv", "bold": True, "size": 13, "color": WHITE},
                                          {"text": "8,760 hours:", "size": 11, "color": PALE},
                                          {"text": "load, GHI, T", "size": 11, "color": PALE}],
         fill=NAVY, line=None)
    arrow(sl, xs[3] + bw, y1 + bh / 2, ox, y1 + bh / 2, color=DEMC, width=1.75)
    arrow(sl, xs[1] + bw, y2 + bh / 2, ox, y2 + bh / 2, color=PVC, width=1.75)
    p, b = picture(sl, "load_heatmap", X0, 3.85, 7.4, 2.75)
    caption(sl, X0, b[1] + b[3] + 0.03, 7.4, "Every hour of the year: working hours, weekends and vacations show clearly.")
    rx, rw = 8.4, 4.27
    node(sl, rx, 3.85, rw, 0.62, [{"text": "Worst-case transient → transient_spec.csv", "size": 12, "bold": True},
                                  {"text": "4 machines together: 93 kW for 5 s (465 kJ)", "size": 11}],
         fill=WHITE, line=SCC, dash=True, color=NAVY)
    node(sl, rx, 4.57, rw, 0.62, [{"text": "NASA POWER 2013–2024", "size": 12, "bold": True},
                                  {"text": "weather years for robustness and Monte Carlo", "size": 11}],
         fill=WHITE, line=PVC, dash=True)
    card(sl, rx, 5.32, rw, 1.38, "Assumptions to state", [
        {"text": "Ratings are estimates; load is not metered", "bullet": True},
        {"text": "Same 2023 load shape in every weather year", "bullet": True}], size=12, tsize=14)


def s_components(D):
    sl = D.new("Modelling", "PV, battery and converter models",
               "The PV model is equation 3 of Kumar et al.: rated capacity times a derating factor of 0.85 times "
               "irradiance over 1,000 W/m², corrected for cell temperature with a coefficient of −0.40 %/°C; cell "
               "temperature comes from ambient temperature and irradiance through the NOCT model with NOCT 45 °C. "
               "The battery is an energy bucket between 20 % and 100 % state of charge, with the 85 % round-trip "
               "efficiency split equally between charge and discharge. Charge and discharge are limited by the "
               "datasheet currents (57 A and 133.9 A at 12 V). The converter limits both directions to its rating "
               "and costs 5 % each way.")
    cw = (XW - 0.48) / 3
    blocks = [
        ("PV array", PVC, [
            "P_PV(t) = P_r · f_d · G(t)/G_STC · [1 + α (T_c(t) − 25)]",
            "T_c(t) = T_a(t) + (NOCT − 20)/800 · G(t)"],
         ["f_d = 0.85 derating", "α = −0.40 %/°C", "NOCT = 45 °C,  G_STC = 1,000 W/m²",
          "Inverter inside CERC all-in cost"]),
        ("Battery bank", BATC, [
            "E(t+1) = E(t) + η_b · P_ch(t)",
            "E(t+1) = E(t) − P_dis(t) / η_b",
            "0.2 E_max ≤ E(t) ≤ E_max"],
         ["η_b = √0.85 each way", "3 kWh per battery, strings of 20", "P_ch ≤ 0.684 kW,  P_dis ≤ 1.607 kW per battery",
          "(57 A and 133.9 A at 12 V)"]),
        ("Bidirectional converter", STEEL, [
            "P_ch = min(surplus·η_c, P_conv·η_c, P_ch,max, room/η_b)",
            "P_dis = min(deficit/η_c, P_conv/η_c, P_dis,max, avail)"],
         ["η_c = 0.95 each way", f"Optimised rating: {O['converter_kw']:,.0f} kW",
          "AC side never exceeds the rating (checked)"])]
    for i, (t, c, eqs, params) in enumerate(blocks):
        x = X0 + i * (cw + 0.24)
        box(sl, x, 1.4, cw, 5.3, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
        text(sl, x + 0.2, 1.5, cw - 0.4, 0.4, t, size=17, bold=True, color=c)
        ey = 2.0
        for e in eqs:
            box(sl, x + 0.18, ey, cw - 0.36, 0.62, fill=WHITE, line=c, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
            text(sl, x + 0.26, ey, cw - 0.52, 0.62, e, size=12, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
            ey += 0.74
        text(sl, x + 0.2, ey + 0.1, cw - 0.4, 6.6 - ey, [{"text": p_, "bullet": True, "bullet_color": c} for p_ in params],
             size=13, color=BODY, space_after=6)
    caption(sl, X0, 6.72 - 0.0, XW, "")


def s_costs(D):
    rep = O["cost_parts_m"]
    sl = D.new("Modelling", "Reliability and lifecycle cost formulation",
               "Reliability is LPSP: unmet energy over demand for the year, which must be at most 1 %. It is an "
               "energy measure, not a count of shortage hours. Economics follow HOMER's conventions. The real "
               "discount rate is (1.1070/1.0571) − 1 = 4.72 %. NPC adds capital, discounted replacements and "
               "O&M, and subtracts the discounted salvage value of life left at year 15. LCOE is NPC times the "
               "capital recovery factor (0.0945) divided by energy served. Battery life is the shorter of the wear "
               "life and the float life. Wear life comes from rainflow-counting the hourly state of charge and "
               "Miner's rule on the datasheet cycle-life curve; float life comes from the datasheet's service-life "
               "versus temperature curve averaged over the site's hourly temperatures: 12.1 years.")
    lx, lw = X0, 6.35
    box(sl, lx, 1.4, lw, 5.3, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    text(sl, lx + 0.2, 1.5, lw - 0.4, 0.4, "Reliability and economics", size=16, bold=True, color=NAVY)
    eqs = [("LPSP = Σ E_unmet(t) / Σ E_load(t)  ≤  1 %", UNMC),
           ("NPC = C_cap + Σ C_rep,k/(1+r)^t_k + Σ C_O&M/(1+r)^t − C_salv/(1+r)^15", STEEL),
           ("r = (1 + i_nom)/(1 + f) − 1 = 1.1070/1.0571 − 1 = 4.72 %", STEEL),
           ("CRF = r(1+r)^N / ((1+r)^N − 1) = 0.0945,   LCOE = NPC · CRF / E_served", STEEL)]
    y = 2.0
    for e, c in eqs:
        box(sl, lx + 0.18, y, lw - 0.36, 0.6, fill=WHITE, line=c, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        text(sl, lx + 0.28, y, lw - 0.56, 0.6, e, size=12, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)
        y += 0.72
    text(sl, lx + 0.2, y + 0.05, lw - 0.4, 1.6, [
        {"text": "Salvage: last unit bought × fraction of life left at year 15 (linear, as HOMER)", "bullet": True},
        {"text": "15-year horizon; costs in constant 2016–17 rupees (Kumar et al., CERC)", "bullet": True},
        {"text": "LPSP counts energy not served, not the number of shortage hours", "bullet": True}],
        size=13, color=BODY, space_after=5)
    rx, rw = X0 + 6.6, 5.4
    box(sl, rx, 1.4, rw, 5.3, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    text(sl, rx + 0.22, 1.5, rw - 0.44, 0.4, "Battery ageing", size=16, bold=True, color=AMBER)
    steps = ["Rainflow-count the hourly state of charge → cycles of depth Dᵢ",
             "Cycle life N(D) from the datasheet: 5,000 at 20 %, 2,500 at 50 %, 1,500 at 80 % DoD",
             "Miner's rule: damage per year = Σ nᵢ / N(Dᵢ);  wear life = 1 / damage",
             f"Float life from service life vs temperature: {EC['float_life']:.1f} years at this site",
             "Battery life = min(wear life, float life) → replacements and salvage"]
    for i, s in enumerate(steps):
        y = 2.05 + i * 0.86
        box(sl, rx + 0.22, y + 0.05, 0.36, 0.36, fill=AMBER, shape=MSO_SHAPE.OVAL)
        text(sl, rx + 0.22, y + 0.05, 0.36, 0.36, str(i + 1), size=12, bold=True, color=NAVY,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0)
        text(sl, rx + 0.72, y, rw - 0.95, 0.85, s, size=13, color=WHITE)


def s_formulation(D):
    b = PS["bounds"]
    sl = D.new("Optimisation", "Mathematical optimisation formulation",
               "Four decision variables: PV capacity, number of battery strings, converter rating and supercapacitor "
               "strings. Minimise NPC subject to LPSP ≤ 1 % and enough supercapacitor strings to absorb the 465 kJ "
               "transient (4 strings). Strings are integers. Constraints are folded into a feasibility-first score: a "
               "feasible design scores its NPC; an infeasible one scores 10¹⁰ × (1 + violation), so any feasible "
               "design beats any infeasible one and smaller violations rank better. A plain penalty NPC + k × "
               "violation can let a slightly unreliable but cheap design win. The supercapacitor count is fixed at the "
               "requirement in the final runs, because extra strings only add cost.")
    box(sl, X0, 1.4, 6.6, 3.15, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    text(sl, X0 + 0.25, 1.5, 6.1, 3.0, [
        {"runs": [("Decision vector", {"color": AMBER, "bold": True})], "size": 14},
        {"text": "x = [ P_PV (kW),  N_str (integer),  P_conv (kW),  N_SC (integer) ]", "size": 15, "color": WHITE},
        {"runs": [("Minimise", {"color": AMBER, "bold": True})], "size": 14},
        {"text": "NPC(x)  over 15 years", "size": 15, "color": WHITE},
        {"runs": [("Subject to", {"color": AMBER, "bold": True})], "size": 14},
        {"text": "LPSP(x) ≤ 0.01", "size": 15, "color": WHITE},
        {"text": "N_SC ≥ N_SC,req = 4   (465 kJ transient)", "size": 15, "color": WHITE},
        {"text": "x within the bounds in the table", "size": 15, "color": WHITE}], space_after=4)
    rows = [["Variable", "Lower", "Upper", "Unit"],
            ["PV capacity", f"{b['pv_kw'][0]:,.0f}", f"{b['pv_kw'][1]:,.0f}", "kW"],
            ["Battery strings", f"{b['batt_strings'][0]:.0f}", f"{b['batt_strings'][1]:.0f}", "× 60 kWh"],
            ["Converter", f"{b['converter_kw'][0]:,.0f}", f"{b['converter_kw'][1]:,.0f}", "kW"],
            ["SC strings", "4", "4", "fixed at need"]]
    table(sl, X0 + 6.9, 1.4, 5.1, rows, [1.85, 1.0, 1.0, 1.25], size=13, header_size=13, row_h=0.5)
    caption(sl, X0 + 6.9, 4.0, 5.1, "Bounds are wider than the grid sweep, so PSO is not boxed in.")
    box(sl, X0, 4.8, XW, 1.85, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    text(sl, X0 + 0.25, 4.9, 5.4, 0.4, "Feasibility-first score", size=15, bold=True, color=NAVY)
    text(sl, X0 + 0.25, 5.35, 5.6, 1.2, [
        {"text": "score = NPC                    if feasible", "size": 14, "color": NAVY},
        {"text": "score = 10¹⁰ · (1 + violation)   otherwise", "size": 14, "color": NAVY},
        {"text": "violation = max(0, LPSP − 0.01) + max(0, N_SC,req − N_SC)", "size": 12, "color": BODY}],
        space_after=3)
    text(sl, X0 + 6.2, 4.95, 5.6, 1.65, [
        {"text": "Every feasible design beats every infeasible one", "bullet": True},
        {"text": "Among infeasible designs, the smaller violation wins", "bullet": True},
        {"text": "Avoids NPC + k·violation, where a cheap unreliable design can win", "bullet": True}],
        size=13, color=BODY, space_after=6)


def s_simulator(D):
    sl = D.new("Modelling", "Python simulator and its verification",
               "One function, simulate(), evaluates a design: it computes PV output for the year, steps through the "
               "8,760 hours of dispatch, then computes battery life and the lifecycle cost and folds the constraints "
               "into the score. It runs in about 9 ms, which makes the 2,700-design sweep and PSO cheap. Verification "
               f"means the code does what it is meant to: {n_checks} automated checks pass. These cover physical "
               "limits, energy balances that close exactly, monotonic behaviour, hand calculations of LCOE, salvage, "
               "cycle life and float life, the penalty logic, and agreement of the 15-year model with the single-year "
               "model when there is no growth. Verification is not external validation: there is no measured "
               "microgrid to compare against, which is a stated limitation.")
    steps = [("Inputs: load, GHI, temperature (8,760 h)", WHITE, NAVY),
             ("PV output for every hour", CARD, PVC),
             ("Hour loop: PV → load; surplus → battery → curtail; deficit → battery → unmet", CARD, BATC),
             ("Annual totals: served, unmet, curtailed, throughput", CARD, STEEL),
             ("Rainflow + Miner → battery life → replacements", CARD, BATC),
             ("NPC, LCOE, salvage", CARD, STEEL),
             ("Score = NPC, or penalty if LPSP > 1 %", NAVY, WHITE)]
    fx, fw, fh, gap = X0, 5.6, 0.6, 0.17
    for i, (t, fill, c) in enumerate(steps):
        y = 1.4 + i * (fh + gap)
        node(sl, fx, y, fw, fh, t, fill=fill, line=(None if fill == NAVY else (c if fill != WHITE else NAVY)),
             color=(WHITE if fill == NAVY else NAVY), size=12, bold=(i in (0, 6)))
        if i:
            arrow(sl, fx + fw / 2, y - gap, fx + fw / 2, y, color=GREYM, width=1.5)
    rx, rw = X0 + 6.0, 6.0
    text(sl, rx, 1.38, rw, 0.4, f"Verification: {n_checks} checks, all passing", size=16, bold=True, color=NAVY)
    groups = [(f"Simulator  ·  {CH['simulator']['passed']}", "Energy balances close; SoC, converter and current limits "
               "hold; LCOE, salvage, cycle and float life match hand calculations; penalties rank correctly"),
              (f"Multi-year model  ·  {CH['multiyear']['passed']}", "With no growth the 15-year model equals the "
               "single-year one for three designs; yearly costs add up to NPC"),
              (f"Grid model  ·  {CH['grid']['passed']}", "Grid-only cost matches the hand calculation; energy "
               "balances close; exports never exceed the cap")]
    for i, (t, d) in enumerate(groups):
        y = 1.88 + i * 1.38
        box(sl, rx, y, rw, 1.28, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        node(sl, rx + 0.15, y + 0.14, 0.75, 0.32, "PASS", fill=GOOD, line=None, color=WHITE, size=11, bold=True)
        text(sl, rx + 1.05, y + 0.08, rw - 1.2, 0.4, t, size=14, bold=True, color=NAVY)
        text(sl, rx + 1.05, y + 0.46, rw - 1.2, 0.8, d, size=12, color=BODY)
    box(sl, rx, 6.0, rw, 0.72, fill=LIGHT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    text(sl, rx + 0.18, 6.0, rw - 0.36, 0.72, "Verification, not validation: the code is checked against itself and hand "
         "calculations, not against a measured microgrid.", size=13, color=NAVY, anchor=MSO_ANCHOR.MIDDLE)


def s_pso(D):
    sl = D.new("Optimisation", "Grid search and particle swarm optimisation",
               f"The grid sweep tests {GS['designs']:,} designs: 12 PV sizes from 1,500 to 7,000 kW, 25 battery sizes from "
               "20 to 500 strings and 9 converter ratings from 600 to 2,200 kW. Its best feasible design costs "
               f"{m(GS['npc_m'], 1)}. PSO uses 20 particles for 40 iterations with the Clerc–Kennedy constriction "
               "coefficients (w = 0.7298, c1 = c2 = 1.49618), velocity capped at 20 % of the range, absorbing walls, "
               "and positions rounded to whole kW and strings with a cache. Five independent seeds all finish within "
               f"{PS['spread_pct']:.2f} % of each other and below the grid best, after about {PS['evals_per_run']} "
               "simulations each. A fine local grid of 3,179 designs around the PSO answer finds nothing better. That "
               "is strong evidence of a good optimum, not a proof of global optimality.")
    steps = ["Initialise 20 particles at random within bounds",
             "Round to whole kW / strings; simulate (cached)",
             "Update personal and global best scores",
             "v ← w·v + c₁r₁(p_best − x) + c₂r₂(g_best − x)",
             "Clip |v| ≤ 20 % of range; walls absorb",
             "Repeat 40 iterations → best design"]
    fx, fw, fh, gap = X0, 4.7, 0.58, 0.2
    for i, t in enumerate(steps):
        y = 1.42 + i * (fh + gap)
        node(sl, fx, y, fw, fh, t, fill=(NAVY if i in (0, 5) else CARD), line=(None if i in (0, 5) else STEEL),
             color=(WHITE if i in (0, 5) else NAVY), size=12, bold=(i in (0, 5)))
        if i:
            arrow(sl, fx + fw / 2, y - gap, fx + fw / 2, y, color=GREYM, width=1.5)
    arrow(sl, fx + fw + 0.05, 1.42 + 4 * (fh + gap) + fh / 2, fx + fw + 0.05, 1.42 + 1 * (fh + gap) + fh / 2,
          color=AMBER, width=1.5, dash=True)
    text(sl, fx + fw + 0.12, 2.9, 0.9, 0.6, "loop", size=11, color=AMBER, italic=True)
    caption(sl, X0, 6.05, 4.9, "w = 0.7298, c₁ = c₂ = 1.49618 (Clerc & Kennedy 2002).")
    p, b = picture(sl, "pso_convergence", X0 + 5.6, 1.38, 6.4, 3.4)
    caption(sl, X0 + 5.6, b[1] + b[3] + 0.03, 6.4, "Best NPC so far for each of 5 seeds, against the grid-sweep optimum.")
    y = 5.2
    w3 = (6.4 - 0.3) / 3
    stat(sl, X0 + 5.6, y, w3, 1.4, f"{GS['designs']:,}", f"grid designs; best {m(GS['npc_m'], 1)}", vsize=22)
    stat(sl, X0 + 5.6 + w3 + 0.15, y, w3, 1.4, "5 / 5", f"PSO seeds within {PS['spread_pct']:.2f} %", vsize=22, color=PVC)
    stat(sl, X0 + 5.6 + 2 * (w3 + 0.15), y, w3, 1.4, f"≈{PS['evals_per_run']}", "simulations per PSO run", vsize=22)


def s_optimum(D):
    cp = O["cost_parts_m"]
    sl = D.new("Results", "Optimal off-grid sizing",
               f"The optimum is {O['pv_kw']:,.0f} kW of PV, {O['batt_kwh']/1000:.1f} MWh of battery ({O['strings']} strings), a "
               f"{O['converter_kw']:,.0f} kW converter and the 4 required supercapacitor strings. NPC is {m(O['npc_m'], 1)}, "
               f"LCOE ₹{O['lcoe']:.2f}/kWh, LPSP exactly at the 1 % limit, and battery life {O['batt_life']:.1f} years, so "
               "the bank is replaced once within 15 years. PV capital is the largest item; battery capital plus "
               "its replacement is next. The balance: more PV is cheaper than more battery for covering most "
               "shortfalls, but PV alone cannot carry the night, and a bigger bank cycles less and lasts longer. "
               f"The grid sweep's best was {m(GS['npc_m'], 1)}; PSO is {GS['npc_m'] - O['npc_m']:.1f} M cheaper because "
               "it searches between grid points.")
    vals = [(f"{O['pv_kw']:,.0f} kW", "PV array", PVC), (f"{O['batt_kwh']/1000:.1f} MWh", f"battery ({O['strings']} strings)", BATC),
            (f"{O['converter_kw']:,.0f} kW", "converter", STEEL), (f"{O['sc_strings']} strings", "supercapacitor (required)", SCC),
            (m(O['npc_m'], 1), "15-year NPC", NAVY), (f"₹{O['lcoe']:.2f}/kWh", "LCOE", NAVY),
            (f"{O['lpsp']*100:.2f} %", "LPSP (limit 1 %)", UNMC), (f"{O['batt_life']:.1f} years", "battery life", BATC)]
    sw, sh = 2.75, 1.08
    for i, (v, l, c) in enumerate(vals):
        x = X0 + (i % 2) * (sw + 0.15)
        y = 1.38 + (i // 2) * (sh + 0.12)
        stat(sl, x, y, sw, sh, v, l, color=c, vsize=21)
    p, b = picture(sl, "cost_breakdown", X0 + 5.95, 1.38, 6.05, 3.6)
    caption(sl, X0 + 5.95, b[1] + b[3] + 0.03, 6.05, "Where the NPC goes: capital (blue), 15-year costs (orange), salvage credit (green).")
    takeaway(sl, 6.1, [(f"PSO {m(O['npc_m'], 1)} vs grid sweep {m(GS['npc_m'], 1)}: ", True),
                       ("the same valley found two independent ways — strong evidence, not a proof of global optimality.", False)],
             h=0.62, size=13)


def s_space(D):
    sl = D.new("Results", "Design space: a flat valley along the reliability boundary",
               "Left: NPC over PV and battery size at a 1,000 kW converter; grey is infeasible (LPSP above 1 %), the "
               "black line is the 1 % boundary, and both optima sit on it. Right: along that boundary, more PV means "
               "less battery is needed, and NPC is flat over a wide range. "
               f"{within2} feasible grid designs lie within 2 % of the cheapest, and the five cheapest are within "
               f"{five_spread:.1f} %. Practically, that gives freedom to choose PV and battery sizes to suit roof "
               "area, procurement or phasing, at almost no cost penalty.")
    p1, b1 = picture(sl, "npc_landscape", X0, 1.38, 5.4, 3.75)
    p2, b2 = picture(sl, "tradeoff", X0 + 5.6, 1.38, 6.4, 3.75, valign="center")
    caption(sl, X0, b1[1] + b1[3] + 0.03, 5.4, "NPC landscape at 1,000 kW converter; line = 1 % LPSP.")
    caption(sl, X0 + 5.6, b2[1] + b2[3] + 0.03, 6.4, "Battery needed and NPC along the 1 % boundary.")
    stat(sl, X0, 5.62, 3.84, 1.05, f"{within2}", "feasible grid designs within 2 % of the cheapest", vsize=22)
    stat(sl, X0 + 4.08, 5.62, 3.84, 1.05, f"{five_spread:.1f} %", "cost spread of the five cheapest", vsize=22)
    stat(sl, X0 + 8.16, 5.62, 3.84, 1.05, "On the boundary", "every optimum sits exactly at LPSP = 1 %", vsize=20, color=UNMC)


def s_flows(D):
    pv = O["pv_gen_mwh"]
    sl = D.new("Results", "Energy flows and hourly dispatch",
               f"Left: a year at the optimum. PV generates about {pv:,.0f} MWh. About a third goes straight to the load, "
               f"a third into the battery, and {O['curtailed_mwh']:,.0f} MWh ({O['curtailed_mwh']/pv*100:.0f} %) is curtailed "
               "because the battery is full. Battery and converter losses are about 441 MWh. Unmet demand is "
               f"{O['unmet_mwh']:.0f} MWh, 1 % of demand. Right: the sunniest day, when the battery fills by mid-morning "
               "and PV is curtailed, and the worst day, when the battery is empty and demand goes unmet in the evening "
               "and night. High curtailment is the price of reliability in an islanded system.")
    p1, b1 = picture(sl, "energy_flows", X0, 1.38, 5.9, 3.0)
    p2, b2 = picture(sl, "dispatch_days", X0 + 6.1, 1.38, 5.9, 3.0)
    caption(sl, X0, b1[1] + b1[3] + 0.03, 5.9, "Annual energy flows at the optimum (MWh).")
    caption(sl, X0 + 6.1, b2[1] + b2[3] + 0.03, 5.9, "Hourly dispatch: sunniest day and worst day.")
    y = 4.55
    stat(sl, X0, y, 2.85, 1.15, f"{pv:,.0f} MWh", "PV generated per year", color=PVC, vsize=22)
    stat(sl, X0 + 3.05, y, 2.85, 1.15, f"{O['curtailed_mwh']/pv*100:.0f} %", "of PV curtailed (battery full)", color=GREYM, vsize=22)
    stat(sl, X0 + 6.1, y, 2.85, 1.15, "441 MWh", "lost in battery and converter", color=BATC, vsize=22)
    stat(sl, X0 + 9.15, y, 2.85, 1.15, f"{O['unmet_mwh']:.0f} MWh", "unmet = 1 % of demand", color=UNMC, vsize=22)
    takeaway(sl, 6.0, "An islanded system must oversize PV and throw energy away to stay reliable through dull spells.")


def s_battery(D):
    cp = O["cost_parts_m"]
    sl = D.new("Results", "Battery operation and ageing",
               "Left: rainflow count of the hourly state of charge. Most cycles are 30–50 % deep, the daily charge "
               "and discharge. Feeding these depths through the datasheet cycle-life curve and Miner's rule gives a "
               f"wear life of {O['batt_life']:.1f} years, shorter than the {EC['float_life']:.1f}-year float life, so this "
               f"bank is limited by cycling and is replaced once, in year {O['replacements'][0]:.1f}. Right: bigger banks "
               "cycle shallower and last longer, until about 20 MWh where they hit the float-life ceiling. That is "
               "why lifecycle cost, not capital cost, decides the bank size: a cheaper small bank needs more "
               f"replacements. Replacements cost {m(cp['battery_replacements'], 1)} in present value.")
    p1, b1 = picture(sl, "soc_cycles", X0, 1.38, 5.9, 3.0)
    p2, b2 = picture(sl, "battery_life", X0 + 6.1, 1.38, 5.9, 3.0)
    caption(sl, X0, b1[1] + b1[3] + 0.03, 5.9, "Rainflow cycle depths of the hourly SoC (one year).")
    caption(sl, X0 + 6.1, b2[1] + b2[3] + 0.03, 5.9, "Battery life against bank size at the optimum PV.")
    y = 4.6
    stat(sl, X0, y, 2.85, 1.15, f"{O['batt_life']:.1f} y", "wear life: cycling-limited", color=BATC, vsize=22)
    stat(sl, X0 + 3.05, y, 2.85, 1.15, f"{EC['float_life']:.1f} y", "float life at site temperatures", color=GREYM, vsize=22)
    stat(sl, X0 + 6.1, y, 2.85, 1.15, f"year {O['replacements'][0]:.1f}", "one replacement in 15 years", color=AMBER, vsize=22)
    stat(sl, X0 + 9.15, y, 2.85, 1.15, m(cp['battery_replacements'], 1), "replacements (present value)", color=STEEL, vsize=22)
    takeaway(sl, 6.03, "Ageing links sizing to cost: a larger bank cycles less, lasts longer and needs fewer replacements.")


def s_weather(D):
    sl = D.new("Robustness", "Multi-year weather robustness",
               f"The 2023-optimised design was run unchanged on 12 years of NASA weather, 2013–2024, with the 2023 load. "
               f"It misses the 1 % target in {WY['fails']} of 12 years; the worst is {WY['worst_year']} at "
               f"{WY['worst']*100:.2f} %. 2023 was the second-sunniest year in the record, which flatters the design. "
               "The robust design was explicitly optimised, not picked by trial: PSO (20 particles, 30 iterations, "
               "started from the 2023 optimum) minimised the mean NPC over the 12 years subject to LPSP ≤ 1 % in every "
               f"year. It needs {WY['rob_pv']:,.0f} kW PV and {WY['rob_strings']*60/1000:.1f} MWh battery and costs "
               f"{m(WY['rob_mean_npc'])} on average, {WY['premium_pct']:.0f} % more. In 2023 itself the nominal design "
               f"has {SH['events']} shortage events totalling {SH['hours']} hours; the longest lasts {SH['longest']} hours.")
    p, b = picture(sl, "perf_weather_years", X0, 1.38, XW, 4.0)
    caption(sl, X0, b[1] + b[3] + 0.02, XW, "Left: LPSP of each design in each weather year. Right: mean NPC over the 12 years.")
    y = 5.75
    stat(sl, X0, y, 2.85, 0.98, f"{WY['fails']} of 12", "years the 2023 design misses 1 %", color=UNMC, vsize=20, lsize=11)
    stat(sl, X0 + 3.05, y, 2.85, 0.98, f"{WY['worst']*100:.2f} %", f"worst year ({WY['worst_year']})", color=UNMC, vsize=20, lsize=11)
    stat(sl, X0 + 6.1, y, 2.85, 0.98, f"+{WY['premium_pct']:.0f} %", "cost of meeting 1 % in all 12 years", color=BATC, vsize=20, lsize=11)
    stat(sl, X0 + 9.15, y, 2.85, 0.98, f"{SH['hours']} h", f"shortage hours in 2023 ({SH['events']} events)", color=GREYM, vsize=20, lsize=11)


def s_sensitivity(D):
    def g(p, c):
        return SP[p][f"{c:+.2f}"]
    sl = D.new("Sensitivity", "One-at-a-time sensitivity of the re-optimised cost",
               "Each input is changed on its own, PSO re-optimises the design, and the plot shows the percentage "
               "change in the re-optimised NPC from the base. That is the cost of the best design under the new "
               "conditions, not of today's design. Demand dominates: ±20 % demand moves cost by about ±20 %, almost "
               "proportionally, because every component scales with it. PV price is next, then battery price and "
               "battery cycle life. The discount rate and converter price hardly matter. PV derating is limited to "
               "±6 % so it stays physical.")
    p, b = picture(sl, "sens_spider", X0, 1.38, XW, 4.3)
    caption(sl, X0, b[1] + b[3] + 0.02, XW, "Spider plot: % change of re-optimised NPC (base ₹385 M) for each input changed alone.")
    y = 5.95
    vals = [(f"{g('Annual demand', -0.2):+.0f} / {g('Annual demand', 0.2):+.0f} %", "demand −20 / +20 %", DEMC),
            (f"{g('PV price', -0.2):+.0f} / {g('PV price', 0.2):+.0f} %", "PV price −20 / +20 %", PVC),
            (f"{g('Battery price', -0.2):+.0f} / {g('Battery price', 0.2):+.0f} %", "battery price −20 / +20 %", BATC),
            (f"{g('Battery cycle life', -0.2):+.0f} / {g('Battery cycle life', 0.2):+.0f} %", "cycle life −20 / +20 %", BATC)]
    for i, (v, l, c) in enumerate(vals):
        stat(sl, X0 + i * 3.05, y, 2.85, 0.82, v, l, color=c, vsize=17, lsize=11)


def s_reliability(D):
    t01, t10 = REL["0.0010"], REL["0.1000"]
    sl = D.new("Sensitivity", "The reliability target: what each step costs",
               "Here the constraint itself is varied and the design re-optimised for each target. Going from 1 % to "
               f"0.1 % unmet demand raises NPC by {t01['pct']:.0f} %; relaxing to 10 % cuts it by {-t10['pct']:.0f} %. "
               "The design changes too: tighter targets need much more battery, while PV changes less. The tornado "
               "chart in plot_results.py gives the same ranking as the spider plot. The practical point: the 1 % "
               "target is a choice with a price, and should be agreed with the institute, for example by exempting "
               "loads that can be shed.")
    p, b = picture(sl, "sens_reliability", X0, 1.38, XW, 3.9)
    caption(sl, X0, b[1] + b[3] + 0.02, XW, "Re-optimised NPC, PV and battery against the allowed unmet demand (log scale).")
    y = 5.6
    stat(sl, X0, y, 3.84, 1.05, f"{t01['pct']:+.0f} %", f"1 % → 0.1 % unmet ({m(t01['npc_m'])})", color=UNMC, vsize=22)
    stat(sl, X0 + 4.08, y, 3.84, 1.05, m(O['npc_m'], 1), "design target: 1 % unmet", color=NAVY, vsize=22)
    stat(sl, X0 + 8.16, y, 3.84, 1.05, f"{t10['pct']:+.0f} %", f"1 % → 10 % unmet ({m(t10['npc_m'])})", color=GOOD, vsize=22)


def s_montecarlo(D):
    sl = D.new("Uncertainty", "Monte Carlo uncertainty analysis",
               f"Sensitivity moves one input at a time; this moves all of them at once. {MC['n']:,} samples, design fixed "
               "at the optimum. Prices of PV, battery and converter, the real discount rate and battery cycle life are "
               "uniform within ±20 %; PV derating within ±6 %; demand within ±10 %; and the weather year is drawn "
               f"uniformly from 2013–2024. 90 % of sampled NPCs fall between {m(MC['p5'])} and {m(MC['p95'])}: this is the "
               "5th to 95th percentile of the sampled outcomes, not a statistical confidence interval. The design "
               f"misses the 1 % target in {MC['miss_pct']:.0f} % of samples. The right panel shows that prices and "
               "cycle life drive cost, while demand and weather drive reliability.")
    p, b = picture(sl, "sens_montecarlo", X0, 1.38, XW, 3.85)
    caption(sl, X0, b[1] + b[3] + 0.02, XW, "Distributions of NPC and LPSP, and the influence of each input (|Spearman ρ|).")
    rows = [["Sampled input", "Distribution"],
            ["PV, battery, converter prices", "uniform ±20 %"], ["Real discount rate, cycle life", "uniform ±20 %"],
            ["PV derating · demand", "±6 % · ±10 %"], ["Weather year", "uniform, 2013–2024"]]
    table(sl, X0, 5.33, 5.3, rows, [3.0, 2.3], size=11, header_size=11, row_h=0.28)
    stat(sl, X0 + 5.55, 5.33, 3.1, 1.4, f"{m(MC['p5'])}–{MC['p95']:.0f} M", "5th–95th percentile of NPC", vsize=19)
    stat(sl, X0 + 8.85, 5.33, 3.15, 1.4, f"{MC['miss_pct']:.0f} %", "of samples miss the 1 % target", color=UNMC, vsize=22)


def s_growth(D):
    sl = D.new("Scenarios", "Load growth and staged expansion",
               "With demand growing 10 % a year (Kumar et al.), year-15 demand is 3.8 times year 1, and today's optimum "
               "fails from year 2. Two strategies, both meeting 1 % in every year: build everything for year 15 at the "
               "start, or add capacity at the start of years 1, 6 and 11. Each is optimised with PSO plus a local search "
               f"and two seeds, which agree within {GR['spread_pct']:.2f} %. Staging costs {m(GR['staged_m'])} against "
               f"{m(GR['once_m'])}, {GR['saving_pct']:.0f} % less. Two effects: money spent later is discounted, and the "
               "early oversized battery in the build-once plan cycles shallowly for years and still ages. The staged "
               f"LCOE of ₹{GR['staged_lcoe']:.2f}/kWh lies inside the paper's off-grid range of ₹11.96–18.47/kWh.")
    p1, b1 = picture(sl, "growth_npc", X0, 1.38, 5.6, 2.9)
    p2, b2 = picture(sl, "growth_capacity", X0 + 5.8, 1.38, 6.2, 2.9, valign="center")
    caption(sl, X0, b1[1] + b1[3] + 0.03, 5.6, "NPC against growth rate.")
    caption(sl, X0 + 5.8, b2[1] + b2[3] + 0.03, 6.2, "Installed PV and battery, year by year (10 %/yr).")
    y = 4.75
    stat(sl, X0, y, 2.85, 1.15, m(GR['once_m']), "build once for year 15", color=NAVY, vsize=20)
    stat(sl, X0 + 3.05, y, 2.85, 1.15, m(GR['staged_m']), "staged: years 1, 6, 11", color=GOOD, vsize=20)
    stat(sl, X0 + 6.1, y, 2.85, 1.15, f"−{GR['saving_pct']:.0f} %", "lifecycle cost saved", color=GOOD, vsize=22)
    stat(sl, X0 + 9.15, y, 2.85, 1.15, f"₹{GR['staged_lcoe']:.2f}/kWh", "staged LCOE (paper: 11.96–18.47)", color=STEEL, vsize=20)
    takeaway(sl, 6.08, "Under growth, build in stages: later spending is discounted and capacity is not idle for years.")


def s_grid(D):
    sl = D.new("Scenarios", "Grid-connected alternatives",
               f"With a grid at the Assam commercial tariff of ₹{G['tariff']}/kWh, buying everything costs {m(G['grid_only_m'])}. "
               f"Adding {G['pv_kw']:,.0f} kW of PV cuts this to {m(G['grid_pv_m'])} (₹{G['grid_pv_lcoe']:.2f}/kWh), the cheapest "
               "option overall, because PV's lifetime cost is about ₹4.3/kWh, below the tariff. Exports are paid at the "
               "tariff, as the paper assumes, but capped at the 644 kW peak load: without a cap more PV would always "
               "look profitable. The battery never pays: every MWh adds cost, even with no export payment, because "
               "storing a kWh in lead-acid costs more than buying one. Important: the grid is assumed always available, "
               "so this is not the same reliability boundary as off-grid; outages are not modelled.")
    p1, b1 = picture(sl, "grid_scenarios", X0, 1.38, 5.9, 3.0)
    p2, b2 = picture(sl, "grid_battery", X0 + 6.1, 1.38, 5.9, 3.0)
    caption(sl, X0, b1[1] + b1[3] + 0.03, 5.9, "Four ways to supply the same demand.")
    caption(sl, X0 + 6.1, b2[1] + b2[3] + 0.03, 5.9, "NPC as battery is added on the grid.")
    card(sl, X0, 4.55, 5.9, 1.4, "Assumptions", [
        {"text": f"Buy ₹{G['tariff']}/kWh; export ₹{G['sell']}/kWh up to {G['export_cap_kw']:.0f} kW", "bullet": True},
        {"text": "Grid always available: no outages modelled", "bullet": True}], size=13, tsize=14)
    stat(sl, X0 + 6.1, 4.55, 2.85, 1.4, m(G['grid_pv_m']), f"grid + {G['pv_kw']:,.0f} kW PV (₹{G['grid_pv_lcoe']:.2f}/kWh)", color=PVC, vsize=20)
    stat(sl, X0 + 9.15, 4.55, 2.85, 1.4, "0 kWh", "battery chosen at every export price", color=BATC, vsize=22)
    takeaway(sl, 6.1, "With a reliable grid, storage is not worth it: the grid is the cheapest battery.")


def s_sc1(D):
    sl = D.new("Supercapacitor", "Supercapacitor: what it would see",
               "The hourly model cannot see a supercapacitor. sc_study.py builds a synthetic 1-second load for a working "
               "hour from the equipment list: machines switch on and off as Markov chains, direct-on-line motors draw a "
               "starting surge, and welders flicker. Left: one 30-minute window at 1 s, 1 min and 1 h. Right: a first-"
               "order low-pass filter with time constant τ sends the slow part of the storage power to the battery and "
               f"the fast part to the supercapacitor. The design transient is {SC['step_kw']:.0f} kW for 5 s, "
               f"{SC['energy_kj']:.0f} kJ, needing 4 strings of 24 modules (16 V, 58 F). For this {O['batt_kwh']/1000:.1f} MWh "
               f"bank that step is only {SC['c_rate']:.4f} C, far below the C/10 rate the battery is rated at.")
    p1, b1 = picture(sl, "sc_resolution", X0, 1.38, 5.9, 2.75)
    p2, b2 = picture(sl, "sc_power_split", X0 + 6.1, 1.38, 5.9, 3.05)
    caption(sl, X0, b1[1] + b1[3] + 0.03, 5.9, "Synthetic 1-s workshop load (from the equipment list).")
    caption(sl, X0 + 6.1, b2[1] + b2[3] + 0.03, 5.9, "Low-pass split: battery share (blue) and SC share (purple), τ = 10 s.")
    y = 4.85
    stat(sl, X0, y, 2.85, 1.1, f"{SC['step_kw']:.0f} kW", "coincident step, 5 s (465 kJ)", color=SCC, vsize=22)
    stat(sl, X0 + 3.05, y, 2.85, 1.1, f"{SC['c_rate']:.4f} C", f"step relative to the {O['batt_kwh']/1000:.1f} MWh bank", color=SCC, vsize=22)
    stat(sl, X0 + 6.1, y, 2.85, 1.1, f"{SC['payback']['2']['ramp_pct']:.0f} %", "battery ramp left with τ = 2 s", color=BATC, vsize=22)
    stat(sl, X0 + 9.15, y, 2.85, 1.1, "4 × 24", "strings × 16 V / 58 F modules", color=SCC, vsize=22)
    takeaway(sl, 6.12, "Technically the SC smooths the battery's fastest ramps; the question is whether that pays.")


def s_sc2(D):
    pb = SC["payback"]
    sl = D.new("Supercapacitor", "Is a supercapacitor economically justified?",
               "Its only economic value here is longer battery life. sc_study.py rainflow-counts the battery's second-"
               "scale cycles with and without the supercapacitor, adds them to the hourly cycles, and converts the life "
               "gain into NPC saved. Those cycles are far shallower than the datasheet's lowest point (20 % DoD), so two "
               "bounds are used: extending the datasheet's log-log slope (upper) or constant wear per kWh (lower). At "
               f"τ = 1 s the SC and its DC–DC stage cost ₹{pb['1']['cost_m']:.2f} M and save ₹{pb['1']['saved_lo_m']:.2f}–"
               f"{pb['1']['saved_hi_m']:.2f} M; at τ = 2 s ₹{pb['2']['cost_m']:.2f} M against ₹{pb['2']['saved_lo_m']:.2f}–"
               f"{pb['2']['saved_hi_m']:.2f} M. At best it breaks even; longer filters cost more than they save. A smaller "
               "bank saves fewer rupees, not more, because it is cheaper to replace. Technical benefit is not economic "
               "benefit, and several inputs are placeholders.")
    p, b = picture(sl, "sc_payback", X0, 1.38, 7.3, 3.0)
    caption(sl, X0, b[1] + b[3] + 0.03, 7.3, "SC + DC–DC cost against battery NPC saved, by filter τ and by bank size.")
    rows = [["Filter τ", "SC + DC–DC cost", "NPC saved (lower–upper)"],
            ["1 s", f"₹{pb['1']['cost_m']:.2f} M", f"₹{pb['1']['saved_lo_m']:.2f}–{pb['1']['saved_hi_m']:.2f} M"],
            ["2 s", f"₹{pb['2']['cost_m']:.2f} M", f"₹{pb['2']['saved_lo_m']:.2f}–{pb['2']['saved_hi_m']:.2f} M"],
            ["10 s", f"₹{pb['10']['cost_m']:.2f} M", f"₹{pb['10']['saved_lo_m']:.2f}–{pb['10']['saved_hi_m']:.2f} M"]]
    table(sl, X0 + 7.55, 1.38, 4.45, rows, [1.05, 1.5, 1.9], size=12, header_size=12, row_h=0.42)
    card(sl, X0 + 7.55, 3.25, 4.45, 2.0, "Unresolved assumptions", [
        {"text": f"Module price ₹{SC['price_placeholder']:,.0f} (placeholder)", "bullet": True},
        {"text": "Motor starting surge 5× rated", "bullet": True},
        {"text": "Machine on-times and power ratings", "bullet": True}], size=13, tsize=14, title_color=UNMC)
    stat(sl, X0, 4.85, 3.55, 1.1, "Break-even at best", "only with the upper bound, τ ≈ 1–2 s", color=SCC, vsize=19)
    stat(sl, X0 + 3.75, 4.85, 3.55, 1.1, f"{SC['c_rate']:.4f} C", "the step is no stress for this bank", color=SCC, vsize=20)
    takeaway(sl, 6.12, "Not justified on cost for this design. Revisit with real prices, or for small banks whose current "
                       "limit the surge exceeds.", size=13)


def s_cerc(D):
    c = R["cerc"]
    sl = D.new("Source validation", "Checking the reference paper against CERC",
               "Kumar et al. cite the CERC FY 2016-17 tariff order (Petition SM/03/2016, 29 April 2016) for the PV cost "
               "and discount rate. The order says ₹530.02 lakh/MW, which is ₹53,002/kW, and a discount factor of 10.64 % "
               "(12.76 % × 0.70 × (1 − 34.61 %) + 16 % × 0.30). The paper uses ₹50,502/kW and 10.70 %. 10.70 % is the "
               "earlier figure that the order replaces; 50,502 does not appear in the order. We do not speculate about "
               "why. Re-running with the CERC values raises NPC by "
               f"{c['change_pct']:.1f} % to {m(c['npc_m'], 1)}, and re-optimising returns the same design. We keep the paper's "
               "values as the base case for comparability and report the corrected case. The lesson for reproducibility: "
               "check inputs against the primary source, not the citing paper.")
    rows = [["Input", "Kumar et al. (2018)", "CERC order (primary)", "Used in this project"],
            ["PV capital cost", "₹50,502 / kW", "₹53,002 / kW (₹530.02 lakh/MW)", "Paper value (base)"],
            ["Discount factor", "10.70 %", "10.64 %", "Paper value (base)"]]
    table(sl, X0, 1.45, XW, rows, [2.4, 2.8, 3.9, 2.9], size=14, header_size=14, row_h=0.6)
    y = 3.55
    stat(sl, X0, y, 3.84, 1.3, f"{c['change_pct']:+.1f} %", "NPC with CERC values", color=AMBER, vsize=26)
    stat(sl, X0 + 4.08, y, 3.84, 1.3, m(c['npc_m'], 1), f"vs base {m(O['npc_m'], 1)}", color=NAVY, vsize=24)
    stat(sl, X0 + 8.16, y, 3.84, 1.3, "Unchanged", "re-optimised design: same sizes", color=GOOD, vsize=24)
    card(sl, X0, 5.1, XW, 1.55, "Sources", [
        {"text": "CERC, Petition SM/03/2016, order 29 Apr 2016, para 9 (discount factor) and para 27 (PV cost); CERC, "
                 "Petition 17/SM/2015, order 23 Mar 2016 (PV cost breakdown). Both PDFs are in resources/.", "size": 13}],
         size=13, tsize=14)


def s_discussion(D):
    sl = D.new("Discussion", "Integrated engineering discussion",
               "Pull the threads together. Cost is set mostly by demand and the PV and battery prices. Reliability is "
               "set by weather and demand, and a single-year optimum sits exactly on the 1 % boundary, so any worse "
               "year breaks it. Robustness costs about 14 % for weather alone. Growth favours staging. Grid access "
               "changes the answer completely. The supercapacitor's case is conditional. The central message: optimal "
               "sizing is a trade-off between lifecycle cost, reliability and robustness, and the cheapest nominal "
               "design is the least robust one.")
    cells = [("Cost", "Demand ±20 % → ±20 % NPC; then PV price, battery price, cycle life.", NAVY),
             ("Reliability", f"Nominal optimum sits on the 1 % edge; misses it in {WY['fails']} of 12 years.", UNMC),
             ("Robustness", f"+{WY['premium_pct']:.0f} % buys 1 % in every weather year; Monte Carlo misses {MC['miss_pct']:.0f} %.", BATC),
             ("Demand growth", f"Staged expansion saves {GR['saving_pct']:.0f} % at 10 %/yr.", GOOD),
             ("Grid access", f"Grid + PV is {(1 - G['grid_pv_m']/O['npc_m'])*100:.0f} % cheaper than off-grid; no battery.", PVC),
             ("Supercapacitor", "Technical benefit is real; economic benefit is at best break-even.", SCC)]
    cw, chh = (XW - 0.48) / 3, 1.85
    for i, (t, d, c) in enumerate(cells):
        x = X0 + (i % 3) * (cw + 0.24)
        y = 1.4 + (i // 3) * (chh + 0.2)
        box(sl, x, y, cw, chh, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
        box(sl, x + 0.2, y + 0.2, 0.32, 0.32, fill=c, shape=MSO_SHAPE.OVAL)
        text(sl, x + 0.65, y + 0.14, cw - 0.8, 0.4, t, size=16, bold=True, color=NAVY)
        text(sl, x + 0.2, y + 0.68, cw - 0.4, 1.1, d, size=14, color=BODY)
    box(sl, X0, 5.55, XW, 1.12, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    text(sl, X0 + 0.3, 5.55, XW - 0.6, 1.12, [
        {"runs": [("Optimal microgrid sizing is a trade-off between ", {"color": WHITE}),
                  ("lifecycle cost, reliability and robustness", {"color": AMBER, "bold": True}),
                  (" to changing operating conditions.", {"color": WHITE})]}], size=19, anchor=MSO_ANCHOR.MIDDLE)


def s_conclusions(D):
    sl = D.new("Conclusions", "Conclusions, limitations and future work",
               "Conclusions are the verified numbers. Limitations are stated plainly: the load is synthetic, the model "
               "is verified but not validated against a measured system, the supercapacitor inputs are placeholders, "
               "the battery costs date from 2016, and the grid case ignores outages. Future work follows directly from "
               "the limitations: meter data, a multi-year design as the headline result, LFP batteries, diesel backup "
               "as in the reference study, CO₂ accounting and real supercapacitor quotes.")
    cols = [("Conclusions", PVC, [
        f"Optimum: {O['pv_kw']:,.0f} kW PV, {O['batt_kwh']/1000:.1f} MWh, {O['converter_kw']:,.0f} kW; {m(O['npc_m'], 1)}, ₹{O['lcoe']:.2f}/kWh",
        "PSO matches and improves on grid search (5/5 seeds)",
        f"Robust to 12 weather years: +{WY['premium_pct']:.0f} % cost",
        f"Staging saves {GR['saving_pct']:.0f} % under 10 % growth",
        f"Grid + PV: {m(G['grid_pv_m'])}, no battery",
        "Supercapacitor: at best break-even"]),
        ("Limitations", UNMC, [
            "Synthetic load, not metered",
            "Verified (35 checks), not externally validated",
            "SC price, surge, on-times are placeholders",
            "Costs from 2016–17; lead-acid only",
            "Grid case ignores outages",
            "Hourly model; one load shape for all years"]),
        ("Future work", STEEL, [
            "Calibrate with department meter data",
            "Adopt the multi-year design as the main result",
            "Compare LFP batteries at today's prices",
            "Add diesel backup, as in Kumar et al.",
            "CO₂ savings and cost–emission trade-off",
            "Supplier quotes for SC and DC–DC stage"])]
    cw = (XW - 0.48) / 3
    for i, (t, c, items) in enumerate(cols):
        x = X0 + i * (cw + 0.24)
        box(sl, x, 1.4, cw, 5.3, fill=CARD, line=BORDER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
        text(sl, x + 0.2, 1.52, cw - 0.4, 0.42, t, size=18, bold=True, color=c)
        text(sl, x + 0.2, 2.05, cw - 0.4, 4.55, [{"text": s, "bullet": True, "bullet_color": c} for s in items],
             size=14, color=BODY, space_after=9)


REFS = [
    "A. Kumar, A. R. Singh, Y. Deng, X. He, P. Kumar, R. C. Bansal, “Multiyear load growth based techno-financial evaluation of a microgrid for an academic institution,” IEEE Access, vol. 6, pp. 37533–37555, 2018. doi:10.1109/ACCESS.2018.2849411",
    "CERC, Determination of levellised generic tariff for FY 2016-17, Petition No. SM/03/2016, order 29 Apr 2016. cercind.gov.in/2016/orders/SORE.pdf",
    "CERC, Benchmark capital cost norm for solar PV and solar thermal projects, FY 2016-17, Petition No. 17/SM/2015, order 23 Mar 2016.",
    "NASA POWER Project, hourly all-sky irradiance (CERES SYN1deg) and 2 m temperature (MERRA-2), 26.162 N 91.7668 E, 2013–2024. power.larc.nasa.gov",
    "Discover Energy Corp., 12VRE-3000TF-L Tubular Flooded RE Series datasheet, 12 Nov 2013.",
    "B. S. Borowy, Z. M. Salameh, “Methodology for optimally sizing the combination of a battery bank and PV array in a wind/PV hybrid system,” IEEE Trans. Energy Convers., vol. 11, no. 2, pp. 367–375, 1996. doi:10.1109/60.507648",
    "H. Yang, W. Zhou, L. Lu, Z. Fang, “Optimal sizing method for stand-alone hybrid solar–wind system with LPSP technology by using genetic algorithm,” Solar Energy, vol. 82, no. 4, pp. 354–367, 2008. doi:10.1016/j.solener.2007.08.005",
    "R. Dufo-López, J. L. Bernal-Agustín, “Multi-objective design of PV–wind–diesel–hydrogen–battery systems,” Renewable Energy, vol. 33, no. 12, pp. 2559–2572, 2008. doi:10.1016/j.renene.2008.02.027",
    "B. Xu, A. Oudalov, A. Ulbig, G. Andersson, D. S. Kirschen, “Modeling of lithium-ion battery degradation for cell life assessment,” IEEE Trans. Smart Grid, vol. 9, no. 2, pp. 1131–1140, 2018. doi:10.1109/TSG.2016.2578950",
    "J. Kennedy, R. Eberhart, “Particle swarm optimization,” Proc. ICNN’95, vol. 4, pp. 1942–1948, 1995. doi:10.1109/ICNN.1995.488968",
    "M. Clerc, J. Kennedy, “The particle swarm — explosion, stability, and convergence in a multidimensional complex space,” IEEE Trans. Evol. Comput., vol. 6, no. 1, pp. 58–73, 2002. doi:10.1109/4235.985692",
    "R. H. Lasseter, “MicroGrids,” IEEE PES Winter Meeting, vol. 1, pp. 305–308, 2002. doi:10.1109/PESW.2002.985003",
    "N. Hatziargyriou, H. Asano, R. Iravani, C. Marnay, “Microgrids,” IEEE Power Energy Mag., vol. 5, no. 4, pp. 78–94, 2007. doi:10.1109/MPAE.2007.376583",
    "T. Dragičević, X. Lu, J. C. Vasquez, J. M. Guerrero, “DC microgrids—Part I: A review of control strategies and stabilization techniques,” IEEE Trans. Power Electron., vol. 31, no. 7, pp. 4876–4891, 2016. doi:10.1109/TPEL.2015.2478859",
    "T. Lambert, P. Gilman, P. Lilienthal, “Micropower system modeling with HOMER,” in Integration of Alternative Sources of Energy, Wiley, 2006, ch. 15. doi:10.1002/0471755621.ch15",
    "M. A. Miner, “Cumulative damage in fatigue,” J. Appl. Mech., vol. 12, pp. A159–A164, 1945.  ·  ASTM E1049-85, Standard practices for cycle counting in fatigue analysis.",
]


def s_refs(D):
    sl = D.new("References", "References and acknowledgements",
               "Point to the full list in References.md and resources/SOURCES.md. Thank your supervisor, Kuldeep Kumar, "
               "the Department of Energy Engineering, and the providers of open data (NASA POWER) and the reference "
               "study. Then invite questions.")
    half = (len(REFS) + 1) // 2
    for col, refs in enumerate((REFS[:half], REFS[half:])):
        x = X0 + col * 6.1
        text(sl, x, 1.32, 5.9, 4.6,
             [{"runs": [(f"[{i + 1 + col * half}] ", {"bold": True, "color": NAVY}), (r, {})], "size": 10}
              for i, r in enumerate(refs)], size=10, color=BODY, space_after=3)
    box(sl, X0, 5.95, XW, 0.85, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    text(sl, X0 + 0.25, 5.95, XW - 0.5, 0.85, [
        {"runs": [("Acknowledgements  ", {"color": AMBER, "bold": True}),
                  ("Supervisor Kuldeep Kumar · Department of Energy Engineering, IIT Guwahati · NASA POWER open data. ",
                   {"color": WHITE}), ("Thank you — questions welcome.", {"color": AMBER, "bold": True})]}],
         size=14, anchor=MSO_ANCHOR.MIDDLE)


def main():
    D = Deck()
    for f in [s_title, s_outline, s_microgrid, s_demand, s_solar, s_motivation,
              s_landscape, s_reference, s_littable, s_gap, s_rqmap,
              s_architecture, s_pipeline, s_components, s_costs, s_formulation, s_simulator, s_pso,
              s_optimum, s_space, s_flows, s_battery,
              s_weather, s_sensitivity, s_reliability, s_montecarlo,
              s_growth, s_grid, s_sc1, s_sc2, s_cerc, s_discussion, s_conclusions, s_refs]:
        f(D)
    n = D.finish()
    with open("References.md", "w") as fh:
        fh.write("# References\n\nCited in `IITG_BTP_Microgrid_Presentation.pptx`. Every entry was checked against a "
                 "publisher, index or official record during preparation; see `Presentation_QA.md`. Project "
                 "results (all ₹ figures for this project) are generated by the Python model, not taken from these "
                 "sources.\n\n")
        for i, r in enumerate(REFS, 1):
            fh.write(f"{i}. {r}\n")
        fh.write("\nAlso used (methods and documentation): HOMER Pro online help pages on salvage value, economics, "
                 "total annualized cost and battery bank life (homerenergy.com); IIT Guwahati Central Workshop page "
                 "(iitg.ac.in/mech/workshop/), ME110 syllabus and Central Instruments Facility pages. Full list with "
                 "what each source was used for: `resources/SOURCES.md`.\n")
    print(f"wrote {OUT} ({n} slides), {NOTES_MD}, References.md")


if __name__ == "__main__":
    main()
