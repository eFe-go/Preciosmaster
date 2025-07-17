import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading # Para que la interfaz no se congele al procesar
import pyperclip # Para copiar al portapapeles
import re
import sys
import io # Para manejar strings como si fueran archivos (para csv)
import csv # Lo usaremos para formatear la salida para el portapapeles
import json # Para manejar el archivo de configuración
import os # Para verificar si existe el archivo de configuración
import math # Para redondear precios

# --- Configuración ---
DESC_SLICE_APPROX = slice(19, 49) # Posiciones 20 a 49
BARCODE_PATTERN = re.compile(r'(?:HE|UC)(\d{13})')
PRICE_LIKE_PATTERN = re.compile(r'(0\d{12})')
MIN_LINE_LENGTH = 160
CONFIG_FILE = 'divisores_config.json'

# --- Carga de configuración ---
def load_config():
    """Carga la configuración desde el archivo JSON"""
    config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILE)
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Error al cargar configuración: {e}")
    return {
        "divisores": {},
        "configuracion": {
            "color_asoprofarma": "#2ECC40",
            "color_delsud": "#0074D9",
            "mostrar_diferencia": True,
            "resaltar_mejor_precio": True
        }
    }

def save_config(config):
    """Guarda la configuración en el archivo JSON"""
    config_path = os.path.join(os.path.dirname(__file__), CONFIG_FILE)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        messagebox.showerror("Error", f"Error al guardar configuración: {e}")
        return False

# Cargar configuración inicial
CONFIG = load_config()
TARGET_DIVISORS = CONFIG.get('divisores', {})

