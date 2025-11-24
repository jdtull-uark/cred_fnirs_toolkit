# fNIRS Toolkit CLI Usage

## Overview

The fNIRS Toolkit CLI processes SNIRF files and generates hemoglobin analysis reports with pivot tables and heatmap visualizations.

## Installation

After installing the package, the CLI command `fnirs-toolkit` will be available:

```bash
pip install -e .
```

## Basic Usage

```bash
fnirs-toolkit <input_directory> [options]
```

### Required Arguments

- `input_dir`: Directory containing `.snirf` files to process

### Optional Arguments

- `-o, --output <dir>`: Output directory for processed data and figures (default: `output/`)
- `-m, --mapping <file>`: Path to channel mapping JSON file for region-based analysis

## Examples

### Process files with default output directory

```bash
fnirs-toolkit data/raw/
```

This will:
- Process all `.snirf` files in `data/raw/`
- Save outputs to `output/data/` and `output/figures/`

### Specify custom output directory

```bash
fnirs-toolkit data/raw/ -o results/
```

### Include channel mapping for region-based analysis

```bash
fnirs-toolkit data/raw/ -o results/ -m references/nirsit_full_channel_map.json
```

## Output Structure

The CLI generates the following outputs:

```
<output_dir>/
├── data/
│   ├── hbo_averages_detailed_pivot.csv           # Detailed Trial/Channel × Blocks
│   ├── hbo_region_dorsolateral_prefrontal_cortex.csv
│   ├── hbo_region_frontopolar_prefrontal_cortex.csv
│   ├── hbo_region_orbitofrontal_cortex.csv
│   └── hbo_region_ventrolateral_prefrontal_cortex.csv
└── figures/
    ├── heatmap_dorsolateral_prefrontal_cortex.png
    ├── heatmap_frontopolar_prefrontal_cortex.png
    ├── heatmap_orbitofrontal_cortex.png
    └── heatmap_ventrolateral_prefrontal_cortex.png
```

### Without Channel Mapping

If no channel mapping file is provided (or not found), the CLI will:
- Generate the detailed pivot table (`hbo_averages_detailed_pivot.csv`)
- Skip region-based pivot tables and heatmaps

## Input File Format

SNIRF files should follow the naming convention:
```
YYYYMMDD_TREATMENT_ID.snirf
```

For example:
- `20250624_MRSA_1.snirf`
- `20250625_N_2.snirf`
- `20250630_R_3.snirf`

The CLI extracts:
- **Trial name**: `TREATMENT_ID` (e.g., `MRSA_1`, `N_2`)
- **Treatment**: Second part of filename (e.g., `MRSA`, `N`)
- **Participant ID**: Third part of filename (e.g., `1`, `2`)

## Channel Mapping File Format

The channel mapping JSON file should have this structure:

```json
[
  {
    "source": 1,
    "detector": 1,
    "region": "Dorsolateral Prefrontal Cortex"
  },
  {
    "source": 1,
    "detector": 2,
    "region": "Frontopolar Prefrontal Cortex"
  }
]
```

## Processing Pipeline

The CLI performs the following steps:

1. **Load SNIRF files** from input directory
2. **Resample** to 5 Hz
3. **Convert to optical density**
4. **Apply temporal derivative distribution repair**
5. **Band-pass filter** (0.01-0.25 Hz)
6. **Convert to hemoglobin** using Beer-Lambert Law
7. **Extract block averages** for each channel
8. **Create pivot tables**:
   - Detailed: Trial/Channel × Blocks
   - Region-based: Trial × Blocks (averaged by region)
9. **Generate heatmaps** for each brain region

## Help

View all options:

```bash
fnirs-toolkit --help
```

## Troubleshooting

### No .snirf files found
- Verify the input directory path is correct
- Ensure files have `.snirf` extension

### Channel mapping warnings
- Some channels may not be mapped to regions
- Processing continues but unmapped channels are excluded from region analysis

### Processing errors
- Check that SNIRF files are valid and not corrupted
- Ensure all required packages are installed
