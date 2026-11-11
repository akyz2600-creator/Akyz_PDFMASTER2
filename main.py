import os
import io
from pathlib import Path

from kivy.app import App
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.utils import get_color_from_hex

from plyer import filechooser
from pypdf import PdfWriter


BG = "#101827"
PANEL = "#1B2940"
BLUE = "#2878F0"
TEXT = "#F4F7FB"
MUTED = "#AAB8CC"
GREEN = "#20A879"
RED = "#D9534F"



def jpeg_dimensions(data):
    """Read width, height and component count from a JPEG SOF marker."""
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        raise ValueError("El archivo no parece ser un JPEG válido.")
    i = 2
    sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while i < len(data):
        while i < len(data) and data[i] != 0xFF:
            i += 1
        while i < len(data) and data[i] == 0xFF:
            i += 1
        if i >= len(data):
            break
        marker = data[i]
        i += 1
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            continue
        if i + 2 > len(data):
            break
        length = int.from_bytes(data[i:i+2], "big")
        if length < 2 or i + length > len(data):
            break
        if marker in sof:
            if length < 8:
                break
            height = int.from_bytes(data[i+3:i+5], "big")
            width = int.from_bytes(data[i+5:i+7], "big")
            components = data[i+7]
            if width and height and components in (1, 3, 4):
                return width, height, components
            break
        i += length
    raise ValueError("No se pudieron leer las dimensiones del JPEG.")


def jpeg_files_to_pdf(paths):
    """Build a PDF with original JPEG byte streams (no image recompression)."""
    objects = []

    def add_object(body):
        objects.append(body)
        return len(objects)

    catalog_id = add_object(b"")
    pages_id = add_object(b"")
    page_ids = []

    for path in paths:
        raw = Path(path).read_bytes()
        width, height, components = jpeg_dimensions(raw)
        if components == 1:
            colorspace = b"/DeviceGray"
        elif components == 3:
            colorspace = b"/DeviceRGB"
        else:
            colorspace = b"/DeviceCMYK"

        # Ajusta la página al tamaño A4 sin cambiar ni recomprimir el JPEG.
        if width >= height:
            box_w, box_h = 841.89, 595.28
        else:
            box_w, box_h = 595.28, 841.89
        scale = min(box_w / width, box_h / height)
        page_w = width * scale
        page_h = height * scale

        image_id = len(objects) + 1
        content_id = image_id + 1
        page_id = image_id + 2

        image_obj = (
            b"<< /Type /XObject /Subtype /Image /Width " + str(width).encode() +
            b" /Height " + str(height).encode() +
            b" /ColorSpace " + colorspace +
            b" /BitsPerComponent 8 /Filter /DCTDecode /Length " +
            str(len(raw)).encode() + b" >>\nstream\n" + raw + b"\nendstream"
        )
        content = (
            b"q\n" + ("%.4f" % page_w).encode() + b" 0 0 " +
            ("%.4f" % page_h).encode() + b" 0 0 cm\n/Im0 Do\nQ"
        )
        content_obj = b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream"
        page_obj = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 " +
            ("%.4f" % page_w).encode() + b" " + ("%.4f" % page_h).encode() +
            b"] /Resources << /XObject << /Im0 " + str(image_id).encode() +
            b" 0 R >> >> /Contents " + str(content_id).encode() + b" 0 R >>"
        )
        add_object(image_obj)
        add_object(content_obj)
        page_ids.append(add_object(page_obj))

    kids = b" ".join(str(x).encode() + b" 0 R" for x in page_ids)
    objects[catalog_id - 1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[pages_id - 1] = (
        b"<< /Type /Pages /Kids [" + kids + b"] /Count " +
        str(len(page_ids)).encode() + b" >>"
    )

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(str(number).encode() + b" 0 obj\n")
        output.extend(body)
        output.extend(b"\nendobj\n")

    xref_offset = len(output)
    output.extend(b"xref\n0 " + str(len(objects) + 1).encode() + b"\n")
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() +
        b" /Root 1 0 R >>\nstartxref\n" +
        str(xref_offset).encode() + b"\n%%EOF\n"
    )
    return bytes(output)


