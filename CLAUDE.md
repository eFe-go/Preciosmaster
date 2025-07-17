# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python desktop application for comparing pharmaceutical pricing data between two drugstores: **Asoprofarma** and **Del Sud**. It processes separate files for each drugstore (both TXT and CSV formats) to calculate unit prices and help identify the best deals through real price comparison.

## Key Architecture

### Main Application (`procesar_maestros.py`)
- **GUI Framework**: Tkinter (built into Python)
- **Configuration**: JSON-based configuration system (`divisores_config.json`)
- **External Dependency**: `pyperclip` for clipboard operations
- **File Support**: Both TXT (maestros format) and CSV (catalog format)

### Data Processing Flow
1. User selects separate TXT or CSV files for each drugstore through the GUI
2. Application detects file types and uses appropriate processors
3. Searches for configured barcodes in `TARGET_DIVISORS` dictionary in each file
4. Calculates unit prices for each drugstore using the configured divisor
5. Compares prices between the two files and identifies the best option
6. Displays results with color-coded interface showing availability and price differences

### Key Data Structure
```python
TARGET_DIVISORS = {
    "7793640000839": {
        "divisor": 2,
        "descripcion": "Product description"
    }
}
```

### Configuration System
- **File**: `divisores_config.json`
- **Structure**: Stores barcode configurations and UI settings
- **Functions**: `load_config()`, `save_config()` handle persistence
- **Management**: GUI interface for adding/editing barcodes

## Common Development Tasks

### Running the Application
```bash
python procesar_maestros.py
```

### Installing Dependencies
```bash
pip install pyperclip
```

### Testing Changes
Test manually by:
1. Running the application
2. Loading separate TXT files for each drugstore from `Precios de drogueria/`
3. Loading separate CSV files (CatalogoEspecialidades.csv, CatalogoPerfumeria.csv) for each drugstore
4. Testing the configuration window functionality
5. Verifying price calculations, comparison logic, and color coding
6. Testing scenarios with products available in only one drugstore

### Adding New Barcodes
1. Use the "Configurar Códigos" button in the GUI
2. Enter 13-digit barcode (without HE/UC prefix)
3. Set divisor (number of units per package)
4. Configuration auto-saves to JSON file

## File Formats

### TXT Files (Maestros Format)
- Fixed-width format, lines start with 'D'
- Barcodes: HE/UC + 13 digits
- Prices: 13-digit numbers starting with 0
- Descriptions: positions 20-49
- Encoding: latin-1

### CSV Files (Catalog Format)
- Headers: "Codigo de barras", "Descripcion", "Costo s/IVA", "Vigencia"
- Encoding: UTF-8
- Prices in decimal format
- **Asoprofarma**: Uses column K ("Vigencia") for public price
- **Del Sud**: Uses "Costo s/IVA" for price
- **Auto-detection**: Drugstore determined by filename

## GUI Features

### Main Interface
- **File Selection**: Separate fields for each drugstore's file
- **Colors**: Green for Asoprofarma, Blue for Del Sud
- **Subrows**: Each product shows as 2 consecutive rows (Asoprofarma first, then Del Sud)
- **Columns**: Description, divisor, unit price, drugstore, status
- **Highlighting**: Color-coded rows show availability and best prices
- **Statistics**: Real-time totals and comparisons
- **Availability**: Shows products available in one or both drugstores

### Configuration Window
- View/edit existing barcodes
- Add new products with single divisor (units per package)
- Delete obsolete codes
- Auto-save functionality

## Important Notes

- The application uses threading to prevent GUI freezing
- Configuration changes are immediately saved to JSON
- Price calculations handle division by zero
- Results are sorted alphabetically by product description
- Export functionality supports both clipboard and CSV formats
- Color coding helps quickly identify best deals