# --- Función de redondeo ---
def round_price_up(price):
    """Redondea al múltiplo de 100 más cercano con umbral en 41 para evitar dar cambio de 50"""
    base = int(price // 100) * 100  # Parte base (ej: 4800 para 4802)
    remainder = price - base        # Parte decimal (ej: 2 para 4802)
    
    if remainder >= 41:
        return base + 100  # Redondear hacia arriba (ej: 4841 → 4900)
    else:
        return base        # Redondear hacia abajo (ej: 4840 → 4800)

# --- Funciones de Procesamiento ---
def detect_file_type(filename):
    """Detecta si el archivo es TXT o CSV basado en la extensión"""
    return 'csv' if filename.lower().endswith('.csv') else 'txt'

def detect_drugstore_from_filename(filename):
    """Detecta qué droguería es basado en el nombre del archivo"""
    filename_lower = filename.lower()
    if 'asopro' in filename_lower or 'asoprofarma' in filename_lower:
        return 'asoprofarma'
    elif 'sud' in filename_lower or 'delsud' in filename_lower or 'del_sud' in filename_lower:
        return 'delsud'
    elif 'catalogo' in filename_lower:
        # Los archivos Catalogo* son típicamente de ASOPRO
        return 'asoprofarma'
    else:
        # Por defecto, asumir que es delsud si no se puede determinar
        return 'delsud'

def process_csv_file_for_drugstore(filename):
    """Procesa archivos CSV con formato catalogo para una droguería específica"""
    results = {}
    drugstore = detect_drugstore_from_filename(filename)
    
    try:
        with open(filename, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                # Handle column names with leading spaces
                barcode = row.get('Codigo de barras', row.get(' Codigo de barras', '')).strip()
                # Remover prefijos si existen
                if barcode.startswith(('HE', 'UC')):
                    barcode = barcode[2:]
                
                if barcode in TARGET_DIVISORS:
                    descripcion = row.get('Descripcion', row.get(' Descripcion', '')).strip()
                    
                    # Usar columna apropiada según la droguería
                    if drugstore == 'asoprofarma':
                        # Para Asoprofarma, usar columna "Publico" si existe, sino "Costo s/IVA"
                        if 'Publico' in row or ' Publico' in row:
                            precio_str = row.get('Publico', row.get(' Publico', '0')).replace(',', '.')
                        else:
                            precio_str = row.get('Costo s/IVA', row.get(' Costo s/IVA', '0')).replace(',', '.')
                    else:
                        # Para Del Sud, usar Costo s/IVA
                        precio_str = row.get('Costo s/IVA', row.get(' Costo s/IVA', '0')).replace(',', '.')
                    
                    try:
                        precio_base = float(precio_str)
                        divisor = TARGET_DIVISORS[barcode].get('divisor', 1)
                        precio_unitario = precio_base / divisor
                        
                        results[barcode] = {
                            'descripcion': descripcion,
                            'barcode': barcode,
                            'divisor': divisor,
                            'precio_base': precio_base,
                            'precio_unitario': precio_unitario,
                            'drugstore': drugstore
                        }
                    except ValueError as e:
                        # Log detailed error information for debugging
                        if drugstore == 'asoprofarma':
                            if 'Publico' in row or ' Publico' in row:
                                column_used = 'Publico'
                            else:
                                column_used = 'Costo s/IVA'
                        else:
                            column_used = 'Costo s/IVA'
                        print(f"Error procesando precio para código {barcode}: '{precio_str}' en columna '{column_used}' no es un número válido", file=sys.stderr)
                        pass
                    except ZeroDivisionError:
                        print(f"Error procesando código {barcode}: divisor es cero", file=sys.stderr)
                        pass
    
    except FileNotFoundError:
        raise
    except Exception as e:
        raise
    
    return results

def process_txt_file_for_drugstore(filename):
    """
    Procesa archivos TXT con formato maestros para una droguería específica
    """
    results = {}
    drugstore = detect_drugstore_from_filename(filename)
    
    try:
        with open(filename, 'r', encoding='latin-1') as infile:
            for line_number, line in enumerate(infile, 1):
                line = line.rstrip('\r\n')

                if not line or not line.startswith('D') or len(line) < MIN_LINE_LENGTH:
                    continue

                barcode_match = BARCODE_PATTERN.search(line)
                if not barcode_match: continue

                current_barcode = barcode_match.group(1)
                barcode_end_pos = barcode_match.end()

                if current_barcode in TARGET_DIVISORS:
                    try:
                        potential_prices = PRICE_LIKE_PATTERN.findall(line, pos=barcode_end_pos)

                        pvp_str = None
                        if len(potential_prices) >= 2: pvp_str = potential_prices[1]
                        elif len(potential_prices) == 1: pvp_str = potential_prices[0]
                        else: continue

                        if len(line) >= DESC_SLICE_APPROX.stop:
                            descripcion = line[DESC_SLICE_APPROX].strip()
                        else:
                            descripcion = "ERROR_DESC_CORTA"

                        pvp_int = int(pvp_str)
                        precio_base = float(pvp_int) / 100.0
                        divisor = TARGET_DIVISORS[current_barcode].get('divisor', 1)
                        precio_unitario = precio_base / divisor
                        
                        results[current_barcode] = {
                            'descripcion': descripcion,
                            'barcode': current_barcode,
                            'divisor': divisor,
                            'precio_base': precio_base,
                            'precio_unitario': precio_unitario,
                            'drugstore': drugstore
                        }
                    except ValueError:
                        pass
                    except Exception as e:
                        print(f"Error procesando línea {line_number}: {e}", file=sys.stderr)

    except FileNotFoundError:
        raise
    except Exception as e:
        raise

    return results

def process_file(filename):
    """Función principal que detecta el tipo de archivo y lo procesa para una droguería"""
    file_type = detect_file_type(filename)
    if file_type == 'csv':
        return process_csv_file_for_drugstore(filename)
    else:
        return process_txt_file_for_drugstore(filename)

# --- Clase de la Aplicación GUI ---
class App:
    def __init__(self, root):
        """Inicializa la interfaz gráfica de usuario."""
        self.root = root
        self.root.title("Procesador de Precios - Comparador de Droguerías v2.0")
        self.root.geometry("1200x700")
        
        # Cargar configuración
        self.config = CONFIG
        self.color_asopro = self.config['configuracion']['color_asoprofarma']
        self.color_sud = self.config['configuracion']['color_delsud']

        # Variables de Tkinter para archivos separados
        self.filepath_asopro = tk.StringVar()
        self.filepath_sud = tk.StringVar()
        self.status_text = tk.StringVar()
        self.status_text.set("Seleccione archivos para ambas droguerías (TXT o CSV).")

        # --- Frame superior para selección de archivos ---
        top_frame = ttk.Frame(root, padding="10")
        top_frame.pack(fill=tk.X)

        # Archivo Asoprofarma
        asopro_frame = ttk.Frame(top_frame)
        asopro_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(asopro_frame, text="Archivo Asoprofarma:", width=20).pack(side=tk.LEFT, padx=5)
        self.file_entry_asopro = ttk.Entry(asopro_frame, textvariable=self.filepath_asopro, width=50, state='readonly')
        self.file_entry_asopro.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.select_button_asopro = ttk.Button(asopro_frame, text="Seleccionar...", command=self.select_file_asopro)
        self.select_button_asopro.pack(side=tk.LEFT, padx=5)
        
        # Archivo Del Sud
        sud_frame = ttk.Frame(top_frame)
        sud_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(sud_frame, text="Archivo Del Sud:", width=20).pack(side=tk.LEFT, padx=5)
        self.file_entry_sud = ttk.Entry(sud_frame, textvariable=self.filepath_sud, width=50, state='readonly')
        self.file_entry_sud.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.select_button_sud = ttk.Button(sud_frame, text="Seleccionar...", command=self.select_file_sud)
        self.select_button_sud.pack(side=tk.LEFT, padx=5)

        # --- Frame de botones ---
        button_frame = ttk.Frame(root, padding="5")
        button_frame.pack(fill=tk.X)
        
        self.process_button = ttk.Button(button_frame, text="Procesar y Comparar", command=self.start_processing, state=tk.DISABLED)
        self.process_button.pack(side=tk.LEFT, padx=5)
        
        self.config_button = ttk.Button(button_frame, text="Configurar Códigos", command=self.open_config_window)
        self.config_button.pack(side=tk.LEFT, padx=5)

        # --- Frame de leyenda de colores ---
        legend_frame = ttk.Frame(root, padding="5")
        legend_frame.pack(fill=tk.X)
        
        tk.Label(legend_frame, text="Leyenda:", font=('Arial', 10, 'bold')).pack(side=tk.LEFT, padx=5)
        tk.Label(legend_frame, text="PRECIO ALTO", bg='#E8F5E9', fg="black", padx=10, pady=2, font=('Arial', 9, 'underline')).pack(side=tk.LEFT, padx=5)
        tk.Label(legend_frame, text="DISPONIBLE", bg='#F0F8FF', fg="black", padx=10, pady=2).pack(side=tk.LEFT, padx=5)
        tk.Label(legend_frame, text="(Precio sugerido redondeado hacia arriba)", font=('Arial', 9, 'italic')).pack(side=tk.LEFT, padx=10)

        # --- Frame para la tabla de resultados ---
        tree_frame = ttk.Frame(root, padding="10")
        tree_frame.pack(expand=True, fill=tk.BOTH)

        # Crear la tabla con columnas para mostrar ambas droguerías incluyendo precio base
        columns = ("Descripción", "Divisor", "Precio Base", "Precio Unitario", "Droguería", "Precio Sugerido")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=20)
        
        # Configurar encabezados
        self.tree.heading("Descripción", text="Descripción del Producto")
        self.tree.heading("Divisor", text="Divisor")
        self.tree.heading("Precio Base", text="Precio Base")
        self.tree.heading("Precio Unitario", text="Precio Unitario")
        self.tree.heading("Droguería", text="Droguería")
        self.tree.heading("Precio Sugerido", text="Precio Sugerido")

        # Ajustar ancho de columnas
        self.tree.column("Descripción", width=300, anchor=tk.W)
        self.tree.column("Divisor", width=70, anchor=tk.CENTER)
        self.tree.column("Precio Base", width=100, anchor=tk.E)
        self.tree.column("Precio Unitario", width=110, anchor=tk.E)
        self.tree.column("Droguería", width=100, anchor=tk.CENTER)
        self.tree.column("Precio Sugerido", width=110, anchor=tk.E)
        
        # Configurar tags para colores simplificados
        self.tree.tag_configure('disponible', background='#F0F8FF', font=('Arial', 9))
        self.tree.tag_configure('precio_alto', background='#E8F5E9', font=('Arial', 9, 'underline'))
        self.tree.tag_configure('no_disponible', background='#F5F5F5', font=('Arial', 9), foreground='#999999')

        # Scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # --- Frame de botones inferiores ---
        bottom_frame = ttk.Frame(root, padding="5")
        bottom_frame.pack(fill=tk.X)
        
        self.copy_button = ttk.Button(bottom_frame, text="Copiar al Portapapeles", command=self.copy_to_clipboard, state=tk.DISABLED)
        self.copy_button.pack(side=tk.LEFT, padx=5)
        
        self.export_button = ttk.Button(bottom_frame, text="Exportar a CSV", command=self.export_to_csv, state=tk.DISABLED)
        self.export_button.pack(side=tk.LEFT, padx=5)

        # --- Barra de estado ---
        status_bar = ttk.Label(root, textvariable=self.status_text, relief=tk.SUNKEN, anchor=tk.W, padding="2 5")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def select_file_asopro(self):
        """Abre el diálogo para seleccionar archivo de Asoprofarma."""
        filename = filedialog.askopenfilename(
            title="Seleccionar archivo de Asoprofarma",
            filetypes=(
                ("Archivos soportados", "*.txt;*.csv"),
                ("Archivos de Texto", "*.txt"),
                ("Archivos CSV", "*.csv"),
                ("Todos los archivos", "*.*")
            )
        )
        if filename:
            self.filepath_asopro.set(filename)
            file_type = detect_file_type(filename)
            self.update_status_and_buttons()
            # Limpiar resultados anteriores
            for item in self.tree.get_children():
                self.tree.delete(item)
    
    def select_file_sud(self):
        """Abre el diálogo para seleccionar archivo de Del Sud."""
        filename = filedialog.askopenfilename(
            title="Seleccionar archivo de Del Sud",
            filetypes=(
                ("Archivos soportados", "*.txt;*.csv"),
                ("Archivos de Texto", "*.txt"),
                ("Archivos CSV", "*.csv"),
                ("Todos los archivos", "*.*")
            )
        )
        if filename:
            self.filepath_sud.set(filename)
            file_type = detect_file_type(filename)
            self.update_status_and_buttons()
            # Limpiar resultados anteriores
            for item in self.tree.get_children():
                self.tree.delete(item)
    
    def update_status_and_buttons(self):
        """Actualiza el estado de la interfaz según los archivos seleccionados."""
        asopro_file = self.filepath_asopro.get()
        sud_file = self.filepath_sud.get()
        
        if asopro_file and sud_file:
            self.status_text.set(f"Archivos listos: Asopro ({os.path.basename(asopro_file)}) - Sud ({os.path.basename(sud_file)})")
            self.process_button.config(state=tk.NORMAL)
        elif asopro_file:
            self.status_text.set(f"Archivo Asoprofarma seleccionado: {os.path.basename(asopro_file)} - Falta Del Sud")
            self.process_button.config(state=tk.DISABLED)
        elif sud_file:
            self.status_text.set(f"Archivo Del Sud seleccionado: {os.path.basename(sud_file)} - Falta Asoprofarma")
            self.process_button.config(state=tk.DISABLED)
        else:
            self.status_text.set("Seleccione archivos para ambas droguerías (TXT o CSV).")
            self.process_button.config(state=tk.DISABLED)
        
        # Deshabilitar botones de exportación hasta que se procesen los archivos
        self.copy_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)

    def compare_drugstore_results(self, asopro_results, sud_results):
        """Compara los resultados de ambas droguerías y devuelve dos filas por producto para poder verificar precios"""
        final_results = []
        
        # Obtener todos los códigos de barras únicos
        all_barcodes = set(asopro_results.keys()) | set(sud_results.keys())
        
        for barcode in all_barcodes:
            asopro_data = asopro_results.get(barcode)
            sud_data = sud_results.get(barcode)
            
            # Determinar descripción (preferir la más completa)
            descripcion = ""
            if asopro_data and sud_data:
                descripcion = asopro_data['descripcion'] if len(asopro_data['descripcion']) > len(sud_data['descripcion']) else sud_data['descripcion']
            elif asopro_data:
                descripcion = asopro_data['descripcion']
            elif sud_data:
                descripcion = sud_data['descripcion']
            
            # Obtener divisor (debe ser el mismo para ambas)
            divisor = 1
            if asopro_data:
                divisor = asopro_data['divisor']
            elif sud_data:
                divisor = sud_data['divisor']
            
            # Determinar cuál precio es más alto para marcar como ganador
            mejor_precio = None
            if asopro_data and sud_data:
                if asopro_data['precio_unitario'] > sud_data['precio_unitario']:
                    mejor_precio = 'asoprofarma'
                    print(f"Comparación {barcode}: ASOPRO ${asopro_data['precio_unitario']:.2f} > DEL SUD ${sud_data['precio_unitario']:.2f} -> ASOPRO gana (precio más alto)", file=sys.stderr)
                elif sud_data['precio_unitario'] > asopro_data['precio_unitario']:
                    mejor_precio = 'delsud'
                    print(f"Comparación {barcode}: DEL SUD ${sud_data['precio_unitario']:.2f} > ASOPRO ${asopro_data['precio_unitario']:.2f} -> DEL SUD gana (precio más alto)", file=sys.stderr)
                else:
                    # Empate, marcar ASOPRO como ganador por defecto
                    mejor_precio = 'asoprofarma'
                    print(f"Comparación {barcode}: ASOPRO ${asopro_data['precio_unitario']:.2f} = DEL SUD ${sud_data['precio_unitario']:.2f} -> Empate, usando ASOPRO", file=sys.stderr)
            elif asopro_data:
                mejor_precio = 'asoprofarma'
                print(f"Comparación {barcode}: Solo ASOPRO ${asopro_data['precio_unitario']:.2f} disponible", file=sys.stderr)
            elif sud_data:
                mejor_precio = 'delsud'
                print(f"Comparación {barcode}: Solo DEL SUD ${sud_data['precio_unitario']:.2f} disponible", file=sys.stderr)
            
            # Crear fila para ASOPROFARMA
            if asopro_data:
                es_precio_alto = (mejor_precio == 'asoprofarma')
                precio_sugerido = round_price_up(asopro_data['precio_unitario']) if es_precio_alto else 0
                
                final_results.append({
                    'barcode': barcode,
                    'descripcion': descripcion,
                    'divisor': divisor,
                    'precio_base': asopro_data['precio_base'],
                    'precio_unitario': asopro_data['precio_unitario'],
                    'precio_sugerido': precio_sugerido,
                    'drugstore': 'ASOPROFARMA',
                    'disponible': True,
                    'es_precio_alto': es_precio_alto
                })
            else:
                # No disponible en ASOPRO
                final_results.append({
                    'barcode': barcode,
                    'descripcion': descripcion,
                    'divisor': divisor,
                    'precio_base': 0,
                    'precio_unitario': 0,
                    'precio_sugerido': 0,
                    'drugstore': 'ASOPROFARMA',
                    'disponible': False,
                    'es_precio_alto': False
                })
            
            # Crear fila para DEL SUD
            if sud_data:
                es_precio_alto = (mejor_precio == 'delsud')
                precio_sugerido = round_price_up(sud_data['precio_unitario']) if es_precio_alto else 0
                
                final_results.append({
                    'barcode': barcode,
                    'descripcion': descripcion,
                    'divisor': divisor,
                    'precio_base': sud_data['precio_base'],
                    'precio_unitario': sud_data['precio_unitario'],
                    'precio_sugerido': precio_sugerido,
                    'drugstore': 'DEL SUD',
                    'disponible': True,
                    'es_precio_alto': es_precio_alto
                })
            else:
                # No disponible en DEL SUD
                final_results.append({
                    'barcode': barcode,
                    'descripcion': descripcion,
                    'divisor': divisor,
                    'precio_base': 0,
                    'precio_unitario': 0,
                    'precio_sugerido': 0,
                    'drugstore': 'DEL SUD',
                    'disponible': False,
                    'es_precio_alto': False
                })
        
        # Ordenar por descripción y luego por droguería (ASOPROFARMA primero)
        final_results.sort(key=lambda x: (x['descripcion'], x['drugstore']))
        return final_results

    def start_processing(self):
        """Inicia el procesamiento de ambos archivos en un hilo separado."""
        asopro_file = self.filepath_asopro.get()
        sud_file = self.filepath_sud.get()
        
        if not asopro_file or not sud_file:
            messagebox.showwarning("Archivos incompletos", "Por favor, seleccione archivos para ambas droguerías.")
            return

        # Deshabilitar botones durante el procesamiento
        self.select_button_asopro.config(state=tk.DISABLED)
        self.select_button_sud.config(state=tk.DISABLED)
        self.process_button.config(state=tk.DISABLED)
        self.copy_button.config(state=tk.DISABLED)
        self.export_button.config(state=tk.DISABLED)
        self.status_text.set("Procesando archivos... por favor espere.")
        self.root.update_idletasks()

        # Limpiar tabla
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Ejecutar procesamiento en hilo separado
        thread = threading.Thread(target=self.run_processing_thread, args=(asopro_file, sud_file), daemon=True)
        thread.start()

    def run_processing_thread(self, asopro_file, sud_file):
        """Función que se ejecuta en el hilo secundario. Procesa ambos archivos."""
        try:
            # Procesar archivos por separado
            asopro_results = process_file(asopro_file)
            sud_results = process_file(sud_file)
            
            # Comparar resultados
            compared_results = self.compare_drugstore_results(asopro_results, sud_results)
            
            # Actualizar GUI
            self.root.after(0, self.update_gui_with_results, compared_results, None)
        except Exception as e:
            self.root.after(0, self.update_gui_with_results, [], e)

    def update_gui_with_results(self, processed_results, error):
        """
        Actualiza la GUI con los resultados o muestra un mensaje de error.
        Esta función SIEMPRE se ejecuta en el hilo principal de Tkinter.
        """
        if error:
            messagebox.showerror("Error durante el procesamiento", f"Ocurrió un error:\n{error}")
            self.status_text.set("Error durante el procesamiento.")
        else:
            if processed_results:
                # Como ahora hay 2 filas por producto, dividir por 2 para contar productos únicos
                productos_procesados = len(processed_results) // 2
                asopro_count = sum(1 for item in processed_results if item['drugstore'] == 'ASOPROFARMA' and item['disponible'])
                sud_count = sum(1 for item in processed_results if item['drugstore'] == 'DEL SUD' and item['disponible'])
                productos_disponibles = asopro_count + sud_count
                
                # Insertar productos en la tabla
                for item in processed_results:
                    # Determinar tag para colorear
                    if not item['disponible']:
                        tag = 'no_disponible'
                    elif item['es_precio_alto']:
                        tag = 'precio_alto'
                    else:
                        tag = 'disponible'
                    
                    # Preparar datos para mostrar
                    if item['disponible']:
                        precio_base_str = f"${item['precio_base']:.2f}"
                        precio_str = f"${item['precio_unitario']:.2f}"
                        precio_sugerido_str = f"${item['precio_sugerido']:.0f}" if item['precio_sugerido'] > 0 else "-"
                        divisor_str = f"/{item['divisor']}"
                    else:
                        precio_base_str = "No disponible"
                        precio_str = "No disponible"
                        precio_sugerido_str = "-"
                        divisor_str = "-"
                    
                    # Insertar fila en la tabla (ahora con 6 columnas incluyendo Precio Base)
                    self.tree.insert('', tk.END, values=(
                        item['descripcion'],
                        divisor_str,
                        precio_base_str,
                        precio_str,
                        item['drugstore'],
                        precio_sugerido_str
                    ), tags=(tag,))
                
                # Actualizar estado con estadísticas
                self.status_text.set(
                    f"Procesados {productos_procesados} productos | "
                    f"Disponibles: {productos_disponibles} | "
                    f"ASOPRO: {asopro_count} | DEL SUD: {sud_count}"
                )
                
                self.copy_button.config(state=tk.NORMAL)
                self.export_button.config(state=tk.NORMAL)
            else:
                self.status_text.set("Proceso completado. No se encontraron productos en la lista de códigos configurados.")
                self.copy_button.config(state=tk.DISABLED)
                self.export_button.config(state=tk.DISABLED)

        # Rehabilitar botones
        self.select_button_asopro.config(state=tk.NORMAL)
        self.select_button_sud.config(state=tk.NORMAL)
        self.process_button.config(state=tk.NORMAL)


    def copy_to_clipboard(self):
        """Copia el contenido de la tabla al portapapeles con formato para Excel."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("Nada que copiar", "La tabla de resultados está vacía.")
            return

        # Agregar encabezados
        headers = ["Descripción", "Divisor", "Precio Base", "Precio Unitario", "Droguería", "Precio Sugerido"]
        output_lines = ["\t".join(headers)]
        
        # Agregar datos
        for item_id in items:
            values = self.tree.item(item_id, 'values')
            if len(values) == 6:
                row_string = "\t".join(str(v) for v in values)
                output_lines.append(row_string)

        output_string = "\n".join(output_lines)

        try:
            pyperclip.copy(output_string)
            messagebox.showinfo("Copiado", "¡Tabla copiada al portapapeles!\nPuede pegarla en Excel (Ctrl+V).")
            self.status_text.set("Resultados copiados al portapapeles.")
        except Exception as e:
            messagebox.showerror("Error al copiar", f"No se pudo copiar al portapapeles:\n{e}")
            self.status_text.set("Error al copiar al portapapeles.")
    
    def export_to_csv(self):
        """Exporta los resultados a un archivo CSV."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("Nada que exportar", "La tabla de resultados está vacía.")
            return
        
        filename = filedialog.asksaveasfilename(
            title="Guardar resultados como CSV",
            defaultextension=".csv",
            filetypes=(("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*"))
        )
        
        if filename:
            try:
                with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                    writer = csv.writer(csvfile)
                    # Escribir encabezados
                    writer.writerow(["Descripción", "Divisor", "Precio Base", "Precio Unitario", "Droguería", "Precio Sugerido"])
                    
                    # Escribir datos
                    for item_id in items:
                        values = self.tree.item(item_id, 'values')
                        if len(values) == 6:
                            writer.writerow(values)
                
                messagebox.showinfo("Exportación exitosa", f"Resultados exportados a:\n{filename}")
                self.status_text.set(f"Resultados exportados a {os.path.basename(filename)}")
            except Exception as e:
                messagebox.showerror("Error al exportar", f"No se pudo exportar el archivo:\n{e}")
    
    def open_config_window(self):
        """Abre la ventana de configuración de códigos de barras."""
        config_window = tk.Toplevel(self.root)
        config_window.title("Configuración de Códigos de Barras")
        config_window.geometry("800x600")
        
        # Frame para la lista de códigos
        list_frame = ttk.Frame(config_window, padding="10")
        list_frame.pack(expand=True, fill=tk.BOTH)
        
        # Crear Treeview para mostrar códigos
        columns = ("Código", "Divisor", "Descripción")
        config_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=15)
        
        config_tree.heading("Código", text="Código de Barras")
        config_tree.heading("Divisor", text="Divisor")
        config_tree.heading("Descripción", text="Descripción")
        
        config_tree.column("Código", width=150)
        config_tree.column("Divisor", width=100, anchor=tk.CENTER)
        config_tree.column("Descripción", width=400)
        
        # Cargar códigos actuales
        for barcode, info in TARGET_DIVISORS.items():
            config_tree.insert('', tk.END, values=(
                barcode,
                info.get('divisor', 1),
                info.get('descripcion', 'Sin descripción')
            ))
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=config_tree.yview)
        config_tree.configure(yscrollcommand=scrollbar.set)
        
        config_tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Frame para agregar nuevo código
        add_frame = ttk.LabelFrame(config_window, text="Agregar Nuevo Código", padding="10")
        add_frame.pack(fill=tk.X, padx=10, pady=5)
        
        # Campos de entrada
        ttk.Label(add_frame, text="Código de Barras:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        barcode_entry = ttk.Entry(add_frame, width=20)
        barcode_entry.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(add_frame, text="Divisor:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        divisor_entry = ttk.Entry(add_frame, width=10)
        divisor_entry.grid(row=0, column=3, padx=5, pady=5)
        
        ttk.Label(add_frame, text="Descripción:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        desc_entry = ttk.Entry(add_frame, width=40)
        desc_entry.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky=tk.W+tk.E)
        
        def add_barcode():
            barcode = barcode_entry.get().strip()
            try:
                divisor = float(divisor_entry.get())
            except ValueError:
                messagebox.showerror("Error", "El divisor debe ser un número válido.")
                return
            
            if not barcode or len(barcode) != 13:
                messagebox.showerror("Error", "El código de barras debe tener 13 dígitos.")
                return
            
            if divisor <= 0:
                messagebox.showerror("Error", "El divisor debe ser mayor que cero.")
                return
            
            # Agregar al diccionario
            TARGET_DIVISORS[barcode] = {
                'divisor': divisor,
                'descripcion': desc_entry.get() or 'Sin descripción'
            }
            
            # Actualizar configuración global
            CONFIG['divisores'] = TARGET_DIVISORS
            
            # Guardar configuración
            if save_config(CONFIG):
                # Actualizar árbol
                config_tree.insert('', tk.END, values=(
                    barcode, divisor, desc_entry.get() or 'Sin descripción'
                ))
                
                # Limpiar campos
                barcode_entry.delete(0, tk.END)
                divisor_entry.delete(0, tk.END)
                desc_entry.delete(0, tk.END)
                
                messagebox.showinfo("Éxito", "Código agregado correctamente.")
        
        def delete_barcode():
            selected = config_tree.selection()
            if not selected:
                messagebox.showwarning("Selección", "Por favor seleccione un código para eliminar.")
                return
            
            item = config_tree.item(selected[0])
            barcode = item['values'][0]
            
            if messagebox.askyesno("Confirmar", f"¿Está seguro de eliminar el código {barcode}?"):
                # Eliminar del diccionario
                if barcode in TARGET_DIVISORS:
                    del TARGET_DIVISORS[barcode]
                    CONFIG['divisores'] = TARGET_DIVISORS
                    
                    if save_config(CONFIG):
                        config_tree.delete(selected[0])
                        messagebox.showinfo("Éxito", "Código eliminado correctamente.")
        
        # Botones
        button_frame = ttk.Frame(add_frame)
        button_frame.grid(row=2, column=0, columnspan=4, pady=10)
        
        ttk.Button(button_frame, text="Agregar Código", command=add_barcode).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Eliminar Seleccionado", command=delete_barcode).pack(side=tk.LEFT, padx=5)
        
        # Botón cerrar
        ttk.Button(config_window, text="Cerrar", command=config_window.destroy).pack(pady=10)


# --- Ejecución Principal ---
if __name__ == "__main__":
    try:
        # Intenta importar pyperclip al inicio para fallar rápido si no está instalado
        import pyperclip
    except ImportError:
        # Muestra error en consola Y en una ventana emergente si Tkinter puede iniciar
        error_msg = "Error: La librería 'pyperclip' no está instalada.\nPor favor, instálala ejecutando:\n\npip install pyperclip"
        print(error_msg, file=sys.stderr)
        try:
            # Intenta mostrar un messagebox de error (puede fallar si Tkinter no está bien)
            root_check = tk.Tk()
            root_check.withdraw() # Oculta la ventana principal temporal
            messagebox.showerror("Librería Faltante", error_msg)
            root_check.destroy()
        except tk.TclError:
            pass # No se pudo mostrar messagebox, el error de consola es suficiente
        sys.exit(1) # Termina la ejecución del script

    # Si pyperclip está disponible, crea la ventana principal y la aplicación
    root = tk.Tk()
    app = App(root)
    # Inicia el bucle de eventos de la GUI (mantiene la ventana abierta y reactiva)
    root.mainloop()