class AkyzPDFMaster(App):
    def build(self):
        self.title = "Akyz_PDFMASTER"
        self.mode = None
        self.files = []

        root = BoxLayout(orientation="vertical", padding=dp(16), spacing=dp(12))
        root.canvas.before.clear()
        with root.canvas.before:
            from kivy.graphics import Color, Rectangle
            Color(*get_color_from_hex(BG))
            self.bg_rect = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)

        header = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(82), spacing=dp(3))
        header.add_widget(Label(text="[b]AKYZ_PDFMASTER[/b]", markup=True,
                                color=get_color_from_hex(TEXT), font_size="23sp",
                                halign="left", valign="middle"))
        header.add_widget(Label(text="Herramientas PDF · Sin conexión · Gratis",
                                color=get_color_from_hex(MUTED), font_size="12sp",
                                halign="left", valign="middle"))
        root.add_widget(header)

        self.menu = BoxLayout(orientation="vertical", spacing=dp(12))
        self.btn_images = self.make_button("🖼  CONVERTIR JPEG A PDF", BLUE, self.start_images)
        self.btn_merge = self.make_button("📄  UNIR ARCHIVOS PDF", GREEN, self.start_pdfs)
        self.menu.add_widget(self.btn_images)
        self.menu.add_widget(self.btn_merge)
        root.add_widget(self.menu)

        self.workspace = BoxLayout(orientation="vertical", spacing=dp(9))
        self.workspace.opacity = 0
        self.workspace.disabled = True

        self.mode_label = Label(text="", size_hint_y=None, height=dp(34),
                                color=get_color_from_hex(TEXT), font_size="17sp")
        self.workspace.add_widget(self.mode_label)

        actions = GridLayout(cols=2, spacing=dp(8), size_hint_y=None, height=dp(48))
        self.add_button = self.make_button("＋ Agregar archivos", BLUE, self.add_files, font_size="14sp")
        self.clear_button = self.make_button("Limpiar lista", RED, self.clear_files, font_size="14sp")
        actions.add_widget(self.add_button)
        actions.add_widget(self.clear_button)
        self.workspace.add_widget(actions)

        self.list_label = Label(text="Todavía no has seleccionado archivos.",
                                color=get_color_from_hex(MUTED), size_hint_y=None,
                                height=dp(35), font_size="13sp")
        self.workspace.add_widget(self.list_label)

        scroll = ScrollView()
        self.file_list = GridLayout(cols=1, spacing=dp(6), size_hint_y=None, padding=(0, dp(2)))
        self.file_list.bind(minimum_height=self.file_list.setter("height"))
        scroll.add_widget(self.file_list)
        self.workspace.add_widget(scroll)

        reorder = GridLayout(cols=3, spacing=dp(8), size_hint_y=None, height=dp(44))
        reorder.add_widget(self.make_button("↑ Subir", PANEL, lambda *_: self.move_file(-1), "13sp"))
        reorder.add_widget(self.make_button("↓ Bajar", PANEL, lambda *_: self.move_file(1), "13sp"))
        reorder.add_widget(self.make_button("✕ Quitar", RED, self.remove_last, "13sp"))
        self.workspace.add_widget(reorder)

        self.status = Label(text="Selecciona archivos para comenzar.",
                            color=get_color_from_hex(MUTED), size_hint_y=None,
                            height=dp(38), font_size="12sp")
        self.workspace.add_widget(self.status)

        self.create_button = self.make_button("CREAR PDF", GREEN, self.create_pdf)
        self.workspace.add_widget(self.create_button)
        self.back_button = self.make_button("← Volver al inicio", PANEL, self.go_home, "13sp")
        self.workspace.add_widget(self.back_button)

        root.add_widget(self.workspace)
        self.show_home()
        return root

    def _update_bg(self, widget, *_):
        self.bg_rect.pos = widget.pos
        self.bg_rect.size = widget.size

    def make_button(self, title, color, callback, font_size="15sp"):
        b = Button(text=title, size_hint_y=None, height=dp(52),
                   background_normal="", background_down="",
                   background_color=get_color_from_hex(color),
                   color=get_color_from_hex(TEXT), font_size=font_size,
                   bold=True)
        b.bind(on_release=callback)
        return b

    def show_home(self):
        self.menu.opacity = 1
        self.menu.disabled = False
        self.workspace.opacity = 0
        self.workspace.disabled = True

    def start_images(self, *_):
        self.mode = "images"
        self.files = []
        self.mode_label.text = "CONVERTIR JPEG A PDF"
        self.create_button.text = "CONVERTIR Y GUARDAR PDF"
        self.show_workspace()
        self.status.text = "Agrega una o varias imágenes JPG/JPEG."

    def start_pdfs(self, *_):
        self.mode = "pdf"
        self.files = []
        self.mode_label.text = "UNIR DOCUMENTOS PDF"
        self.create_button.text = "UNIR Y GUARDAR PDF"
        self.show_workspace()
        self.status.text = "Agrega dos o más archivos PDF."

    def show_workspace(self):
        self.menu.opacity = 0
        self.menu.disabled = True
        self.workspace.opacity = 1
        self.workspace.disabled = False
        self.refresh_list()

    def go_home(self, *_):
        self.files = []
        self.mode = None
        self.show_home()

    def add_files(self, *_):
        if self.mode == "images":
            filechooser.open_file(
                multiple=True, filters=["image"],
                on_selection=self.on_files_selected
            )
        elif self.mode == "pdf":
            filechooser.open_file(
                multiple=True, filters=["pdf"],
                on_selection=self.on_files_selected
            )

    def on_files_selected(self, selection):
        if not selection:
            self.status.text = "No se seleccionaron archivos."
            return
        added = 0
        for item in selection:
            path = str(item)
            ext = Path(path).suffix.lower()
            if self.mode == "images" and ext not in (".jpg", ".jpeg"):
                continue
            if self.mode == "pdf" and ext != ".pdf":
                continue
            if path not in self.files:
                self.files.append(path)
                added += 1
        self.refresh_list()
        self.status.text = f"Se agregaron {added} archivo(s)." if added else "No se agregaron archivos compatibles."

    def refresh_list(self):
        self.file_list.clear_widgets()
        self.list_label.text = f"Archivos seleccionados: {len(self.files)}"
        for i, path in enumerate(self.files):
            row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(4),
                            padding=(dp(5), 0))
            row.canvas.before.clear()
            with row.canvas.before:
                from kivy.graphics import Color, RoundedRectangle
                Color(*get_color_from_hex(PANEL))
                row.bg = RoundedRectangle(pos=row.pos, size=row.size, radius=[dp(8)])
            row.bind(pos=lambda w, *_: setattr(w.bg, "pos", w.pos),
                     size=lambda w, *_: setattr(w.bg, "size", w.size))
            name = Path(path).name
            row.add_widget(Label(text=f"{i+1}. {name}", color=get_color_from_hex(TEXT),
                                 halign="left", shorten=True, shorten_from="right",
                                 font_size="11sp"))
            up = Button(text="↑", size_hint_x=None, width=dp(38),
                        background_normal="", background_color=get_color_from_hex(BLUE))
            up.bind(on_release=lambda _btn, index=i: self.move_file(index, -1))
            down = Button(text="↓", size_hint_x=None, width=dp(38),
                          background_normal="", background_color=get_color_from_hex(BLUE))
            down.bind(on_release=lambda _btn, index=i: self.move_file(index, 1))
            delete = Button(text="×", size_hint_x=None, width=dp(38),
                            background_normal="", background_color=get_color_from_hex(RED))
            delete.bind(on_release=lambda _btn, index=i: self.remove_file(index))
            row.add_widget(up)
            row.add_widget(down)
            row.add_widget(delete)
            self.file_list.add_widget(row)

    def clear_files(self, *_):
        self.files = []
        self.refresh_list()
        self.status.text = "Lista vacía."

    def move_file(self, index, direction):
        target = index + direction
        if 0 <= index < len(self.files) and 0 <= target < len(self.files):
            self.files[index], self.files[target] = self.files[target], self.files[index]
            self.refresh_list()
            self.status.text = "Orden actualizado."

    def remove_file(self, index):
        if 0 <= index < len(self.files):
            removed = self.files.pop(index)
            self.refresh_list()
            self.status.text = f"Quitado: {Path(removed).name}"

    def create_pdf(self, *_):
        if not self.files:
            self.show_message("Faltan archivos", "Primero agrega archivos.")
            return
        try:
            if self.mode == "images":
                # Se incrustan los bytes JPEG originales, sin recompresión.
                output = jpeg_files_to_pdf(self.files)
                suggested = "Akyz_imagenes.pdf"
            else:
                if len(self.files) < 2:
                    self.show_message("Faltan PDF", "Selecciona al menos dos PDF para unir.")
                    return
                writer = PdfWriter()
                for path in self.files:
                    writer.append(path)
                buffer = io.BytesIO()
                writer.write(buffer)
                writer.close()
                output = buffer.getvalue()
                suggested = "Akyz_documentos_unidos.pdf"

            self.pending_output = output
            self.status.text = "PDF listo. Elige dónde guardarlo."
            filechooser.save_file(
                title=suggested,
                filters=["pdf"],
                callback=self.save_output
            )
        except Exception as exc:
            self.show_message("No se pudo crear el PDF", str(exc))
            self.status.text = "Ocurrió un error al procesar los archivos."

    def save_output(self, stream):
        try:
            # Plyer Android devuelve un java.io.FileOutputStream.
            # Pyjnius convierte bytes de Python al byte[] de Java.
            stream.write(self.pending_output)
            stream.flush()
            stream.close()
            self.status.text = "PDF guardado correctamente."
            self.show_message("¡Listo!", "Tu PDF se guardó en la ubicación que elegiste.")
        except Exception as exc:
            self.show_message("Error al guardar", str(exc))
            self.status.text = "No se pudo guardar el archivo."

    def show_message(self, title, message):
        content = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(10))
        content.add_widget(Label(text=message, color=get_color_from_hex(TEXT)))
        close = self.make_button("ACEPTAR", BLUE, lambda *_: popup.dismiss(), "13sp")
        content.add_widget(close)
        popup = Popup(title=title, content=content, size_hint=(0.88, 0.42),
                      separator_color=get_color_from_hex(BLUE))
        popup.open()


if __name__ == "__main__":
    AkyzPDFMaster().run()
