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
        
        self.export_button = ttk.Button(bottom_frame, text="Exportar a CSV", command=self.open_price_selection_window, state=tk.DISABLED)
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

    def open_price_selection_window(self):
        """Abre la ventana compacta de selección de precios para exportar CSV."""
        items = self.tree.get_children()
        if not items:
            messagebox.showinfo("Nada que exportar", "La tabla de resultados está vacía.")
            return

        # Variables para almacenar las selecciones
        self.price_selections = {}
        self.custom_prices = {}
        self.price_vars = {}  # Para radio buttons
        
        # Procesar datos de la tabla actual para obtener información completa
        self.products_data = self.prepare_products_for_selection()
        
        # Crear ventana modal compacta con tamaño auto-ajustable
        self.price_window = tk.Toplevel(self.root)
        self.price_window.title("🎯 Selección de Precios para Exportar")
        self.price_window.transient(self.root)
        self.price_window.grab_set()
        self.price_window.configure(bg='#f8f9fa')
        
        # --- Header compacto ---
        header_frame = tk.Frame(self.price_window, bg='#2c3e50', height=40)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)
        
        title_label = tk.Label(header_frame, text="Configuración de Exportación de Precios", 
                              font=('Arial', 12, 'bold'), fg='white', bg='#2c3e50')
        title_label.pack(pady=8)
        
        # --- Frame principal ---
        main_container = tk.Frame(self.price_window, bg='#f8f9fa')
        main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Configuración del archivo compacta ---
        config_frame = tk.LabelFrame(main_container, text="⚙️ Configuración", 
                                    font=('Arial', 9, 'bold'), bg='#f8f9fa', fg='#2c3e50')
        config_frame.pack(fill=tk.X, pady=(0, 5))
        
        config_inner = tk.Frame(config_frame, bg='#f8f9fa')
        config_inner.pack(fill=tk.X, padx=5, pady=5)
        
        # Campos de configuración horizontales
        tk.Label(config_inner, text="📅 Fecha:", font=('Arial', 9), bg='#f8f9fa').grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.export_date = tk.StringVar(value="20-feb")
        date_entry = tk.Entry(config_inner, textvariable=self.export_date, width=12, font=('Arial', 9))
        date_entry.grid(row=0, column=1, padx=(0, 15), sticky=tk.W)
        
        tk.Label(config_inner, text="📍 Ubicación:", font=('Arial', 9), bg='#f8f9fa').grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.export_location = tk.StringVar(value="San Luis")
        location_entry = tk.Entry(config_inner, textvariable=self.export_location, width=12, font=('Arial', 9))
        location_entry.grid(row=0, column=3, sticky=tk.W)
        
        # --- Botones de selección masiva compactos ---
        bulk_frame = tk.Frame(main_container, bg='#f8f9fa')
        bulk_frame.pack(fill=tk.X, pady=(0, 5))
        
        tk.Label(bulk_frame, text="🚀 Selección Rápida:", font=('Arial', 9, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(side=tk.LEFT, padx=(0, 10))
        
        # Botones más compactos
        asopro_btn = tk.Button(bulk_frame, text="✓ ASOPRO", font=('Arial', 8, 'bold'),
                              bg='#27ae60', fg='white', relief=tk.FLAT, padx=12, pady=4,
                              command=lambda: self.bulk_select_modern('ASOPROFARMA'))
        asopro_btn.pack(side=tk.LEFT, padx=2)
        
        sud_btn = tk.Button(bulk_frame, text="✓ DEL SUD", font=('Arial', 8, 'bold'),
                           bg='#3498db', fg='white', relief=tk.FLAT, padx=12, pady=4,
                           command=lambda: self.bulk_select_modern('DEL SUD'))
        sud_btn.pack(side=tk.LEFT, padx=2)
        
        sugerido_btn = tk.Button(bulk_frame, text="✓ Sugerido", font=('Arial', 8, 'bold'),
                                bg='#f39c12', fg='white', relief=tk.FLAT, padx=12, pady=4,
                                command=lambda: self.bulk_select_modern('SUGERIDO'))
        sugerido_btn.pack(side=tk.LEFT, padx=2)
        
        # --- Área de productos con tabla alineada ---
        products_container = tk.Frame(main_container, bg='#f8f9fa')
        products_container.pack(fill=tk.BOTH, expand=True)
        
        # Canvas para scroll
        canvas = tk.Canvas(products_container, bg='#f8f9fa', highlightthickness=0)
        scrollbar = ttk.Scrollbar(products_container, orient="vertical", command=canvas.yview)
        self.scrollable_frame = tk.Frame(canvas, bg='#f8f9fa')
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Crear tabla con alineación perfecta
        self.create_aligned_product_table()
        
        # --- Botones de acción compactos ---
        action_frame = tk.Frame(self.price_window, bg='#ecf0f1', height=50)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)
        action_frame.pack_propagate(False)
        
        button_container = tk.Frame(action_frame, bg='#ecf0f1')
        button_container.pack(expand=True, fill=tk.Y)
        
        export_btn = tk.Button(button_container, text="💾 Exportar CSV", font=('Arial', 10, 'bold'),
                              bg='#e74c3c', fg='white', relief=tk.FLAT, padx=20, pady=6,
                              command=self.export_custom_csv_modern)
        export_btn.pack(side=tk.RIGHT, padx=8, pady=12)
        
        cancel_btn = tk.Button(button_container, text="✕ Cancelar", font=('Arial', 10),
                              bg='#95a5a6', fg='white', relief=tk.FLAT, padx=20, pady=6,
                              command=self.price_window.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=3, pady=12)
        
        # Auto-ajustar tamaño de la ventana
        self.price_window.update_idletasks()
        self.auto_resize_window()

    def prepare_products_for_selection(self):
        """Prepara los datos de productos para la ventana de selección de precios."""
        products_data = {}
        items = self.tree.get_children()
        
        for item_id in items:
            values = self.tree.item(item_id, 'values')
            if len(values) == 6:
                descripcion, divisor_str, precio_base_str, precio_unitario_str, drugstore, precio_sugerido_str = values
                
                # Limpiar datos
                barcode = descripcion  # Usaremos descripción como clave única por ahora
                divisor = divisor_str.replace('/', '') if divisor_str != '-' else '1'
                
                # Extraer precios numéricos
                precio_base = 0
                precio_unitario = 0
                precio_sugerido = 0
                
                if precio_base_str != "No disponible":
                    precio_base = float(precio_base_str.replace('$', '').replace(',', ''))
                if precio_unitario_str != "No disponible":
                    precio_unitario = float(precio_unitario_str.replace('$', '').replace(',', ''))
                if precio_sugerido_str != "-" and precio_sugerido_str != "":
                    precio_sugerido = float(precio_sugerido_str.replace('$', '').replace(',', ''))
                
                # Crear o actualizar registro del producto
                if descripcion not in products_data:
                    products_data[descripcion] = {
                        'descripcion': descripcion,
                        'divisor': divisor,
                        'asopro_precio': 0,
                        'delsud_precio': 0,
                        'precio_sugerido': 0,
                        'available_sources': []
                    }
                
                # Agregar datos según la droguería
                if drugstore == 'ASOPROFARMA':
                    products_data[descripcion]['asopro_precio'] = precio_unitario
                    products_data[descripcion]['available_sources'].append('ASOPROFARMA')
                    if precio_sugerido > 0:
                        products_data[descripcion]['precio_sugerido'] = precio_sugerido
                elif drugstore == 'DEL SUD':
                    products_data[descripcion]['delsud_precio'] = precio_unitario
                    products_data[descripcion]['available_sources'].append('DEL SUD')
                    if precio_sugerido > 0:
                        products_data[descripcion]['precio_sugerido'] = precio_sugerido
        
        return products_data

    def create_aligned_product_table(self):
        """Crea una tabla perfectamente alineada con encabezados y datos."""
        # Definir anchos fijos para cada columna (en píxeles)
        self.column_widths = {
            'producto': 320,
            'divisor': 50,
            'asopro': 80,
            'delsud': 80,
            'sugerido': 80,
            'final': 90,
            'edit': 50
        }
        
        # Configurar el grid principal del scrollable_frame
        self.scrollable_frame.grid_columnconfigure(0, weight=0, minsize=self.column_widths['producto'])
        self.scrollable_frame.grid_columnconfigure(1, weight=0, minsize=self.column_widths['divisor'])
        self.scrollable_frame.grid_columnconfigure(2, weight=0, minsize=self.column_widths['asopro'])
        self.scrollable_frame.grid_columnconfigure(3, weight=0, minsize=self.column_widths['delsud'])
        self.scrollable_frame.grid_columnconfigure(4, weight=0, minsize=self.column_widths['sugerido'])
        self.scrollable_frame.grid_columnconfigure(5, weight=0, minsize=self.column_widths['final'])
        self.scrollable_frame.grid_columnconfigure(6, weight=0, minsize=self.column_widths['edit'])
        
        # Crear encabezado de tabla con alineación perfecta
        self.create_table_header()
        
        # Crear filas de productos con alineación perfecta
        self.create_table_rows()
    
    def create_table_header(self):
        """Crea el encabezado de tabla con alineación perfecta."""
        header_row = 0
        
        # Producto
        tk.Label(self.scrollable_frame, text="Producto", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['producto']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=0, sticky=tk.EW, padx=1, pady=1)
        
        # Divisor
        tk.Label(self.scrollable_frame, text="Div", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['divisor']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=1, sticky=tk.EW, padx=1, pady=1)
        
        # ASOPROFARMA
        tk.Label(self.scrollable_frame, text="ASOPROFARMA", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['asopro']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=2, sticky=tk.EW, padx=1, pady=1)
        
        # DEL SUD
        tk.Label(self.scrollable_frame, text="DEL SUD", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['delsud']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=3, sticky=tk.EW, padx=1, pady=1)
        
        # SUGERIDO
        tk.Label(self.scrollable_frame, text="SUGERIDO", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['sugerido']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=4, sticky=tk.EW, padx=1, pady=1)
        
        # Precio Final
        tk.Label(self.scrollable_frame, text="Precio Final", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['final']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=5, sticky=tk.EW, padx=1, pady=1)
        
        # Editar
        tk.Label(self.scrollable_frame, text="Edit", font=('Arial', 9, 'bold'),
                bg='#34495e', fg='white', width=int(self.column_widths['edit']/8),
                anchor=tk.CENTER, relief=tk.FLAT).grid(
                row=header_row, column=6, sticky=tk.EW, padx=1, pady=1)
    
    def create_table_rows(self):
        """Crea las filas de productos con alineación perfecta."""
        # Ordenar productos alfabéticamente
        sorted_products = sorted(self.products_data.items(), key=lambda x: x[0])
        
        for i, (descripcion, data) in enumerate(sorted_products):
            row_num = i + 1  # +1 porque row 0 es el header
            
            # Color de fondo alternado
            bg_color = '#ffffff' if i % 2 == 0 else '#f8f9fa'
            
            # Variable para radio buttons de este producto
            price_var = tk.StringVar()
            self.price_vars[descripcion] = price_var
            
            # Determinar selección inicial
            initial_selection = "SUGERIDO"
            if data['precio_sugerido'] > 0:
                initial_selection = "SUGERIDO"
            elif data['asopro_precio'] >= data['delsud_precio']:
                initial_selection = "ASOPROFARMA"
            else:
                initial_selection = "DEL SUD"
            
            price_var.set(initial_selection)
            self.price_selections[descripcion] = initial_selection
            
            # Columna 0: Nombre del producto
            product_name = descripcion[:40] + "..." if len(descripcion) > 40 else descripcion
            product_label = tk.Label(self.scrollable_frame, text=product_name, 
                                   font=('Arial', 9), bg=bg_color, fg='#2c3e50',
                                   anchor=tk.W, width=int(self.column_widths['producto']/8))
            product_label.grid(row=row_num, column=0, sticky=tk.EW, padx=1, pady=1)
            
            # Columna 1: Divisor
            divisor_label = tk.Label(self.scrollable_frame, text=f"/{data['divisor']}", 
                                   font=('Arial', 8), bg=bg_color, fg='#7f8c8d',
                                   anchor=tk.CENTER, width=int(self.column_widths['divisor']/8))
            divisor_label.grid(row=row_num, column=1, sticky=tk.EW, padx=1, pady=1)
            
            # Columna 2: ASOPROFARMA (Radio + Precio)
            asopro_frame = tk.Frame(self.scrollable_frame, bg='#e8f5e9', relief=tk.FLAT)
            asopro_frame.grid(row=row_num, column=2, sticky=tk.EW, padx=1, pady=1)
            
            asopro_radio = tk.Radiobutton(asopro_frame, text="", 
                                         variable=price_var, value="ASOPROFARMA",
                                         bg='#e8f5e9', fg='#27ae60', selectcolor='#27ae60',
                                         command=lambda d=descripcion: self.update_selected_price_table(d))
            asopro_radio.pack(side=tk.LEFT, padx=2)
            
            asopro_price = f"${data['asopro_precio']:.0f}" if data['asopro_precio'] > 0 else "N/A"
            tk.Label(asopro_frame, text=asopro_price, font=('Arial', 8, 'bold'),
                    bg='#e8f5e9', fg='#27ae60', anchor=tk.E).pack(side=tk.RIGHT, padx=2)
            
            # Columna 3: DEL SUD (Radio + Precio)
            sud_frame = tk.Frame(self.scrollable_frame, bg='#ebf3fd', relief=tk.FLAT)
            sud_frame.grid(row=row_num, column=3, sticky=tk.EW, padx=1, pady=1)
            
            sud_radio = tk.Radiobutton(sud_frame, text="", 
                                      variable=price_var, value="DEL SUD",
                                      bg='#ebf3fd', fg='#3498db', selectcolor='#3498db',
                                      command=lambda d=descripcion: self.update_selected_price_table(d))
            sud_radio.pack(side=tk.LEFT, padx=2)
            
            sud_price = f"${data['delsud_precio']:.0f}" if data['delsud_precio'] > 0 else "N/A"
            tk.Label(sud_frame, text=sud_price, font=('Arial', 8, 'bold'),
                    bg='#ebf3fd', fg='#3498db', anchor=tk.E).pack(side=tk.RIGHT, padx=2)
            
            # Columna 4: SUGERIDO (Radio + Precio)
            sugerido_frame = tk.Frame(self.scrollable_frame, bg='#fef9e7', relief=tk.FLAT)
            sugerido_frame.grid(row=row_num, column=4, sticky=tk.EW, padx=1, pady=1)
            
            sugerido_radio = tk.Radiobutton(sugerido_frame, text="", 
                                           variable=price_var, value="SUGERIDO",
                                           bg='#fef9e7', fg='#f39c12', selectcolor='#f39c12',
                                           command=lambda d=descripcion: self.update_selected_price_table(d))
            sugerido_radio.pack(side=tk.LEFT, padx=2)
            
            sugerido_price = f"${data['precio_sugerido']:.0f}" if data['precio_sugerido'] > 0 else "N/A"
            tk.Label(sugerido_frame, text=sugerido_price, font=('Arial', 8, 'bold'),
                    bg='#fef9e7', fg='#f39c12', anchor=tk.E).pack(side=tk.RIGHT, padx=2)
            
            # Columna 5: Precio Final
            final_price_text = self.get_selected_price_for_display(descripcion, data, initial_selection)
            final_price = tk.Label(self.scrollable_frame, text=final_price_text, 
                                  font=('Arial', 9, 'bold'), bg=bg_color, fg='#e74c3c',
                                  anchor=tk.E, width=int(self.column_widths['final']/8))
            final_price.grid(row=row_num, column=5, sticky=tk.EW, padx=1, pady=1)
            
            # Guardar referencia para actualizar después
            setattr(final_price, 'descripcion', descripcion)
            setattr(final_price, 'row_num', row_num)
            
            # Columna 6: Botón Editar (con nuevo icono)
            edit_btn = tk.Button(self.scrollable_frame, text="🖊️", font=('Arial', 12),
                                bg='#3498db', fg='white', relief=tk.FLAT, width=4,
                                command=lambda d=descripcion, l=final_price: self.edit_custom_price_table(d, l))
            edit_btn.grid(row=row_num, column=6, sticky=tk.EW, padx=1, pady=1)

    def update_selected_price_table(self, descripcion):
        """Actualiza el precio final cuando se cambia la selección en la tabla."""
        selection = self.price_vars[descripcion].get()
        self.price_selections[descripcion] = selection
        
        # Buscar el label correspondiente y actualizar el precio final
        for child in self.scrollable_frame.winfo_children():
            if hasattr(child, 'descripcion') and child.descripcion == descripcion:
                data = self.products_data[descripcion]
                final_price_text = self.get_selected_price_for_display(descripcion, data, selection)
                child.config(text=final_price_text)
                break
    
    def update_selected_price_compact(self, descripcion):
        """Actualiza el precio final cuando se cambia la selección en layout compacto."""
        selection = self.price_vars[descripcion].get()
        self.price_selections[descripcion] = selection
        
        # Buscar el row correspondiente y actualizar el precio final
        for child in self.scrollable_frame.winfo_children():
            if hasattr(child, 'descripcion') and child.descripcion == descripcion:
                data = self.products_data[descripcion]
                final_price_text = self.get_selected_price_for_display(descripcion, data, selection)
                child.final_price_label.config(text=final_price_text)
                break
    
    def update_selected_price(self, descripcion):
        """Actualiza el precio final cuando se cambia la selección."""
        selection = self.price_vars[descripcion].get()
        self.price_selections[descripcion] = selection
        
        # Buscar el card correspondiente y actualizar el precio final
        for child in self.scrollable_frame.winfo_children():
            if hasattr(child, 'descripcion') and child.descripcion == descripcion:
                data = self.products_data[descripcion]
                final_price_text = self.get_selected_price_for_display(descripcion, data, selection)
                child.final_price_label.config(text=final_price_text)
                break

    def get_selected_price_for_display(self, descripcion, data, selection):
        """Obtiene el precio seleccionado formateado para mostrar."""
        # Si hay precio personalizado, usarlo
        if descripcion in self.custom_prices and self.custom_prices[descripcion] > 0:
            return f"${self.custom_prices[descripcion]:.0f} (Personalizado)"
        
        # Usar selección actual
        if selection == "ASOPROFARMA" and data['asopro_precio'] > 0:
            return f"${data['asopro_precio']:.0f}"
        elif selection == "DEL SUD" and data['delsud_precio'] > 0:
            return f"${data['delsud_precio']:.0f}"
        elif selection == "SUGERIDO" and data['precio_sugerido'] > 0:
            return f"${data['precio_sugerido']:.0f}"
        
        return "No disponible"

    def edit_custom_price_compact(self, descripcion, row_frame):
        """Abre ventana compacta para editar precio personalizado."""
        # Ventana de edición compacta
        edit_window = tk.Toplevel(self.price_window)
        edit_window.title("✏️ Editar Precio")
        edit_window.geometry("350x200")
        edit_window.transient(self.price_window)
        edit_window.grab_set()
        edit_window.configure(bg='#f8f9fa')
        
        # Header compacto
        header = tk.Frame(edit_window, bg='#3498db', height=35)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="Editar Precio", font=('Arial', 11, 'bold'),
                fg='white', bg='#3498db').pack(pady=8)
        
        # Contenido compacto
        content = tk.Frame(edit_window, bg='#f8f9fa')
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        tk.Label(content, text=f"Producto:", font=('Arial', 9, 'bold'),
                bg='#f8f9fa').pack(anchor=tk.W)
        tk.Label(content, text=descripcion[:40] + ("..." if len(descripcion) > 40 else ""),
                font=('Arial', 9), bg='#f8f9fa', fg='#7f8c8d').pack(anchor=tk.W, pady=(0, 10))
        
        tk.Label(content, text="Nuevo Precio:", font=('Arial', 10, 'bold'),
                bg='#f8f9fa').pack(anchor=tk.W)
        
        # Campo de entrada compacto
        price_frame = tk.Frame(content, bg='#f8f9fa')
        price_frame.pack(fill=tk.X, pady=(5, 15))
        
        current_price = self.custom_prices.get(descripcion, 0)
        if current_price == 0:
            # Usar precio actual seleccionado
            data = self.products_data[descripcion]
            selection = self.price_selections.get(descripcion, 'SUGERIDO')
            if selection == "ASOPROFARMA":
                current_price = data['asopro_precio']
            elif selection == "DEL SUD":
                current_price = data['delsud_precio']
            else:
                current_price = data['precio_sugerido']
        
        price_var = tk.StringVar(value=f"{current_price:.0f}")
        price_entry = tk.Entry(price_frame, textvariable=price_var, width=15,
                              font=('Arial', 12), relief=tk.FLAT, bd=2, justify=tk.CENTER)
        price_entry.pack()
        price_entry.select_range(0, tk.END)
        price_entry.focus()
        
        # Botones compactos
        button_frame = tk.Frame(content, bg='#f8f9fa')
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        def save_custom_price():
            try:
                new_price = float(price_var.get())
                self.custom_prices[descripcion] = new_price
                self.price_selections[descripcion] = "PERSONALIZADO"
                
                # Actualizar display
                final_price_text = f"${new_price:.0f} (Personalizado)"
                row_frame.final_price_label.config(text=final_price_text)
                
                edit_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Por favor ingrese un precio válido.")
        
        save_btn = tk.Button(button_frame, text="💾 Guardar", font=('Arial', 9, 'bold'),
                            bg='#27ae60', fg='white', relief=tk.FLAT, padx=15, pady=5,
                            command=save_custom_price)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="✕ Cancelar", font=('Arial', 9),
                              bg='#95a5a6', fg='white', relief=tk.FLAT, padx=15, pady=5,
                              command=edit_window.destroy)
        cancel_btn.pack(side=tk.RIGHT)
    
    def edit_custom_price(self, descripcion, card):
        """Abre ventana para editar precio personalizado."""
        # Ventana de edición moderna
        edit_window = tk.Toplevel(self.price_window)
        edit_window.title("✏️ Editar Precio Personalizado")
        edit_window.geometry("400x250")
        edit_window.transient(self.price_window)
        edit_window.grab_set()
        edit_window.configure(bg='#f0f0f0')
        
        # Header
        header = tk.Frame(edit_window, bg='#3498db', height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="Editar Precio", font=('Arial', 14, 'bold'),
                fg='white', bg='#3498db').pack(pady=12)
        
        # Contenido
        content = tk.Frame(edit_window, bg='#f0f0f0')
        content.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        tk.Label(content, text=f"Producto:", font=('Arial', 10, 'bold'),
                bg='#f0f0f0').pack(anchor=tk.W)
        tk.Label(content, text=descripcion[:50] + ("..." if len(descripcion) > 50 else ""),
                font=('Arial', 10), bg='#f0f0f0', fg='#7f8c8d').pack(anchor=tk.W, pady=(0, 15))
        
        tk.Label(content, text="Nuevo Precio:", font=('Arial', 12, 'bold'),
                bg='#f0f0f0').pack(anchor=tk.W)
        
        # Campo de entrada con estilo
        price_frame = tk.Frame(content, bg='#f0f0f0')
        price_frame.pack(fill=tk.X, pady=(5, 20))
        
        current_price = self.custom_prices.get(descripcion, 0)
        if current_price == 0:
            # Usar precio actual seleccionado
            data = self.products_data[descripcion]
            selection = self.price_selections.get(descripcion, 'SUGERIDO')
            if selection == "ASOPROFARMA":
                current_price = data['asopro_precio']
            elif selection == "DEL SUD":
                current_price = data['delsud_precio']
            else:
                current_price = data['precio_sugerido']
        
        price_var = tk.StringVar(value=f"{current_price:.0f}")
        price_entry = tk.Entry(price_frame, textvariable=price_var, width=20,
                              font=('Arial', 14), relief=tk.FLAT, bd=2, justify=tk.CENTER)
        price_entry.pack()
        price_entry.select_range(0, tk.END)
        price_entry.focus()
        
        # Botones
        button_frame = tk.Frame(content, bg='#f0f0f0')
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        def save_custom_price():
            try:
                new_price = float(price_var.get())
                self.custom_prices[descripcion] = new_price
                self.price_selections[descripcion] = "PERSONALIZADO"
                
                # Actualizar display
                final_price_text = f"${new_price:.0f} (Personalizado)"
                card.final_price_label.config(text=final_price_text)
                
                edit_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Por favor ingrese un precio válido.")
        
        save_btn = tk.Button(button_frame, text="💾 Guardar", font=('Arial', 11, 'bold'),
                            bg='#27ae60', fg='white', relief=tk.FLAT, padx=20, pady=8,
                            command=save_custom_price)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="✕ Cancelar", font=('Arial', 11),
                              bg='#95a5a6', fg='white', relief=tk.FLAT, padx=20, pady=8,
                              command=edit_window.destroy)
        cancel_btn.pack(side=tk.RIGHT)

    def edit_custom_price_table(self, descripcion, price_label):
        """Abre ventana compacta para editar precio personalizado en la tabla."""
        # Ventana de edición compacta
        edit_window = tk.Toplevel(self.price_window)
        edit_window.title("🖊️ Editar Precio")
        edit_window.geometry("350x200")
        edit_window.transient(self.price_window)
        edit_window.grab_set()
        edit_window.configure(bg='#f8f9fa')
        
        # Header compacto
        header = tk.Frame(edit_window, bg='#3498db', height=35)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        
        tk.Label(header, text="Editar Precio", font=('Arial', 11, 'bold'),
                fg='white', bg='#3498db').pack(pady=8)
        
        # Contenido compacto
        content = tk.Frame(edit_window, bg='#f8f9fa')
        content.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        tk.Label(content, text=f"Producto:", font=('Arial', 9, 'bold'),
                bg='#f8f9fa').pack(anchor=tk.W)
        tk.Label(content, text=descripcion[:40] + ("..." if len(descripcion) > 40 else ""),
                font=('Arial', 9), bg='#f8f9fa', fg='#7f8c8d').pack(anchor=tk.W, pady=(0, 10))
        
        tk.Label(content, text="Nuevo Precio:", font=('Arial', 10, 'bold'),
                bg='#f8f9fa').pack(anchor=tk.W)
        
        # Campo de entrada compacto
        price_frame = tk.Frame(content, bg='#f8f9fa')
        price_frame.pack(fill=tk.X, pady=(5, 15))
        
        current_price = self.custom_prices.get(descripcion, 0)
        if current_price == 0:
            # Usar precio actual seleccionado
            data = self.products_data[descripcion]
            selection = self.price_selections.get(descripcion, 'SUGERIDO')
            if selection == "ASOPROFARMA":
                current_price = data['asopro_precio']
            elif selection == "DEL SUD":
                current_price = data['delsud_precio']
            else:
                current_price = data['precio_sugerido']
        
        price_var = tk.StringVar(value=f"{current_price:.0f}")
        price_entry = tk.Entry(price_frame, textvariable=price_var, width=15,
                              font=('Arial', 12), relief=tk.FLAT, bd=2, justify=tk.CENTER)
        price_entry.pack()
        price_entry.select_range(0, tk.END)
        price_entry.focus()
        
        # Botones compactos
        button_frame = tk.Frame(content, bg='#f8f9fa')
        button_frame.pack(fill=tk.X, pady=(5, 0))
        
        def save_custom_price():
            try:
                new_price = float(price_var.get())
                self.custom_prices[descripcion] = new_price
                self.price_selections[descripcion] = "PERSONALIZADO"
                
                # Actualizar display
                final_price_text = f"${new_price:.0f} (Personalizado)"
                price_label.config(text=final_price_text)
                
                edit_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Por favor ingrese un precio válido.")
        
        save_btn = tk.Button(button_frame, text="💾 Guardar", font=('Arial', 9, 'bold'),
                            bg='#27ae60', fg='white', relief=tk.FLAT, padx=15, pady=5,
                            command=save_custom_price)
        save_btn.pack(side=tk.RIGHT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="✕ Cancelar", font=('Arial', 9),
                              bg='#95a5a6', fg='white', relief=tk.FLAT, padx=15, pady=5,
                              command=edit_window.destroy)
        cancel_btn.pack(side=tk.RIGHT)

    def bulk_select_modern(self, selection_type):
        """Selección masiva para la interfaz moderna y compacta."""
        for descripcion in self.price_vars:
            self.price_vars[descripcion].set(selection_type)
            self.price_selections[descripcion] = selection_type
            self.update_selected_price_table(descripcion)
    
    def auto_resize_window(self):
        """Auto-ajusta el tamaño de la ventana basado en el contenido de la tabla."""
        # Calcular dimensiones basadas en el contenido
        num_products = len(self.products_data)
        
        # Anchura calculada a partir de las columnas
        total_column_width = sum(self.column_widths.values())
        base_width = total_column_width + 50  # Espacio adicional para scrollbar y márgenes
        
        # Altura base + altura por producto
        base_height = 120  # Header + config + botones (más compacto)
        product_height = 25   # Altura por producto en tabla
        max_visible_products = 22  # Máximo de productos visibles sin scroll
        
        # Calcular altura total
        if num_products <= max_visible_products:
            total_height = base_height + (num_products * product_height) + 80
        else:
            total_height = base_height + (max_visible_products * product_height) + 80
        
        # Límites de tamaño optimizados para la tabla
        min_width = total_column_width + 30
        max_width = min(total_column_width + 100, 1100)
        min_height, max_height = 350, 750
        
        # Aplicar límites
        final_width = max(min_width, min(base_width, max_width))
        final_height = max(min_height, min(total_height, max_height))
        
        # Centrar la ventana
        screen_width = self.price_window.winfo_screenwidth()
        screen_height = self.price_window.winfo_screenheight()
        x = (screen_width - final_width) // 2
        y = (screen_height - final_height) // 2
        
        # Aplicar geometría
        self.price_window.geometry(f"{final_width}x{final_height}+{x}+{y}")
        
        # Configurar tamaño mínimo y máximo
        self.price_window.minsize(min_width, min_height)
        self.price_window.maxsize(max_width, max_height)

    def export_custom_csv_modern(self):
        """Exporta CSV con la interfaz moderna."""
        # Solicitar nombre de archivo
        filename = filedialog.asksaveasfilename(
            title="💾 Guardar CSV de precios",
            defaultextension=".csv",
            filetypes=(("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*"))
        )
        
        if not filename:
            return
        
        try:
            # Recopilar datos finales
            export_data = []
            
            for descripcion, data in self.products_data.items():
                selection = self.price_selections.get(descripcion, 'SUGERIDO')
                
                # Determinar precio final
                final_price = 0
                if descripcion in self.custom_prices and self.custom_prices[descripcion] > 0:
                    final_price = self.custom_prices[descripcion]
                elif selection == "ASOPROFARMA" and data['asopro_precio'] > 0:
                    final_price = data['asopro_precio']
                elif selection == "DEL SUD" and data['delsud_precio'] > 0:
                    final_price = data['delsud_precio']
                elif selection == "SUGERIDO" and data['precio_sugerido'] > 0:
                    final_price = data['precio_sugerido']
                
                if final_price > 0:
                    export_data.append({
                        'descripcion': descripcion,
                        'divisor': f"/{data['divisor']}",
                        'precio': final_price
                    })
            
            # Ordenar alfabéticamente
            export_data.sort(key=lambda x: x['descripcion'])
            
            # Escribir archivo con formato específico
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                
                # Línea 1: Fecha de actualización
                writer.writerow([f"Ultima act", self.export_date.get(), ""])
                
                # Línea 2: Título y ubicación
                writer.writerow(["Precios1", "", self.export_location.get()])
                
                # Líneas de productos
                for item in export_data:
                    precio_formateado = self.format_price_for_export(item['precio'])
                    writer.writerow([item['descripcion'], item['divisor'], precio_formateado])
                
                # Línea final vacía
                writer.writerow(["", "", "."])
            
            messagebox.showinfo("✅ Exportación exitosa", f"CSV exportado correctamente a:\n{filename}")
            self.price_window.destroy()
            
        except Exception as e:
            messagebox.showerror("❌ Error al exportar", f"No se pudo exportar el archivo:\n{e}")

    def format_price_for_export(self, price):
        """Formatea el precio según las reglas del CSV objetivo."""
        # Devolver solo el número sin símbolos ni comillas
        return f"{price:.0f}"


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
