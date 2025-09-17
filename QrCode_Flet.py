#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gerador de Rótulos com QR — Biochar & Biomassa (Flet, com DatePicker e formato INFORMAÇÕES/JSON)

Ajustes:
- Cabeçalho estilizado (azul escuro) + botão de tema com ícones lua/sol.
- Formato "Informações" (legível) sem UUID, sem timestamp e sem hora; mostra apenas campos essenciais.
- Labels das notas com emoji de caderno (📒).
"""

import io
import json
import re
import textwrap
import datetime as dt
from pathlib import Path

import base64
import flet as ft
from PIL import Image, ImageDraw, ImageFont
import qrcode

SCHEMA = "arrakis.lab.qrlabel.v2"

# --- Compat com Flet 0.24–0.27+ ---
try:
    ControlState = ft.ControlState
except AttributeError:
    # versões antigas
    ControlState = ft.MaterialState

try:
    Colors = ft.Colors
except AttributeError:
    # fallback p/ constantes antigas; util with_opacity continua em ft.colors
    Colors = ft.colors


# ======================== Núcleo (render e utilitários) ========================
def _load_font(size=36):
    candidates = [
        str(Path(__file__).parent / "fonts" / "DejaVuSans-Bold.ttf"),  # fonte embutida
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/Library/Fonts/Arial Unicode.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for p in candidates:
        path = Path(p)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                continue
    return ImageFont.load_default()


def _titlecase(s: str) -> str:
    if not s:
        return s
    parts = s.split()
    out = []
    for p in parts:
        if len(p) <= 3 and p.isupper():
            out.append(p)  # provável sigla
        else:
            out.append(p[:1].upper() + p[1:].lower())
    return " ".join(out)

def _normalize_date(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        dd, mm, yyyy = m.groups()
        return f"{yyyy}-{mm}-{dd}"
    m = re.fullmatch(r"(\d{2})-(\d{2})-(\d{4})", s)
    if m:
        dd, mm, yyyy = m.groups()
        return f"{yyyy}-{mm}-{dd}"
    return s

def make_payload_biochar(sample_name, producer, biomass, reactor_type, pyro_temp_c,
                         residence_time_min, production_date=None, notes=None):
    return json.dumps({
        "kind": "biochar",
        "schema": SCHEMA,
        "sample_name": sample_name,
        "producer": producer,
        "biomass": biomass,
        "reactor_type": reactor_type,
        "pyro_temp_C": pyro_temp_c,
        "residence_time_min": residence_time_min,
        "production_date": _normalize_date(production_date or ""),
        "notes": (notes or "")
    }, ensure_ascii=False)

def make_payload_biomass(biomass_name, origin, collection_date=None, notes=None):
    return json.dumps({
        "kind": "biomass",
        "schema": SCHEMA,
        "biomass_name": biomass_name,
        "origin": origin,
        "collection_date": _normalize_date(collection_date or ""),
        "notes": (notes or "")
    }, ensure_ascii=False)

# ---------- Formato INFORMAÇÕES (legível no scanner) ----------
# Sem UUID, sem timestamp, sem hora — apenas dados essenciais.
def make_text_biochar(sample_name, producer, biomass, reactor_type, pyro_temp_c,
                      residence_time_min, production_date=None, notes=None):
    production_date = _normalize_date(production_date or "")
    lines = [
        f"Nome da amostra: {sample_name}",
        f"Biomassa: {biomass}",
        f"Quem produziu: {producer}",
        f"Tipo de reator: {reactor_type}",
        f"Temperatura de pirólise (°C): {pyro_temp_c}",
        f"Tempo de residência (min): {residence_time_min}",
    ]
    if production_date:
        lines.append(f"Data de produção: {production_date}")
    if notes:
        lines.append(f"Notas: {notes}")
    return "\n".join(lines)

def make_text_biomass(biomass_name, origin, collection_date=None, notes=None):
    collection_date = _normalize_date(collection_date or "")
    lines = [
        f"Nome da biomassa: {biomass_name}",
        f"Origem: {origin}",
    ]
    if collection_date:
        lines.append(f"Data de coleta: {collection_date}")
    if notes:
        lines.append(f"Notas: {notes}")
    return "\n".join(lines)

def _wrap_title_lines(title_text: str, font_title, label_width_px: int, padding: int, line_gap: int):
    dummy = Image.new("RGB", (label_width_px, 100), "white")
    draw_dummy = ImageDraw.Draw(dummy)
    text_w = draw_dummy.textbbox((0, 0), title_text, font=font_title)[2]
    if text_w > label_width_px - 2 * padding:
        est_chars = max(18, int(len(title_text) * (label_width_px - 2 * padding) / text_w))
        wrapped = textwrap.fill(title_text, width=est_chars)
        title_lines = wrapped.splitlines()
    else:
        title_lines = [title_text]
    tmp = Image.new("RGB", (label_width_px, 200), "white")
    dtmp = ImageDraw.Draw(tmp)
    heights = []
    for line in title_lines:
        bbox = dtmp.textbbox((0, 0), line, font=font_title)
        heights.append(bbox[3] - bbox[1])
    title_h = sum(heights) + line_gap * (len(heights) - 1)
    return title_lines, title_h

def render_label_pil(title_left, title_right, qr_payload, label_width_px=800, qr_box_size=10, border=4) -> Image.Image:
    # QR
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=qr_box_size,
        border=border
    )
    qr.add_data(qr_payload)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")

    # Layout
    font_title = _load_font(size=44)
    padding = 30
    line_gap = 8

    title_text = f"{title_left} | {title_right}" if title_right else f"{title_left}"
    title_lines, title_h = _wrap_title_lines(title_text, font_title, label_width_px, padding, line_gap)

    # Ajusta QR para caber
    qr_scale = min((label_width_px - 2 * padding) / qr_img.width, 1.0)
    new_w = int(qr_img.width * qr_scale)
    new_h = int(qr_img.height * qr_scale)
    try:
        from PIL.Image import Resampling
        qr_img_resized = qr_img.resize((new_w, new_h), Resampling.NEAREST)
    except Exception:
        qr_img_resized = qr_img.resize((new_w, new_h))

    total_h = padding + title_h + padding + new_h + padding
    canvas = Image.new("RGB", (label_width_px, total_h), "white")
    draw = ImageDraw.Draw(canvas)

    # Título
    y = padding
    for i, line in enumerate(title_lines):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        x = (label_width_px - lw) // 2
        draw.text((x, y), line, fill="black", font=font_title)
        y += lh + (line_gap if i < len(title_lines) - 1 else 0)

    # QR
    qr_x = (label_width_px - new_w) // 2
    qr_y = y + padding
    canvas.paste(qr_img_resized, (qr_x, qr_y))

    return canvas

def pil_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def _transparent_png_base64(w=2, h=2) -> str:
    img = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    return base64.b64encode(pil_to_png_bytes(img)).decode("ascii")


# ======================== UI (Flet) ========================
def main(page: ft.Page):
    page.title = "Gerador de Rótulos com QR — Biochar & Biomassa"
    page.padding = 16
    page.window.min_width = 1000
    page.window.min_height = 760
    page.theme_mode = ft.ThemeMode.LIGHT
    page.scroll = ft.ScrollMode.AUTO
    primary_color = "#0D47A1"  # azul escuro do cabeçalho

    # ===== Cabeçalho estilizado + tema (lua/sol) =====
    is_dark = False

    # --- Botão do tema (criamos antes para poder estilizar depois) ---
    theme_btn = ft.IconButton(
        tooltip="Alternar tema (claro/escuro)",
        on_click=lambda e: None,  # definiremos a função já já
    )

    # Estilização da "bolinha" do botão e ícone (ciano no claro, âmbar no escuro)
    def update_theme_button():
        circle_bg = Colors.AMBER_400 if not is_dark else Colors.CYAN_400
        icon_col  = Colors.BLACK
        theme_btn.style = ft.ButtonStyle(
            bgcolor={ControlState.DEFAULT: circle_bg},
            overlay_color={ControlState.HOVERED: Colors.with_opacity(0.12, Colors.WHITE)},
            shape=ft.CircleBorder(),
            padding=12,
            mouse_cursor=ft.MouseCursor.CLICK,
            elevation=2,
        )
        theme_btn.icon_color = icon_col
        theme_btn.icon = ft.icons.NIGHTLIGHT_ROUND if is_dark else ft.icons.WB_SUNNY

    def toggle_theme(e):
        nonlocal is_dark
        is_dark = not is_dark
        page.theme_mode = ft.ThemeMode.DARK if is_dark else ft.ThemeMode.LIGHT
        update_theme_button()
        page.update()

    # conecta o on_click agora
    theme_btn.on_click = toggle_theme
    # aplica aparência inicial
    update_theme_button()

    header = ft.Container(
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.Icon(ft.icons.QR_CODE_2, color="white", size=30),
                        ft.Text("Gerador de Rótulos com QR", size=22, weight=ft.FontWeight.BOLD, color="white"),
                    ],
                    spacing=10,
                ),
                ft.Container(expand=True),
                theme_btn,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        bgcolor=primary_color,
        padding=15,
        border_radius=ft.border_radius.only(0, 0, 12, 12),
    )

    # ===== Tabs =====
    tab = ft.Tabs(
        selected_index=0,
        animation_duration=150,
        tabs=[
            ft.Tab(text="Biochar", icon=ft.icons.SCIENCE),
            ft.Tab(text="Biomassa", icon=ft.icons.GRAIN),
        ],
        expand=0
    )

    # ===== Seletor de formato do QR (padrão: Informações) =====
    dd_format = ft.Dropdown(
        label="Formato do QR",
        value="Informações",
        options=[ft.dropdown.Option("Informações"), ft.dropdown.Option("json")],
        width=200,
    )

    # ---------------- Campos BIOCHAR ----------------
    tf_sample_name = ft.TextField(label="Nome da amostra", icon=ft.icons.LABEL, width=420)
    tf_biomass     = ft.TextField(label="Biomassa", icon=ft.icons.ECO, width=420)
    tf_producer    = ft.TextField(label="Quem produziu", icon=ft.icons.PERSON, width=260)
    tf_reactor     = ft.TextField(label="Tipo de reator", icon=ft.icons.BUILD, width=260)

    tf_prod_date   = ft.TextField(
        label="Data de produção",
        icon=ft.icons.EVENT,
        width=260,
        read_only=True,
        hint_text="YYYY-MM-DD"
    )
    dp_prod = ft.DatePicker(
        first_date=dt.date(2000,1,1),
        last_date=dt.date(2100,12,31),
        on_change=lambda e: (setattr(tf_prod_date, "value", str(e.control.value) or ""), page.update())
    )
    tf_prod_date.suffix = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, on_click=lambda e: page.open(dp_prod))

    tf_pyroC       = ft.TextField(label="Temperatura de pirólise (°C)", icon=ft.icons.THERMOSTAT, width=200, keyboard_type=ft.KeyboardType.NUMBER)
    tf_res_min     = ft.TextField(label="Tempo de residência (min)", icon=ft.icons.TIMER, width=200, keyboard_type=ft.KeyboardType.NUMBER)
    tf_notes_bc    = ft.TextField(label="Notas (opcional)", icon=ft.icons.NOTE, multiline=True, min_lines=2, max_lines=4, width=900)

    # ---------------- Campos BIOMASS ----------------
    tf_bm_name   = ft.TextField(label="Nome da biomassa", icon=ft.icons.ECO, width=420)
    tf_origin    = ft.TextField(label="Origem", icon=ft.icons.LOCATION_ON, width=420)

    tf_coll_date = ft.TextField(
        label="Data de coleta",
        icon=ft.icons.EVENT,
        width=260,
        read_only=True,
        hint_text="YYYY-MM-DD"
    )
    dp_coll = ft.DatePicker(
        first_date=dt.date(2000,1,1),
        last_date=dt.date(2100,12,31),
        on_change=lambda e: (setattr(tf_coll_date, "value", str(e.control.value) or ""), page.update())
    )
    tf_coll_date.suffix = ft.IconButton(icon=ft.icons.CALENDAR_MONTH, on_click=lambda e: page.open(dp_coll))

    tf_notes_bm  = ft.TextField(label="Notas (opcional)", icon=ft.icons.NOTE, multiline=True, min_lines=2, max_lines=4, width=900)

    # ---------- Prévia / Conteúdo e Zoom ----------
    img_preview = ft.Image(
        width=420,
        height=420,
        fit=ft.ImageFit.CONTAIN,
        border_radius=8,
        src_base64=_transparent_png_base64(),  # evita erro na 1ª renderização
    )

    qr_content_out = ft.TextField(label="Conteúdo do QR", multiline=True, min_lines=10, max_lines=18, width=420)
    zoom_slider = ft.Slider(min=0.5, max=1.5, divisions=10, value=1.0, label="{value}x", expand=1)

    zoom_row = ft.Row(
        [
            ft.Icon(ft.icons.ZOOM_IN_MAP),
            ft.Text("Zoom"),
            ft.Container(content=zoom_slider, expand=1),
        ],
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
    )


    current_png_bytes: bytes | None = None
    current_png_name: str = "label.png"

    file_save = ft.FilePicker(on_result=lambda e: None)
    page.overlay.extend([file_save, dp_prod, dp_coll])

    # Helpers
    def _titlecase_all_biochar():
        tf_sample_name.value = _titlecase(tf_sample_name.value or "")
        tf_biomass.value     = _titlecase(tf_biomass.value or "")
        tf_producer.value    = _titlecase(tf_producer.value or "")
        tf_reactor.value     = _titlecase(tf_reactor.value or "")

    def _titlecase_all_biomass():
        tf_bm_name.value = _titlecase(tf_bm_name.value or "")
        tf_origin.value  = _titlecase(tf_origin.value or "")

    def snack(msg, ok=False, warn=False):
        color = Colors.GREEN if ok else Colors.AMBER if warn else Colors.RED
        page.snack_bar = ft.SnackBar(content=ft.Text(msg), bgcolor=color)
        page.snack_bar.open = True
        page.update()

    def set_preview(png_bytes: bytes):
        img_preview.src_base64 = base64.b64encode(png_bytes).decode("ascii")
        factor = zoom_slider.value or 1.0
        img_preview.width = int(420 * factor)
        img_preview.height = int(420 * factor)

    def generate_preview(e=None):
        nonlocal current_png_bytes, current_png_name

        use_text = (dd_format.value or "Informações") == "Informações"

        if tab.selected_index == 0:
            # Biochar
            _titlecase_all_biochar()
            sn = (tf_sample_name.value or "").strip()
            bm = (tf_biomass.value or "").strip()
            if not sn:
                snack("Nome da amostra é obrigatório para Biochar.")
                return
            producer     = (tf_producer.value or "").strip()
            reactor_type = (tf_reactor.value or "").strip()
            prod_date    = _normalize_date(tf_prod_date.value or "")

            try:
                pyroC = float((tf_pyroC.value or "0").replace(",", "."))
            except ValueError:
                pyroC = 0.0
            try:
                res_min = float((tf_res_min.value or "0").replace(",", "."))
            except ValueError:
                res_min = 0.0
            notes = tf_notes_bc.value or ""

            if use_text:
                payload = make_text_biochar(sn, producer, bm, reactor_type, pyroC, res_min, prod_date, notes)
            else:
                payload = make_payload_biochar(sn, producer, bm, reactor_type, pyroC, res_min, prod_date, notes)

            title_left  = _titlecase(sn)
            title_right = _titlecase(bm)
            current_png_name = f"{title_left.replace(' ', '_')}_label.png"

        else:
            # Biomassa
            _titlecase_all_biomass()
            bn = (tf_bm_name.value or "").strip()
            og = (tf_origin.value or "").strip()
            if not bn or not og:
                snack("Nome da biomassa e Origem são obrigatórios para Biomassa.")
                return
            coll_date = _normalize_date(tf_coll_date.value or "")
            notes = tf_notes_bm.value or ""

            if use_text:
                payload = make_text_biomass(bn, og, coll_date, notes)
            else:
                payload = make_payload_biomass(bn, og, coll_date, notes)

            title_left  = _titlecase(bn)
            title_right = _titlecase(og)
            current_png_name = f"{title_left.replace(' ', '_')}_label.png"

        pil_img = render_label_pil(title_left, title_right, payload, label_width_px=800, qr_box_size=10, border=4)
        png_bytes = pil_to_png_bytes(pil_img)
        current_png_bytes = png_bytes
        set_preview(png_bytes)
        qr_content_out.value = payload
        page.update()

    def save_png(e=None):
        nonlocal current_png_bytes
        if not current_png_bytes:
            generate_preview()
            if not current_png_bytes:
                return

        def _save_result(res: ft.FilePickerResultEvent):
            if not res.path:
                return
            try:
                Path(res.path).write_bytes(current_png_bytes)
                snack(f"Salvo em: {res.path}", ok=True)
            except Exception as ex:
                snack(f"Erro ao salvar: {ex}")

        file_save.on_result = _save_result
        file_save.save_file(file_name=current_png_name, allowed_extensions=["png"])

    def copy_qr_content(e=None):
        if not qr_content_out.value:
            generate_preview()
            if not qr_content_out.value:
                return
        page.set_clipboard(qr_content_out.value)
        snack("Conteúdo copiado.", warn=True)

    def on_zoom_change(e=None):
        if not getattr(img_preview, "src_base64", None):
            return
        factor = zoom_slider.value or 1.0
        img_preview.width = int(420 * factor)
        img_preview.height = int(420 * factor)
        page.update()


    zoom_slider.on_change = on_zoom_change

    # ---------- Cards ----------
    biochar_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.SCIENCE, color=Colors.BLUE), ft.Text("Biochar", size=16, weight=ft.FontWeight.BOLD)]),
                ft.Divider(),
                ft.ResponsiveRow([
                    ft.Container(tf_sample_name, col={"xs":12,"md":6}),
                    ft.Container(tf_biomass,     col={"xs":12,"md":6}),
                    ft.Container(tf_producer,    col={"xs":12,"md":4}),
                    ft.Container(tf_reactor,     col={"xs":12,"md":4}),
                    ft.Container(tf_prod_date,   col={"xs":12,"md":4}),
                    ft.Container(tf_pyroC,       col={"xs":12,"md":6}),
                    ft.Container(tf_res_min,     col={"xs":12,"md":6}),
                    ft.Container(tf_notes_bc,    col={"xs":12}),
                ], spacing=12)
            ], tight=True),
            padding=16
        )
    )

    biomass_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.GRAIN, color=Colors.BLUE), ft.Text("Biomassa", size=16, weight=ft.FontWeight.BOLD)]),
                ft.Divider(),
                ft.ResponsiveRow([
                    ft.Container(tf_bm_name,   col={"xs":12,"md":6}),
                    ft.Container(tf_origin,    col={"xs":12,"md":6}),
                    ft.Container(tf_coll_date, col={"xs":12,"md":4}),
                    ft.Container(tf_notes_bm,  col={"xs":12}),
                ], spacing=12)
            ], tight=True),
            padding=16
        )
    )

    # Ações
    btn_generate = ft.ElevatedButton("Gerar prévia", icon=ft.icons.QR_CODE_2, on_click=generate_preview)
    btn_save     = ft.OutlinedButton("Salvar PNG", icon=ft.icons.DOWNLOAD, on_click=save_png)
    btn_copy     = ft.OutlinedButton("Copiar conteúdo", icon=ft.icons.CONTENT_COPY, on_click=copy_qr_content)

    actions = ft.Row([dd_format, btn_generate, btn_save, btn_copy], spacing=12)

    # Prévia/Conteúdo
    preview_card = ft.Card(
        content=ft.Container(
            content=ft.Column([
                ft.Row([ft.Icon(ft.icons.IMAGE, color=Colors.BLUE), ft.Text("Prévia", size=16, weight=ft.FontWeight.BOLD)]),
                ft.Divider(),
                ft.Container(
                    img_preview,
                    bgcolor=Colors.WHITE,
                    padding=10,
                    border_radius=10,
                    shadow=ft.BoxShadow(blur_radius=8, color=Colors.with_opacity(0.2, Colors.BLACK)),
                ),
                #ft.Row([ft.Icon(ft.icons.ZOOM_IN_MAP), ft.Text("Zoom"), zoom_slider], alignment=ft.MainAxisAlignment.START),
                zoom_row,
                ft.Divider(),
                ft.Row([ft.Icon(ft.icons.DATA_OBJECT), ft.Text("Conteúdo do QR", size=14, weight=ft.FontWeight.W_600)]),
                qr_content_out
            ], tight=True),
            padding=16,
            width=460
        )
    )

    left_panel = ft.Column([biochar_card, actions], spacing=12, expand=1)
    right_panel = ft.Column([preview_card], spacing=12)

    def on_tab_change(e):
        left_panel.controls[0] = biochar_card if tab.selected_index == 0 else biomass_card
        page.update()

    tab.on_change = on_tab_change

    # ===== Layout final: header no topo, depois conteúdo =====
    body = ft.Row(
        [
            ft.Container(
                ft.Column([tab, left_panel], spacing=12, expand=True),
                expand=True,
            ),
            ft.Container(right_panel, expand=True),
        ],
        spacing=16,
        vertical_alignment=ft.CrossAxisAlignment.START,  # 🔑 força alinhamento pelo topo
    )


    page.add(header, body)

if __name__ == "__main__":
    import os
    port = int(os.getenv("PORT", "8080"))
    ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="0.0.0.0", port=port)
