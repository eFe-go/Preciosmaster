# Procesador de Precios - Comparador de Droguerías

## Descripción

Este software está diseñado para procesar y comparar precios de medicamentos entre dos droguerías principales: **Asoprofarma** y **Del Sud**. El programa calcula el precio unitario de medicamentos (por tableta, cápsula, etc.) dividiendo el precio total de la caja por el número de unidades especificado por el usuario.

## Características Principales

- **Comparación de precios**: Muestra precios unitarios de ambas droguerías lado a lado
- **Identificación visual**: Colores distintivos para cada droguería (Verde para Asoprofarma, Azul para Del Sud)
- **Mejor precio**: Resalta automáticamente qué droguería ofrece el mejor precio
- **Múltiples formatos**: Soporta archivos TXT (formato maestros) y CSV (formato catálogo)
- **Gestión de códigos**: Interfaz para agregar, editar y eliminar códigos de barras
- **Exportación**: Copia al portapapeles o exporta a CSV
- **Estadísticas**: Muestra totales, diferencias y conteos por droguería

## Instalación

### Requisitos

- Python 3.6 o superior
- Tkinter (incluido con Python)
- pyperclip (para funcionalidad de portapapeles)

### Instalación de dependencias

```bash
pip install pyperclip
```

## Uso

### Ejecución

```bash
python procesar_maestros.py
```

### Flujo de trabajo básico

1. **Seleccionar archivo Asoprofarma**: Haga clic en "Seleccionar..." junto a "Archivo Asoprofarma" para elegir un archivo TXT o CSV
2. **Seleccionar archivo Del Sud**: Haga clic en "Seleccionar..." junto a "Archivo Del Sud" para elegir un archivo TXT o CSV
3. **Procesar datos**: Haga clic en "Procesar y Comparar" para analizar los precios de ambos archivos
4. **Revisar resultados**: La tabla mostrará los precios comparativos con colores distintivos
5. **Exportar**: Use "Copiar al Portapapeles" o "Exportar a CSV" para guardar los resultados

### Configuración de códigos

1. Haga clic en "Configurar Códigos" para abrir la ventana de configuración
2. Agregue nuevos códigos de barras con su divisor correspondiente
3. El divisor representa cuántas unidades (tabletas, cápsulas, etc.) vienen por caja
4. Los cambios se guardan automáticamente en `divisores_config.json`

## Formatos de Archivo Soportados

**Importante**: Ahora debe seleccionar un archivo para cada droguería por separado. Cada archivo debe contener los precios de una sola droguería.

### Archivos TXT (Formato Maestros)

- Archivos de texto de ancho fijo
- Cada línea comienza con 'D'
- Códigos de barras en formato HE/UC seguido de 13 dígitos
- Precios en formato de 13 dígitos comenzando con 0
- **Uso**: Seleccione un archivo TXT para Asoprofarma y otro para Del Sud

### Archivos CSV (Formato Catálogo)

- Archivos CSV con encabezados
- Columnas esperadas:
  - `Codigo de barras`: Código del producto
  - `Descripcion`: Nombre del producto
  - `Costo s/IVA`: Precio sin IVA (usado para Del Sud)
  - `Vigencia`: Precio público (usado para Asoprofarma - columna K)
- **Uso**: Seleccione un archivo CSV para Asoprofarma y otro para Del Sud
- **Detección automática**: El software detecta qué archivo pertenece a cuál droguería por el nombre

## Interpretación de Resultados

### Estructura de la tabla

Cada producto aparece en **dos filas consecutivas** (subrenglones):
- **Fila superior**: Datos de Asoprofarma (fondo verde)
- **Fila inferior**: Datos de Del Sud (fondo azul)

### Columnas de la tabla

- **Descripción**: Nombre del producto
- **Divisor**: Número de unidades por caja (mismo para ambas droguerías)
- **Precio Unitario**: Precio por unidad (tableta, cápsula, etc.)
- **Droguería**: ASOPROFARMA o DEL SUD
- **Estado**: Disponible o No disponible

### Códigos de colores

- **Verde claro**: Filas de Asoprofarma disponibles
- **Verde oscuro (negrita)**: Asoprofarma tiene mejor precio
- **Azul claro**: Filas de Del Sud disponibles
- **Azul oscuro (negrita)**: Del Sud tiene mejor precio
- **Gris**: Producto no disponible en esa droguería

### Estadísticas

La barra de estado muestra:
- Total de productos procesados
- Suma total de precios por droguería
- Diferencia total entre droguerías
- Conteo de productos donde cada droguería tiene mejor precio

## Configuración Avanzada

### Archivo de configuración

El archivo `divisores_config.json` contiene:

```json
{
  \"divisores\": {
    \"7793640000839\": {
      \"divisor\": 2,
      \"descripcion\": \"Producto ejemplo\"
    }
  },
  \"configuracion\": {
    \"color_asoprofarma\": \"#2ECC40\",
    \"color_delsud\": \"#0074D9\",
    \"mostrar_diferencia\": true,
    \"resaltar_mejor_precio\": true
  }
}
```

### Personalización de colores

Puede modificar los colores editando el archivo de configuración:
- `color_asoprofarma`: Color para Asoprofarma (hex)
- `color_delsud`: Color para Del Sud (hex)

## Casos de Uso

### Ejemplo típico

1. **Farmacia busca comparar precios**: Obtiene archivos de precios separados de cada droguería
2. **Selecciona archivos**: Carga archivo de Asoprofarma y archivo de Del Sud
3. **Configura divisores**: Establece cuántas unidades vienen por caja para cada producto
4. **Procesa comparación**: El software compara precios reales entre ambos archivos
5. **Revisa resultados**: Identifica qué droguería ofrece mejores precios para cada medicamento
6. **Toma decisiones**: Decide de qué droguería comprar cada producto

### Agregar nuevo medicamento

1. Obtener el código de barras del medicamento
2. Determinar cuántas unidades vienen por caja del producto
3. Usar \"Configurar Códigos\" para agregar el nuevo producto con su divisor
4. Reprocesar los archivos para ver los nuevos resultados

## Solución de Problemas

### Errores comunes

- **\"pyperclip no está instalado\"**: Instale con `pip install pyperclip`
- **\"Archivo no encontrado\"**: Verifique que el archivo seleccionado existe
- **\"No se encontraron productos\"**: Ningún código de barras del archivo coincide con los configurados

### Problemas de codificación

- Los archivos TXT usan codificación latin-1
- Los archivos CSV usan codificación UTF-8
- Si hay caracteres raros, verifique la codificación del archivo

## Mantenimiento

### Actualización de precios

1. Obtener nuevos archivos maestros o catálogos
2. Procesar con el software sin cambios adicionales
3. Los precios se actualizan automáticamente

### Respaldo de configuración

- Hacer copia de seguridad de `divisores_config.json`
- Contiene todos los códigos y divisores configurados

## Soporte Técnico

### Archivos de registro

El software imprime errores en la consola. Para depuración:

```bash
python procesar_maestros.py > log.txt 2>&1
```

### Información del sistema

- Versión de Python: Se requiere 3.6+
- Tkinter: Incluido con Python
- pyperclip: Para funcionalidad de portapapeles

## Actualizaciones

### Versión 2.0

- Comparación de dos droguerías
- Soporte para archivos CSV
- Interfaz de configuración gráfica
- Exportación mejorada
- Estadísticas en tiempo real

### Versión 1.1 (anterior)

- Procesamiento básico de archivos TXT
- Cálculo de precios unitarios para una sola droguería
- Interfaz simple

## Licencia

Este software es de uso interno para procesamiento de precios de medicamentos.